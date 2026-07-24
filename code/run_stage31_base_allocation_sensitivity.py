"""Run Stage 31: base-allocation sensitivity for the 2-state HMM guardrail.

This stage tests whether the annual-refit, hysteresis-filtered, quarterly
HMM guardrail only worked because the current static diversified allocation
was well chosen, or whether the drawdown-control effect survives across a
small set of pre-declared base portfolios.
"""

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

from run_stage21_2state_overlay_redesign import probability_blend_weights, static_weights
from run_stage24_walkforward_oos_overlay import ASSETS, OOS_START, expanding_walkforward_signals
from run_stage29_filtered_rebalance_overlay import apply_hysteresis
from run_stage30_realistic_benchmark_accounting import drift_aware_backtest
from stage12_hmm_comparison import Stage12Config, load_stage12_inputs, performance_metrics


LOGGER = logging.getLogger(__name__)

BASE_PORTFOLIOS = {
    "defensive_35": {"SPY": 0.35, "TLT": 0.30, "GLD": 0.20, "DBC": 0.10, "CASH": 0.05},
    "balanced_40": {"SPY": 0.40, "TLT": 0.25, "GLD": 0.20, "DBC": 0.10, "CASH": 0.05},
    "current_45": {"SPY": 0.45, "TLT": 0.25, "GLD": 0.15, "DBC": 0.10, "CASH": 0.05},
    "growth_50": {"SPY": 0.50, "TLT": 0.25, "GLD": 0.10, "DBC": 0.10, "CASH": 0.05},
    "aggressive_55": {"SPY": 0.55, "TLT": 0.20, "GLD": 0.10, "DBC": 0.10, "CASH": 0.05},
}

DEFENSE_REALLOCATION = {"TLT": 5.0 / 28.0, "GLD": 5.0 / 28.0, "CASH": 18.0 / 28.0}


def _save_table(df: pd.DataFrame, path: Path, index: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=index, encoding="utf-8-sig")


def normalize_spec(spec: dict[str, float]) -> dict[str, float]:
    total = sum(spec.values())
    if total <= 0:
        raise ValueError("Portfolio weights must have positive total.")
    return {asset: float(spec.get(asset, 0.0)) / total for asset in ASSETS}


def stress_from_base(base: dict[str, float]) -> dict[str, float]:
    """Apply one declared defensive transformation to every base portfolio.

    The rule deliberately mirrors the Stage 21 balanced overlay for the current
    base: SPY is cut by up to 25% points, DBC by 3% points, and the released
    weight moves mostly to cash with smaller additions to TLT and GLD.
    """
    stress = normalize_spec(base)
    new_spy = max(0.20, stress["SPY"] - 0.25)
    spy_cut = stress["SPY"] - new_spy
    dbc_cut = min(0.03, max(stress["DBC"] - 0.04, 0.0))
    stress["SPY"] = new_spy
    stress["DBC"] -= dbc_cut
    released = spy_cut + dbc_cut
    for asset, share in DEFENSE_REALLOCATION.items():
        stress[asset] += released * share
    return normalize_spec(stress)


def build_overlay_spec(base: dict[str, float]) -> dict:
    return {
        "description": "Base-allocation sensitivity guardrail spec.",
        "base": normalize_spec(base),
        "stress": stress_from_base(base),
    }


def build_targets(returns: pd.DataFrame, filtered_signals: pd.DataFrame) -> tuple[dict[str, pd.DataFrame], pd.DataFrame]:
    targets = {}
    spec_rows = []
    for base_name, base in BASE_PORTFOLIOS.items():
        spec = build_overlay_spec(base)
        for regime_name, weights in {"base": spec["base"], "stress": spec["stress"]}.items():
            row = {"base_portfolio": base_name, "regime": regime_name}
            row.update(weights)
            spec_rows.append(row)
        targets[f"{base_name}_static_quarterly"] = static_weights(returns, spec["base"])
        targets[f"{base_name}_static_buy_hold"] = static_weights(returns, spec["base"])
        targets[f"{base_name}_hmm_guardrail_quarterly"] = probability_blend_weights(returns, filtered_signals, spec)
    return targets, pd.DataFrame(spec_rows)


def run_backtests(
    returns: pd.DataFrame,
    targets: dict[str, pd.DataFrame],
    cost_bps: float,
) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame], dict[str, str]]:
    backtests = {}
    realized_weights = {}
    frequencies = {}
    for name, target in targets.items():
        frequency = "buy_hold" if name.endswith("_static_buy_hold") else "quarterly"
        bt, realized = drift_aware_backtest(returns, target, frequency, cost_bps, start=OOS_START)
        backtests[name] = bt
        realized_weights[name] = realized
        frequencies[name] = frequency
    return backtests, realized_weights, frequencies


