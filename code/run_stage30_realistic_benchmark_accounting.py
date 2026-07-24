"""Run Stage 30: drift-aware benchmark accounting and fair rebalance comparison."""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

os.environ.setdefault("OMP_NUM_THREADS", "1")

LOCAL_PACKAGE_DIR = Path(__file__).resolve().parent / ".python_packages"
if LOCAL_PACKAGE_DIR.exists():
    sys.path.append(str(LOCAL_PACKAGE_DIR))

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from run_stage21_2state_overlay_redesign import STATIC_PORTFOLIOS, static_weights
from run_stage29_filtered_rebalance_overlay import build_strategy_weights, expanding_walkforward_signals
from stage12_hmm_comparison import Stage12Config, load_stage12_inputs, performance_metrics


LOGGER = logging.getLogger(__name__)

ASSETS = ["SPY", "TLT", "GLD", "DBC", "CASH"]
OOS_START = "2013-01-01"
DIVERSIFIED = STATIC_PORTFOLIOS["static_diversified"]


def _save_table(df: pd.DataFrame, path: Path, index: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=index, encoding="utf-8-sig")


def _rebalance_flags(index: pd.Index, frequency: str) -> pd.Series:
    idx = pd.DatetimeIndex(index)
    if frequency == "buy_hold":
        flags = pd.Series(False, index=idx)
        flags.iloc[0] = True
        return flags
    if frequency == "daily":
        return pd.Series(True, index=idx)
    if frequency == "monthly":
        periods = idx.to_period("M")
    elif frequency == "quarterly":
        periods = idx.to_period("Q")
    elif frequency == "annual":
        periods = idx.to_period("Y")
    else:
        raise ValueError(f"Unsupported frequency: {frequency}")
    return pd.Series(~periods.duplicated(), index=idx)


