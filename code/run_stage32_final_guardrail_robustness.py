"""Run Stage 32: final robustness check for the 2-state HMM guardrail.

This is the closing validation stage. It does not search for a better model.
It checks whether the Stage 31 conclusion survives modest changes in the
hysteresis thresholds and transaction-cost assumptions.
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
from run_stage31_base_allocation_sensitivity import BASE_PORTFOLIOS, build_overlay_spec
from stage12_hmm_comparison import Stage12Config, load_stage12_inputs, performance_metrics


LOGGER = logging.getLogger(__name__)

ACTIVATION_THRESHOLDS = [0.65, 0.70, 0.75]
DEACTIVATION_THRESHOLDS = [0.35, 0.40, 0.45]
COST_BPS_GRID = [0.0, 2.0, 5.0, 10.0]
ACTIVATION_CONFIRM_DAYS = 5
DEACTIVATION_CONFIRM_DAYS = 10
PASS_CAGR_FLOOR_PCT_POINTS = -0.75


def _save_table(df: pd.DataFrame, path: Path, index: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=index, encoding="utf-8-sig")


def _threshold_id(activation: float, deactivation: float) -> str:
    return f"a{int(round(activation * 100)):02d}_d{int(round(deactivation * 100)):02d}"


def static_benchmark_metrics(returns: pd.DataFrame, cost_bps_grid: list[float]) -> pd.DataFrame:
    rows = []
    for base_name, base in BASE_PORTFOLIOS.items():
        target = static_weights(returns, build_overlay_spec(base)["base"])
        for cost_bps in cost_bps_grid:
            bt, _ = drift_aware_backtest(returns, target, "quarterly", cost_bps, start=OOS_START)
            perf = performance_metrics({f"{base_name}_static_quarterly_cost_{cost_bps:g}": bt}).iloc[0].to_dict()
            rows.append(
                {
                    "base_portfolio": base_name,
                    "cost_bps": cost_bps,
                    "benchmark_model": perf["model"],
                    "benchmark_CAGR": perf["CAGR"],
                    "benchmark_Sharpe": perf["Sharpe"],
                    "benchmark_Sortino": perf["Sortino"],
                    "benchmark_max_drawdown": perf["max_drawdown"],
                    "benchmark_Calmar": perf["Calmar"],
                    "benchmark_avg_turnover": perf["avg_turnover"],
                }
            )
    return pd.DataFrame(rows)


def run_hmm_grid(returns: pd.DataFrame, annual_signals: pd.DataFrame, cost_bps_grid: list[float]) -> tuple[pd.DataFrame, pd.DataFrame]:
    metric_rows = []
    signal_rows = []
    for activation in ACTIVATION_THRESHOLDS:
        for deactivation in DEACTIVATION_THRESHOLDS:
            if deactivation >= activation:
                continue
            threshold_name = _threshold_id(activation, deactivation)
            filter_config = {
                "activation_threshold": activation,
                "deactivation_threshold": deactivation,
                "activation_confirm_days": ACTIVATION_CONFIRM_DAYS,
                "deactivation_confirm_days": DEACTIVATION_CONFIRM_DAYS,
            }
            filtered = apply_hysteresis(annual_signals, filter_config)
            active = filtered["filtered_stress_active"].astype(int)
            signal_rows.append(
                {
                    "threshold_set": threshold_name,
                    "activation_threshold": activation,
                    "deactivation_threshold": deactivation,
                    "stress_active_days": int(active.sum()),
                    "stress_active_share": float(active.mean()),
                    "stress_activation_events": int((active.diff().fillna(active) > 0).sum()),
                    "stress_deactivation_events": int((active.diff().fillna(0) < 0).sum()),
                }
            )
            for base_name, base in BASE_PORTFOLIOS.items():
                spec = build_overlay_spec(base)
                target = probability_blend_weights(returns, filtered, spec)
                for cost_bps in cost_bps_grid:
                    model_name = f"{base_name}_hmm_{threshold_name}_cost_{cost_bps:g}"
                    bt, _ = drift_aware_backtest(returns, target, "quarterly", cost_bps, start=OOS_START)
                    perf = performance_metrics({model_name: bt}).iloc[0].to_dict()
                    metric_rows.append(
                        {
                            "base_portfolio": base_name,
                            "threshold_set": threshold_name,
                            "activation_threshold": activation,
                            "deactivation_threshold": deactivation,
                            "cost_bps": cost_bps,
                            "model": model_name,
                            "CAGR": perf["CAGR"],
                            "Sharpe": perf["Sharpe"],
                            "Sortino": perf["Sortino"],
                            "max_drawdown": perf["max_drawdown"],
                            "Calmar": perf["Calmar"],
                            "avg_turnover": perf["avg_turnover"],
                        }
                    )
    return pd.DataFrame(metric_rows), pd.DataFrame(signal_rows)


def attach_deltas(hmm_metrics: pd.DataFrame, static_metrics: pd.DataFrame) -> pd.DataFrame:
    merged = hmm_metrics.merge(static_metrics, on=["base_portfolio", "cost_bps"], how="left")
    merged["cagr_delta_pct_points"] = (merged["CAGR"] - merged["benchmark_CAGR"]) * 100
    merged["sharpe_delta"] = merged["Sharpe"] - merged["benchmark_Sharpe"]
    merged["mdd_improvement_pct_points"] = (merged["max_drawdown"] - merged["benchmark_max_drawdown"]) * 100
    merged["calmar_delta"] = merged["Calmar"] - merged["benchmark_Calmar"]
    merged["turnover_delta"] = merged["avg_turnover"] - merged["benchmark_avg_turnover"]
    merged["mdd_pass"] = merged["mdd_improvement_pct_points"] > 0.0
    merged["calmar_pass"] = merged["calmar_delta"] > 0.0
    merged["cagr_cost_pass"] = merged["cagr_delta_pct_points"] >= PASS_CAGR_FLOOR_PCT_POINTS
    merged["overall_guardrail_pass"] = merged["mdd_pass"] & merged["calmar_pass"] & merged["cagr_cost_pass"]
    return merged


def robustness_summaries(results: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    grouped = results.groupby(["activation_threshold", "deactivation_threshold", "cost_bps"], as_index=False)
    grid_summary = grouped.agg(
        tests=("overall_guardrail_pass", "size"),
        pass_rate=("overall_guardrail_pass", "mean"),
        median_cagr_delta_pct_points=("cagr_delta_pct_points", "median"),
        median_sharpe_delta=("sharpe_delta", "median"),
        median_mdd_improvement_pct_points=("mdd_improvement_pct_points", "median"),
        median_calmar_delta=("calmar_delta", "median"),
        median_turnover_delta=("turnover_delta", "median"),
    )

    cost_summary = results.groupby("cost_bps", as_index=False).agg(
        tests=("overall_guardrail_pass", "size"),
        pass_rate=("overall_guardrail_pass", "mean"),
        median_cagr_delta_pct_points=("cagr_delta_pct_points", "median"),
        median_mdd_improvement_pct_points=("mdd_improvement_pct_points", "median"),
        median_calmar_delta=("calmar_delta", "median"),
    )

    threshold_summary = results.groupby(["activation_threshold", "deactivation_threshold"], as_index=False).agg(
        tests=("overall_guardrail_pass", "size"),
        pass_rate=("overall_guardrail_pass", "mean"),
        median_cagr_delta_pct_points=("cagr_delta_pct_points", "median"),
        median_mdd_improvement_pct_points=("mdd_improvement_pct_points", "median"),
        median_calmar_delta=("calmar_delta", "median"),
    )
    return grid_summary, cost_summary, threshold_summary


def baseline_slice(results: pd.DataFrame) -> pd.DataFrame:
    return results[
        (results["activation_threshold"].eq(0.70))
        & (results["deactivation_threshold"].eq(0.40))
        & (results["cost_bps"].eq(2.0))
    ].copy()


def make_figures(results: pd.DataFrame, grid_summary: pd.DataFrame, output_dir: Path) -> dict[str, Path]:
    figure_dir = output_dir / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)
    figures = {}

    for cost_bps in [0.0, 2.0, 5.0, 10.0]:
        sub = grid_summary[grid_summary["cost_bps"].eq(cost_bps)]
        pivot = sub.pivot(index="activation_threshold", columns="deactivation_threshold", values="pass_rate")
        fig, ax = plt.subplots(figsize=(5, 4))
        im = ax.imshow(pivot.values, vmin=0, vmax=1, cmap="viridis")
        ax.set_xticks(np.arange(len(pivot.columns)), [f"{x:.2f}" for x in pivot.columns])
        ax.set_yticks(np.arange(len(pivot.index)), [f"{x:.2f}" for x in pivot.index])
        ax.set_xlabel("Deactivation threshold")
        ax.set_ylabel("Activation threshold")
        ax.set_title(f"Pass rate by threshold, cost {cost_bps:g}bps")
        for i in range(pivot.shape[0]):
            for j in range(pivot.shape[1]):
                ax.text(j, i, f"{pivot.values[i, j]:.0%}", ha="center", va="center", color="white")
        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        fig.tight_layout()
        path = figure_dir / f"stage32_pass_rate_heatmap_cost_{cost_bps:g}bps.png"
        fig.savefig(path, dpi=150)
        plt.close(fig)
        figures[f"pass_heatmap_{cost_bps:g}bps"] = path

    baseline = baseline_slice(results).set_index("base_portfolio").loc[list(BASE_PORTFOLIOS)]
    fig, axes = plt.subplots(1, 3, figsize=(13, 4))
    axes[0].bar(baseline.index, baseline["cagr_delta_pct_points"], color="#607D8B")
    axes[0].axhline(0, color="black", linewidth=0.8)
    axes[0].set_title("Baseline CAGR delta")
    axes[0].set_ylabel("Pct points")
    axes[1].bar(baseline.index, baseline["mdd_improvement_pct_points"], color="#2E7D32")
    axes[1].axhline(0, color="black", linewidth=0.8)
    axes[1].set_title("Baseline MDD improvement")
    axes[1].set_ylabel("Pct points")
    axes[2].bar(baseline.index, baseline["calmar_delta"], color="#455A64")
    axes[2].axhline(0, color="black", linewidth=0.8)
    axes[2].set_title("Baseline Calmar delta")
    for ax in axes:
        ax.tick_params(axis="x", rotation=35)
    fig.tight_layout()
    path = figure_dir / "stage32_baseline_guardrail_deltas.png"
    fig.savefig(path, dpi=150)
    plt.close(fig)
    figures["baseline_deltas"] = path
    return figures


def build_report(results, grid_summary, cost_summary, threshold_summary, signal_summary, baseline):
    total_pass_rate = results["overall_guardrail_pass"].mean()
    baseline_pass_rate = baseline["overall_guardrail_pass"].mean()
    lines = [
        "# Stage 32 Final Guardrail Robustness",
        "",
        "## Purpose",
        "",
        "Stage 32 is the final validation pass. It checks whether the annual-refit, hysteresis-filtered, quarterly 2-state HMM guardrail is fragile to modest threshold or transaction-cost changes.",
        "",
        "## Grid",
        "",
        f"- Activation thresholds: `{ACTIVATION_THRESHOLDS}`",
        f"- Deactivation thresholds: `{DEACTIVATION_THRESHOLDS}`",
        f"- Confirmation days: activation `{ACTIVATION_CONFIRM_DAYS}`, deactivation `{DEACTIVATION_CONFIRM_DAYS}`",
        f"- Transaction costs: `{COST_BPS_GRID}` bps",
        f"- Base portfolios: `{list(BASE_PORTFOLIOS)}`",
        f"- OOS start: `{OOS_START}`",
        "",
        "The grid is deliberately small and theory-driven. It is not used to select a best model.",
        "",
        "## Baseline Slice",
        "",
        "Baseline means activation `0.70`, deactivation `0.40`, and cost `2bps`, matching Stage 31.",
        "",
        baseline.to_markdown(index=False),
        "",
        "## Overall Robustness",
        "",
        f"Total guardrail pass rate across all base/threshold/cost combinations: `{total_pass_rate:.1%}`.",
        "",
        f"Baseline pass rate across base portfolios: `{baseline_pass_rate:.1%}`.",
        "",
        "Pass means positive MDD improvement, positive Calmar delta, and CAGR drag no worse than 0.75 percentage points versus the same base portfolio rebalanced quarterly under the same cost assumption.",
        "",
        "## Cost Summary",
        "",
        cost_summary.to_markdown(index=False),
        "",
        "## Threshold Summary",
        "",
        threshold_summary.to_markdown(index=False),
        "",
        "## Full Grid Summary",
        "",
        grid_summary.to_markdown(index=False),
        "",
        "## Signal Activation Summary",
        "",
        signal_summary.to_markdown(index=False),
        "",
        "## Final Interpretation",
        "",
        "If the pass rate remains broad across costs and nearby thresholds, the research conclusion can be closed: the HMM signal is not strong enough to be a direct allocation engine, but it is usable as a low-frequency drawdown guardrail around a static diversified policy portfolio.",
    ]
    return "\n".join(lines)


def run_stage32(
    stage7_dir: str | Path = "outputs/stage7_mixed_frequency",
    stage9_dir: str | Path = "outputs/stage9_simplified",
    output_dir: str | Path = "outputs/stage32_final_guardrail_robustness",
) -> dict[str, Path]:
    stage7_dir = Path(stage7_dir)
    stage9_dir = Path(stage9_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    config = Stage12Config(n_states=2)

    LOGGER.info("Loading availability-aware axes and returns.")
    axes, returns = load_stage12_inputs(stage7_dir, stage9_dir)
    returns = returns.reindex(columns=[c for c in ASSETS if c in returns.columns])

    LOGGER.info("Building annual HMM signals once.")
    annual_signals, fold_audit = expanding_walkforward_signals(axes, config, refit_frequency="YS")

    LOGGER.info("Running static benchmarks and HMM threshold/cost grid.")
    static_metrics = static_benchmark_metrics(returns, COST_BPS_GRID)
    hmm_metrics, signal_summary = run_hmm_grid(returns, annual_signals, COST_BPS_GRID)
    results = attach_deltas(hmm_metrics, static_metrics)
    grid_summary, cost_summary, threshold_summary = robustness_summaries(results)
    baseline = baseline_slice(results)
    figures = make_figures(results, grid_summary, output_dir)

    paths = {
        "config": output_dir / "stage32_config.json",
        "static_metrics": output_dir / "stage32_static_benchmark_metrics.csv",
        "hmm_metrics": output_dir / "stage32_hmm_grid_metrics.csv",
        "results": output_dir / "stage32_guardrail_robustness_results.csv",
        "grid_summary": output_dir / "stage32_grid_summary.csv",
        "cost_summary": output_dir / "stage32_cost_summary.csv",
        "threshold_summary": output_dir / "stage32_threshold_summary.csv",
        "signal_summary": output_dir / "stage32_signal_activation_summary.csv",
        "baseline": output_dir / "stage32_baseline_slice.csv",
        "fold_audit": output_dir / "stage32_annual_fold_audit.csv",
        "report": output_dir / "stage32_final_guardrail_robustness_report.md",
        **figures,
    }
    paths["config"].write_text(
        json.dumps(
            {
                "stage": 32,
                "purpose": "final threshold and transaction-cost robustness for HMM guardrail",
                "activation_thresholds": ACTIVATION_THRESHOLDS,
                "deactivation_thresholds": DEACTIVATION_THRESHOLDS,
                "activation_confirm_days": ACTIVATION_CONFIRM_DAYS,
                "deactivation_confirm_days": DEACTIVATION_CONFIRM_DAYS,
                "cost_bps_grid": COST_BPS_GRID,
                "base_portfolios": BASE_PORTFOLIOS,
                "pass_rule": {
                    "mdd_improvement_pct_points": "> 0",
                    "calmar_delta": "> 0",
                    "cagr_delta_pct_points": f">= {PASS_CAGR_FLOOR_PCT_POINTS}",
                },
                "oos_start": OOS_START,
                "taxes": "not included",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    _save_table(static_metrics, paths["static_metrics"])
    _save_table(hmm_metrics, paths["hmm_metrics"])
    _save_table(results, paths["results"])
    _save_table(grid_summary, paths["grid_summary"])
    _save_table(cost_summary, paths["cost_summary"])
    _save_table(threshold_summary, paths["threshold_summary"])
    _save_table(signal_summary, paths["signal_summary"])
    _save_table(baseline, paths["baseline"])
    _save_table(fold_audit, paths["fold_audit"])
    paths["report"].write_text(
        build_report(results, grid_summary, cost_summary, threshold_summary, signal_summary, baseline),
        encoding="utf-8",
    )
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage7-dir", default="outputs/stage7_mixed_frequency")
    parser.add_argument("--stage9-dir", default="outputs/stage9_simplified")
    parser.add_argument("--output-dir", default="outputs/stage32_final_guardrail_robustness")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    paths = run_stage32(args.stage7_dir, args.stage9_dir, args.output_dir)
    print("Stage 32 outputs:")
    for name, path in paths.items():
        print(f"- {name}: {path}")


if __name__ == "__main__":
    main()