def comparison_deltas(performance: pd.DataFrame) -> pd.DataFrame:
    perf = performance.set_index("model")
    rows = []
    for base_name in BASE_PORTFOLIOS:
        hmm = f"{base_name}_hmm_guardrail_quarterly"
        static = f"{base_name}_static_quarterly"
        buy_hold = f"{base_name}_static_buy_hold"
        for benchmark in [static, buy_hold]:
            rows.append(
                {
                    "base_portfolio": base_name,
                    "model": hmm,
                    "benchmark": benchmark,
                    "cagr_delta_pct_points": (perf.loc[hmm, "CAGR"] - perf.loc[benchmark, "CAGR"]) * 100,
                    "sharpe_delta": perf.loc[hmm, "Sharpe"] - perf.loc[benchmark, "Sharpe"],
                    "mdd_improvement_pct_points": (perf.loc[hmm, "max_drawdown"] - perf.loc[benchmark, "max_drawdown"]) * 100,
                    "calmar_delta": perf.loc[hmm, "Calmar"] - perf.loc[benchmark, "Calmar"],
                    "turnover_delta": perf.loc[hmm, "avg_turnover"] - perf.loc[benchmark, "avg_turnover"],
                }
            )
    return pd.DataFrame(rows)


def pass_fail_summary(deltas: pd.DataFrame) -> pd.DataFrame:
    fair = deltas[deltas["benchmark"].str.endswith("_static_quarterly")].copy()
    fair["mdd_pass"] = fair["mdd_improvement_pct_points"] > 0.0
    fair["calmar_pass"] = fair["calmar_delta"] > 0.0
    fair["cagr_cost_pass"] = fair["cagr_delta_pct_points"] >= -0.75
    fair["overall_guardrail_pass"] = fair["mdd_pass"] & fair["calmar_pass"] & fair["cagr_cost_pass"]
    return fair


def turnover_summary(backtests: dict[str, pd.DataFrame]) -> pd.DataFrame:
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
        weights = realized_weights[model]
        for period, (start, end) in periods.items():
            sub = bt.loc[(bt.index >= start) & (bt.index <= end)]
            sub_w = weights.loc[(weights.index >= start) & (weights.index <= end)]
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
                row[f"avg_{asset}"] = sub_w[asset].mean() if asset in sub_w else np.nan
            rows.append(row)
    return pd.DataFrame(rows)


def make_figures(backtests: dict[str, pd.DataFrame], pass_fail: pd.DataFrame, output_dir: Path) -> dict[str, Path]:
    figure_dir = output_dir / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)

    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    fair = pass_fail.set_index("base_portfolio").loc[list(BASE_PORTFOLIOS)]
    axes[0].bar(fair.index, fair["cagr_delta_pct_points"], color="#607D8B")
    axes[0].axhline(0, color="black", linewidth=0.8)
    axes[0].set_title("CAGR delta vs static quarterly")
    axes[0].set_ylabel("Pct points")
    axes[1].bar(fair.index, fair["mdd_improvement_pct_points"], color="#2E7D32")
    axes[1].axhline(0, color="black", linewidth=0.8)
    axes[1].set_title("MDD improvement")
    axes[1].set_ylabel("Pct points")
    axes[2].bar(fair.index, fair["calmar_delta"], color="#455A64")
    axes[2].axhline(0, color="black", linewidth=0.8)
    axes[2].set_title("Calmar delta")
    for ax in axes:
        ax.tick_params(axis="x", rotation=35)
    fig.tight_layout()
    delta_path = figure_dir / "stage31_base_sensitivity_deltas.png"
    fig.savefig(delta_path, dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 5))
    for name in [
        "defensive_35_static_quarterly",
        "defensive_35_hmm_guardrail_quarterly",
        "current_45_static_quarterly",
        "current_45_hmm_guardrail_quarterly",
        "aggressive_55_static_quarterly",
        "aggressive_55_hmm_guardrail_quarterly",
    ]:
        ax.plot(backtests[name].index, backtests[name]["equity_curve"], label=name)
    ax.set_title("Stage 31 selected base sensitivity equity curves")
    ax.set_ylabel("Growth of $1")
    ax.legend(fontsize=7)
    fig.tight_layout()
    equity_path = figure_dir / "stage31_selected_equity_curves.png"
    fig.savefig(equity_path, dpi=150)
    plt.close(fig)
    return {"delta_bars": delta_path, "equity_curves": equity_path}


def build_report(performance, deltas, pass_fail, specs, turnover, crisis, frequencies):
    fair = pass_fail.copy()
    pass_rate = fair["overall_guardrail_pass"].mean()
    lines = [
        "# Stage 31 Base-Allocation Sensitivity",
        "",
        "## Purpose",
        "",
        "Stage 31 tests whether the HMM guardrail survives when the static policy portfolio is changed. This is not a portfolio optimization step; the base allocations and defensive transformation are pre-declared and intentionally small in number.",
        "",
        "## Shared Assumptions",
        "",
        f"- OOS start: `{OOS_START}`",
        "- HMM refit: annual expanding walk-forward",
        "- Signal filter: Stage 29 hysteresis",
        "- Rebalance: quarterly, drift-aware holdings accounting",
        "- Transaction cost: 2bps per turnover unit",
        "- Taxes: not included",
        "",
        "## Base and Stress Specifications",
        "",
        specs.to_markdown(index=False),
        "",
        "## Performance",
        "",
        performance.to_markdown(index=False),
        "",
        "## Deltas",
        "",
        deltas.to_markdown(index=False),
        "",
        "## Fair Static Quarterly Pass/Fail",
        "",
        fair.to_markdown(index=False),
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
        f"The guardrail pass rate across base portfolios is {pass_rate:.1%} under the rule: positive MDD improvement, positive Calmar delta, and CAGR drag no worse than 0.75 percentage points versus the same base portfolio rebalanced quarterly.",
        "",
        "If this pass rate is broad, the HMM guardrail is not merely an artifact of the current 45/25/15/10/5 allocation. If it concentrates in only one base, the static allocation choice is doing most of the work.",
        "",
        "## Rebalance Policies",
        "",
        pd.DataFrame([{"model": k, "rebalance_frequency": v} for k, v in frequencies.items()]).to_markdown(index=False),
    ]
    return "\n".join(lines)


