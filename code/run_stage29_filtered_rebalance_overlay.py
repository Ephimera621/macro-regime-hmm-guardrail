"""Run Stage 29: filtered signal and rebalance-frequency overlay tests."""

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

from run_stage21_2state_overlay_redesign import OVERLAY_SPECS, STATIC_PORTFOLIOS, probability_blend_weights, static_weights
from run_stage24_walkforward_oos_overlay import ASSETS, OOS_START, _oos_backtest_from_weights, crisis_oos_summary, expanding_walkforward_signals
from stage12_hmm_comparison import Stage12Config, backtest_weights, load_stage12_inputs, performance_metrics


LOGGER = logging.getLogger(__name__)

BALANCED_SPEC = OVERLAY_SPECS["two_state_overlay_balanced"]
FILTER_CONFIG = {
    "activation_threshold": 0.70,
    "deactivation_threshold": 0.40,
    "activation_confirm_days": 5,
    "deactivation_confirm_days": 10,
}


def _save_table(df: pd.DataFrame, path: Path, index: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=index, encoding="utf-8-sig")


def apply_hysteresis(signals: pd.DataFrame, config: dict = FILTER_CONFIG) -> pd.DataFrame:
    s = signals.sort_values("date").copy()
    p = s["risk_probability"].to_numpy(float)
    active = False
    high_count = 0
    low_count = 0
    filtered = []
    for value in p:
        if value >= config["activation_threshold"]:
            high_count += 1
        else:
            high_count = 0
        if value <= config["deactivation_threshold"]:
            low_count += 1
        else:
            low_count = 0

        if not active and high_count >= config["activation_confirm_days"]:
            active = True
        elif active and low_count >= config["deactivation_confirm_days"]:
            active = False
        filtered.append(1.0 if active else 0.0)

    out = s.copy()
    out["raw_risk_probability"] = out["risk_probability"]
    out["risk_probability"] = filtered
    out["filtered_stress_active"] = np.array(filtered, dtype=int)
    out["posterior_confidence"] = np.maximum(out["risk_probability"], 1.0 - out["risk_probability"])
    out["regime"] = out["filtered_stress_active"]
    return out


def rebalance_limited_weights(target_weights: pd.DataFrame, frequency: str) -> pd.DataFrame:
    w = target_weights.sort_index().copy()
    if frequency == "daily":
        return w
    if frequency == "monthly":
        periods = w.index.to_period("M")
    elif frequency == "quarterly":
        periods = w.index.to_period("Q")
    else:
        raise ValueError(f"Unsupported rebalance frequency: {frequency}")
    rebalance_dates = w.groupby(periods).head(1).index
    limited = w.loc[rebalance_dates].reindex(w.index).ffill()
    return limited.fillna(w.iloc[0])


def build_strategy_weights(returns: pd.DataFrame, annual_signals: pd.DataFrame) -> dict[str, pd.DataFrame]:
    raw_target = probability_blend_weights(returns, annual_signals, BALANCED_SPEC)
    filtered_signals = apply_hysteresis(annual_signals)
    filtered_target = probability_blend_weights(returns, filtered_signals, BALANCED_SPEC)

    weights = {}
    for name, spec in STATIC_PORTFOLIOS.items():
        weights[name] = static_weights(returns, spec)
    weights["annual_direct_daily_balanced"] = raw_target
    weights["annual_direct_monthly_balanced"] = rebalance_limited_weights(raw_target, "monthly")
    weights["annual_hysteresis_daily_balanced"] = filtered_target
    weights["annual_hysteresis_monthly_balanced"] = rebalance_limited_weights(filtered_target, "monthly")
    weights["annual_hysteresis_quarterly_balanced"] = rebalance_limited_weights(filtered_target, "quarterly")
    return weights