def drift_aware_backtest(
    returns: pd.DataFrame,
    target_weights: pd.DataFrame,
    rebalance_frequency: str,
    cost_bps: float,
    start: str = OOS_START,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    r, target = returns.align(target_weights, join="inner", axis=0)
    r = r.loc[r.index >= pd.Timestamp(start)].copy()
    target = target.loc[r.index].copy()
    target = target.div(target.sum(axis=1), axis=0).fillna(0.0)
    flags = _rebalance_flags(r.index, rebalance_frequency)

    current = target.iloc[0].to_numpy(float)
    rows = []
    realized_rows = []
    for i, date in enumerate(r.index):
        target_today = target.iloc[i].to_numpy(float)
        turnover = 0.0
        if flags.loc[date]:
            turnover = float(np.abs(target_today - current).sum())
            current = target_today.copy()

        gross_return = float(np.dot(current, r.iloc[i].to_numpy(float)))
        cost = turnover * cost_bps / 10000.0
        net_return = gross_return - cost
        end_value_weights = current * (1.0 + r.iloc[i].to_numpy(float))
        denom = end_value_weights.sum()
        current = end_value_weights / denom if denom > 0 else current
        rows.append({"date": date, "net_return": net_return, "turnover": turnover, "transaction_cost": cost})
        realized_rows.append(pd.Series(current, index=r.columns, name=date))

    bt = pd.DataFrame(rows).set_index("date")
    bt["equity_curve"] = (1.0 + bt["net_return"]).cumprod()
    bt["drawdown"] = bt["equity_curve"] / bt["equity_curve"].cummax() - 1.0
    realized = pd.DataFrame(realized_rows)
    return bt, realized


def build_static_targets(returns: pd.DataFrame) -> pd.DataFrame:
    return static_weights(returns, DIVERSIFIED)


def build_hmm_targets(returns: pd.DataFrame, annual_signals: pd.DataFrame) -> dict[str, pd.DataFrame]:
    weights = build_strategy_weights(returns, annual_signals)
    return {
        "hmm_annual_hysteresis_monthly_balanced": weights["annual_hysteresis_monthly_balanced"],
        "hmm_annual_hysteresis_quarterly_balanced": weights["annual_hysteresis_quarterly_balanced"],
    }


def run_realistic_backtests(returns: pd.DataFrame, annual_signals: pd.DataFrame, cost_bps: float):
    targets = {}
    targets["static_buy_hold_diversified"] = build_static_targets(returns)
    targets["static_monthly_diversified"] = build_static_targets(returns)
    targets["static_quarterly_diversified"] = build_static_targets(returns)
    targets["static_annual_diversified"] = build_static_targets(returns)
    targets["static_ideal_daily_diversified"] = build_static_targets(returns)
    targets.update(build_hmm_targets(returns, annual_signals))

    frequencies = {
        "static_buy_hold_diversified": "buy_hold",
        "static_monthly_diversified": "monthly",
        "static_quarterly_diversified": "quarterly",
        "static_annual_diversified": "annual",
        "static_ideal_daily_diversified": "daily",
        "hmm_annual_hysteresis_monthly_balanced": "monthly",
        "hmm_annual_hysteresis_quarterly_balanced": "quarterly",
    }

    backtests = {}
    realized_weights = {}
    for name, target in targets.items():
        bt, realized = drift_aware_backtest(returns, target, frequencies[name], cost_bps)
        backtests[name] = bt
        realized_weights[name] = realized
    return targets, backtests, realized_weights, frequencies


def benchmark_deltas(performance: pd.DataFrame) -> pd.DataFrame:
    perf = performance.set_index("model")
    pairs = [
        ("hmm_annual_hysteresis_monthly_balanced", "static_monthly_diversified"),
        ("hmm_annual_hysteresis_quarterly_balanced", "static_quarterly_diversified"),
        ("hmm_annual_hysteresis_quarterly_balanced", "static_buy_hold_diversified"),
        ("hmm_annual_hysteresis_quarterly_balanced", "static_annual_diversified"),
        ("hmm_annual_hysteresis_quarterly_balanced", "static_ideal_daily_diversified"),
    ]
    rows = []
    for model, benchmark in pairs:
        rows.append(
            {
                "model": model,
                "benchmark": benchmark,
                "cagr_delta_pct_points": (perf.loc[model, "CAGR"] - perf.loc[benchmark, "CAGR"]) * 100,
                "sharpe_delta": perf.loc[model, "Sharpe"] - perf.loc[benchmark, "Sharpe"],
                "mdd_improvement_pct_points": (perf.loc[model, "max_drawdown"] - perf.loc[benchmark, "max_drawdown"]) * 100,
                "calmar_delta": perf.loc[model, "Calmar"] - perf.loc[benchmark, "Calmar"],
                "turnover_delta": perf.loc[model, "avg_turnover"] - perf.loc[benchmark, "avg_turnover"],
            }
        )
    return pd.DataFrame(rows)


def turnover_cost_summary(backtests: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for model, bt in backtests.items():
        rows.append(
            {
                "model": model,
                "avg_turnover": bt["turnover"].mean(),
                "total_turnover": bt["turnover"].sum(),
                "total_transaction_cost_drag": bt["transaction_cost"].sum(),
                "rebalance_events": int((bt["turnover"] > 1e-12).sum()),
                "days_turnover_gt_5pct": int((bt["turnover"] > 0.05).sum()),
                "days_turnover_gt_10pct": int((bt["turnover"] > 0.10).sum()),
            }
        )
    return pd.DataFrame(rows)


def crisis_summary(backtests: dict[str, pd.DataFrame], realized_weights: dict[str, pd.DataFrame]) -> pd.DataFrame:
    periods = {
        "covid": ("2020-02-01", "2020-06-30"),
        "inflation_shock": ("2022-01-01", "2022-12-31"),
        "recent": ("2023-01-01", "2026-05-15"),
    }
    rows = []
    for model, bt in backtests.items():
        w = realized_weights[model]
        for period, (start, end) in periods.items():
            sub = bt.loc[(bt.index >= start) & (bt.index <= end)]
            sw = w.loc[(w.index >= start) & (w.index <= end)]
            if len(sub) < 20:
                continue
            row = {
                "model": model,
                "period": period,
                "period_return": (1.0 + sub["net_return"]).prod() - 1.0,
                "period_max_drawdown": sub["drawdown"].min(),
                "avg_turnover": sub["turnover"].mean(),
            }
            for asset in ASSETS:
                if asset in sw:
                    row[f"avg_{asset}"] = sw[asset].mean()
            rows.append(row)
    return pd.DataFrame(rows)


def make_figures(backtests: dict[str, pd.DataFrame], output_dir: Path):
    figure_dir = output_dir / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, 5))
    for name in [
        "static_buy_hold_diversified",
        "static_quarterly_diversified",
        "hmm_annual_hysteresis_quarterly_balanced",
        "static_ideal_daily_diversified",
    ]:
        ax.plot(backtests[name].index, backtests[name]["equity_curve"], label=name)
    ax.set_title("Stage 30 drift-aware benchmark comparison")
    ax.set_ylabel("Growth of $1")
    ax.legend(fontsize=8)
    fig.tight_layout()
    path = figure_dir / "stage30_drift_aware_equity_curves.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    return {"equity_curves": path}