def run_stage31(
    stage7_dir: str | Path = "outputs/stage7_mixed_frequency",
    stage9_dir: str | Path = "outputs/stage9_simplified",
    output_dir: str | Path = "outputs/stage31_base_allocation_sensitivity",
) -> dict[str, Path]:
    stage7_dir = Path(stage7_dir)
    stage9_dir = Path(stage9_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    config = Stage12Config(n_states=2)

    LOGGER.info("Loading availability-aware axes and returns.")
    axes, returns = load_stage12_inputs(stage7_dir, stage9_dir)
    returns = returns.reindex(columns=[c for c in ASSETS if c in returns.columns])

    LOGGER.info("Building annual HMM signals and hysteresis-filtered guardrail signal.")
    annual_signals, fold_audit = expanding_walkforward_signals(axes, config, refit_frequency="YS")
    filtered_signals = apply_hysteresis(annual_signals)

    LOGGER.info("Running base-allocation sensitivity backtests.")
    targets, specs = build_targets(returns, filtered_signals)
    backtests, realized_weights, frequencies = run_backtests(returns, targets, config.transaction_cost_bps)
    performance = performance_metrics(backtests)
    deltas = comparison_deltas(performance)
    pass_fail = pass_fail_summary(deltas)
    turnover = turnover_summary(backtests)
    crisis = crisis_summary(backtests, realized_weights)
    figures = make_figures(backtests, pass_fail, output_dir)

    paths = {
        "config": output_dir / "stage31_config.json",
        "specs": output_dir / "stage31_base_stress_specs.csv",
        "targets": output_dir / "stage31_target_weights.csv",
        "realized_weights": output_dir / "stage31_realized_weights.csv",
        "backtests": output_dir / "stage31_backtest_timeseries.csv",
        "performance": output_dir / "stage31_performance_summary.csv",
        "deltas": output_dir / "stage31_comparison_deltas.csv",
        "pass_fail": output_dir / "stage31_guardrail_pass_fail.csv",
        "turnover": output_dir / "stage31_turnover_cost_summary.csv",
        "crisis": output_dir / "stage31_crisis_summary.csv",
        "fold_audit": output_dir / "stage31_annual_fold_audit.csv",
        "report": output_dir / "stage31_base_allocation_sensitivity_report.md",
        **figures,
    }
    paths["config"].write_text(
        json.dumps(
            {
                "stage": 31,
                "purpose": "base allocation sensitivity for annual hysteresis quarterly HMM guardrail",
                "base_portfolios": BASE_PORTFOLIOS,
                "defensive_transformation": {
                    "spy_cut_pct_points": "up to 0.25 with 0.20 lower bound",
                    "dbc_cut_pct_points": "up to 0.03 with 0.04 lower bound",
                    "released_weight_reallocation": DEFENSE_REALLOCATION,
                },
                "oos_start": OOS_START,
                "transaction_cost_bps": config.transaction_cost_bps,
                "taxes": "not included",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    _save_table(specs, paths["specs"])
    _save_table(pd.concat(targets, names=["model", "date"]).reset_index(), paths["targets"])
    _save_table(pd.concat(realized_weights, names=["model", "date"]).reset_index(), paths["realized_weights"])
    _save_table(pd.concat(backtests, names=["model", "date"]).reset_index(), paths["backtests"])
    _save_table(performance, paths["performance"])
    _save_table(deltas, paths["deltas"])
    _save_table(pass_fail, paths["pass_fail"])
    _save_table(turnover, paths["turnover"])
    _save_table(crisis, paths["crisis"])
    _save_table(fold_audit, paths["fold_audit"])
    paths["report"].write_text(
        build_report(performance, deltas, pass_fail, specs, turnover, crisis, frequencies),
        encoding="utf-8",
    )
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage7-dir", default="outputs/stage7_mixed_frequency")
    parser.add_argument("--stage9-dir", default="outputs/stage9_simplified")
    parser.add_argument("--output-dir", default="outputs/stage31_base_allocation_sensitivity")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    paths = run_stage31(args.stage7_dir, args.stage9_dir, args.output_dir)
    print("Stage 31 outputs:")
    for name, path in paths.items():
        print(f"- {name}: {path}")


if __name__ == "__main__":
    main()