def signal_filter_diagnostics(raw: pd.DataFrame, filtered: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for name, s in {"annual_raw": raw, "annual_hysteresis": filtered}.items():
        x = s.sort_values("date").copy()
        x["regime_flip"] = x["regime"].ne(x["regime"].shift()).fillna(False)
        x["prob_change"] = x["risk_probability"].diff().abs()
        rows.append(
            {
                "signal": name,
                "days": len(x),
                "mean_risk_probability": x["risk_probability"].mean(),
                "high_stress_days": int((x["risk_probability"] > 0.5).sum()),
                "high_stress_share": float((x["risk_probability"] > 0.5).mean()),
                "regime_flips": int(x["regime_flip"].sum()),
                "flips_per_year": int(x["regime_flip"].sum()) / (len(x) / 252),
                "jump_gt_50pct_count": int((x["prob_change"] > 0.5).sum()),
            }
        )
    return pd.DataFrame(rows)


def benchmark_deltas(performance: pd.DataFrame) -> pd.DataFrame:
    perf = performance.set_index("model")
    static = perf.loc["static_diversified"]
    rows = []
    for model in perf.index:
        if model.startswith("static_"):
            continue
        rows.append(
            {
                "model": model,
                "CAGR": perf.loc[model, "CAGR"],
                "Sharpe": perf.loc[model, "Sharpe"],
                "max_drawdown": perf.loc[model, "max_drawdown"],
                "Calmar": perf.loc[model, "Calmar"],
                "avg_turnover": perf.loc[model, "avg_turnover"],
                "cagr_delta_vs_static_pct_points": (perf.loc[model, "CAGR"] - static["CAGR"]) * 100,
                "sharpe_delta_vs_static": perf.loc[model, "Sharpe"] - static["Sharpe"],
                "mdd_improvement_vs_static_pct_points": (perf.loc[model, "max_drawdown"] - static["max_drawdown"]) * 100,
                "calmar_delta_vs_static": perf.loc[model, "Calmar"] - static["Calmar"],
            }
        )
    return pd.DataFrame(rows).sort_values("Sharpe", ascending=False)


def turnover_summary(backtests: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for model, bt in backtests.items():
        turnover = bt["turnover"].fillna(0.0)
        rows.append(
            {
                "model": model,
                "avg_turnover": turnover.mean(),
                "total_turnover": turnover.sum(),
                "days_turnover_gt_5pct": int((turnover > 0.05).sum()),
                "days_turnover_gt_10pct": int((turnover > 0.10).sum()),
                "estimated_total_cost_drag": (turnover * 2.0 / 10000).sum(),
            }
        )
    return pd.DataFrame(rows)


def make_figures(backtests: dict[str, pd.DataFrame], output_dir: Path) -> dict[str, Path]:
    figure_dir = output_dir / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    fig, ax = plt.subplots(figsize=(10, 5))
    for name in [
        "static_diversified",
        "annual_direct_daily_balanced",
        "annual_hysteresis_monthly_balanced",
        "annual_hysteresis_quarterly_balanced",
    ]:
        bt = backtests[name]
        ax.plot(bt.index, bt["equity_curve"], label=name)
    ax.set_title("Stage 29 filtered/rebalance OOS equity curves")
    ax.set_ylabel("Growth of $1")
    ax.legend(fontsize=8)
    fig.tight_layout()
    equity_path = figure_dir / "stage29_filtered_rebalance_equity_curves.png"
    fig.savefig(equity_path, dpi=150)
    plt.close(fig)
    return {"equity_curves": equity_path}


def build_report(performance, deltas, filter_diag, turnover, crisis):
    lines = [
        "# Stage 29 Filtered Signal / Rebalance-Frequency Overlay",
        "",
        "## Purpose",
        "",
        "Stage 29 tests whether annual HMM signals become more usable when weak regime changes are filtered and actual portfolio trading is limited to monthly or quarterly schedules.",
        "",
        "## Implementation",
        "",
        "HMM refit is annual. Raw posterior is observed daily. Hysteresis activates stress only after `p_stress >= 0.70` for 5 trading days and deactivates after `p_stress <= 0.40` for 10 trading days. Rebalance-limited variants update target weights only at the first trading day of each month or quarter.",
        "",
        "## Performance",
        "",
        performance.to_markdown(index=False),
        "",
        "## Deltas vs Static Diversified",
        "",
        deltas.to_markdown(index=False),
        "",
        "## Signal Filter Diagnostics",
        "",
        filter_diag.to_markdown(index=False),
        "",
        "## Turnover Summary",
        "",
        turnover.to_markdown(index=False),
        "",
        "## Crisis Summary",
        "",
        crisis.to_markdown(index=False),
        "",
        "## Interpretation",
        "",
        "This stage tests implementation filtering, not a new alpha model. If filtering and rebalance limits reduce turnover but still fail to improve static diversified performance, the HMM should be used as a dashboard or limited guardrail rather than a direct allocation engine.",
    ]
    return "\n".join(lines)


def run_stage29(
    stage7_dir: str | Path = "outputs/stage7_mixed_frequency",
    stage9_dir: str | Path = "outputs/stage9_simplified",
    output_dir: str | Path = "outputs/stage29_filtered_rebalance_overlay",
) -> dict[str, Path]:
    stage7_dir = Path(stage7_dir)
    stage9_dir = Path(stage9_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    config = Stage12Config(n_states=2)

    LOGGER.info("Loading availability-aware axes and returns.")
    axes, returns = load_stage12_inputs(stage7_dir, stage9_dir)
    returns = returns.reindex(columns=[c for c in ASSETS if c in returns.columns])

    LOGGER.info("Building annual refit signals and filtered overlays.")
    annual_signals, fold_audit = expanding_walkforward_signals(axes, config, refit_frequency="YS")
    filtered_signals = apply_hysteresis(annual_signals)
    weights = build_strategy_weights(returns, annual_signals)
    start = pd.Timestamp(OOS_START)
    backtests = {name: _oos_backtest_from_weights(returns, w, config.transaction_cost_bps, start) for name, w in weights.items()}
    performance = performance_metrics(backtests)
    deltas = benchmark_deltas(performance)
    filter_diag = signal_filter_diagnostics(annual_signals, filtered_signals)
    turnover = turnover_summary(backtests)
    crisis = crisis_oos_summary(backtests, weights)
    figures = make_figures(backtests, output_dir)

    paths = {
        "config": output_dir / "stage29_config.json",
        "annual_signals": output_dir / "stage29_annual_raw_signals.csv",
        "filtered_signals": output_dir / "stage29_hysteresis_signals.csv",
        "fold_audit": output_dir / "stage29_annual_fold_audit.csv",
        "weights": output_dir / "stage29_overlay_weights.csv",
        "backtests": output_dir / "stage29_backtest_timeseries.csv",
        "performance": output_dir / "stage29_oos_performance_summary.csv",
        "deltas": output_dir / "stage29_deltas_vs_static.csv",
        "filter_diagnostics": output_dir / "stage29_filter_diagnostics.csv",
        "turnover": output_dir / "stage29_turnover_summary.csv",
        "crisis": output_dir / "stage29_crisis_summary.csv",
        "report": output_dir / "stage29_filtered_rebalance_overlay_report.md",
        **figures,
    }
    paths["config"].write_text(
        json.dumps(
            {
                "hmm_refit": "annual expanding",
                "filter_config": FILTER_CONFIG,
                "rebalance_variants": ["daily", "monthly", "quarterly"],
                "overlay": "two_state_overlay_balanced",
                "transaction_cost_bps": config.transaction_cost_bps,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    _save_table(annual_signals, paths["annual_signals"])
    _save_table(filtered_signals, paths["filtered_signals"])
    _save_table(fold_audit, paths["fold_audit"])
    _save_table(pd.concat(weights, names=["model", "date"]).reset_index(), paths["weights"])
    _save_table(pd.concat(backtests, names=["model", "date"]).reset_index(), paths["backtests"])
    _save_table(performance, paths["performance"])
    _save_table(deltas, paths["deltas"])
    _save_table(filter_diag, paths["filter_diagnostics"])
    _save_table(turnover, paths["turnover"])
    _save_table(crisis, paths["crisis"])
    paths["report"].write_text(build_report(performance, deltas, filter_diag, turnover, crisis), encoding="utf-8")
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage7-dir", default="outputs/stage7_mixed_frequency")
    parser.add_argument("--stage9-dir", default="outputs/stage9_simplified")
    parser.add_argument("--output-dir", default="outputs/stage29_filtered_rebalance_overlay")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    paths = run_stage29(args.stage7_dir, args.stage9_dir, args.output_dir)
    print("Stage 29 outputs:")
    for name, path in paths.items():
        print(f"- {name}: {path}")


if __name__ == "__main__":
    main()