def build_report(performance, deltas, turnover, crisis, frequencies):
    lines = [
        "# Stage 30 Realistic Benchmark Accounting",
        "",
        "## Purpose",
        "",
        "Stage 30 replaces target-diff-only turnover with drift-aware holdings accounting. Static benchmarks are now tested as true buy-and-hold and monthly/quarterly/annual rebalanced portfolios with 2bps transaction costs.",
        "",
        "## Rebalance Policies",
        "",
        pd.DataFrame([{"model": k, "rebalance_frequency": v} for k, v in frequencies.items()]).to_markdown(index=False),
        "",
        "## Performance",
        "",
        performance.to_markdown(index=False),
        "",
        "## Fair Comparison Deltas",
        "",
        deltas.to_markdown(index=False),
        "",
        "## Turnover and Cost",
        "",
        turnover.to_markdown(index=False),
        "",
        "## Crisis Summary",
        "",
        crisis.to_markdown(index=False),
        "",
        "## Interpretation",
        "",
        "The key comparison is HMM quarterly versus static quarterly, and HMM monthly versus static monthly. Buy-and-hold and ideal daily constant-weight are included as boundary cases. This stage is pre-tax and includes only the 2bps transaction-cost assumption.",
    ]
    return "\n".join(lines)


def run_stage30(
    stage7_dir: str | Path = "outputs/stage7_mixed_frequency",
    stage9_dir: str | Path = "outputs/stage9_simplified",
    output_dir: str | Path = "outputs/stage30_realistic_benchmark_accounting",
) -> dict[str, Path]:
    stage7_dir = Path(stage7_dir)
    stage9_dir = Path(stage9_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    config = Stage12Config(n_states=2)

    LOGGER.info("Loading availability-aware axes and returns.")
    axes, returns = load_stage12_inputs(stage7_dir, stage9_dir)
    returns = returns.reindex(columns=[c for c in ASSETS if c in returns.columns])
    LOGGER.info("Building annual HMM signals.")
    annual_signals, fold_audit = expanding_walkforward_signals(axes, config, refit_frequency="YS")

    LOGGER.info("Running drift-aware static and HMM benchmark backtests.")
    targets, backtests, realized_weights, frequencies = run_realistic_backtests(returns, annual_signals, config.transaction_cost_bps)
    performance = performance_metrics(backtests)
    deltas = benchmark_deltas(performance)
    turnover = turnover_cost_summary(backtests)
    crisis = crisis_summary(backtests, realized_weights)
    figures = make_figures(backtests, output_dir)

    paths = {
        "config": output_dir / "stage30_config.json",
        "targets": output_dir / "stage30_target_weights.csv",
        "realized_weights": output_dir / "stage30_realized_weights.csv",
        "backtests": output_dir / "stage30_backtest_timeseries.csv",
        "performance": output_dir / "stage30_performance_summary.csv",
        "deltas": output_dir / "stage30_fair_comparison_deltas.csv",
        "turnover": output_dir / "stage30_turnover_cost_summary.csv",
        "crisis": output_dir / "stage30_crisis_summary.csv",
        "fold_audit": output_dir / "stage30_annual_fold_audit.csv",
        "report": output_dir / "stage30_realistic_benchmark_accounting_report.md",
        **figures,
    }
    paths["config"].write_text(
        json.dumps(
            {
                "accounting": "drift-aware holdings weights",
                "transaction_cost_bps": config.transaction_cost_bps,
                "taxes": "not included",
                "rebalance_frequencies": frequencies,
                "oos_start": OOS_START,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    _save_table(pd.concat(targets, names=["model", "date"]).reset_index(), paths["targets"])
    _save_table(pd.concat(realized_weights, names=["model", "date"]).reset_index(), paths["realized_weights"])
    _save_table(pd.concat(backtests, names=["model", "date"]).reset_index(), paths["backtests"])
    _save_table(performance, paths["performance"])
    _save_table(deltas, paths["deltas"])
    _save_table(turnover, paths["turnover"])
    _save_table(crisis, paths["crisis"])
    _save_table(fold_audit, paths["fold_audit"])
    paths["report"].write_text(build_report(performance, deltas, turnover, crisis, frequencies), encoding="utf-8")
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage7-dir", default="outputs/stage7_mixed_frequency")
    parser.add_argument("--stage9-dir", default="outputs/stage9_simplified")
    parser.add_argument("--output-dir", default="outputs/stage30_realistic_benchmark_accounting")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    paths = run_stage30(args.stage7_dir, args.stage9_dir, args.output_dir)
    print("Stage 30 outputs:")
    for name, path in paths.items():
        print(f"- {name}: {path}")


if __name__ == "__main__":
    main()
