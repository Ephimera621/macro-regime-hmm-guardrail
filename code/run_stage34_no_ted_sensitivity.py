"""Run Stage 34: TED-spread removal sensitivity for the final HMM guardrail.

TEDRATE is discontinued after the LIBOR transition. Earlier economic axes could
carry macro_ted_spread forward as a stale stress feature. This stage rebuilds
the Stage 9 economic axes after removing macro_ted_spread, then reruns the
Stage 32 threshold/cost robustness grid.
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

import pandas as pd

from run_stage24_walkforward_oos_overlay import ASSETS, expanding_walkforward_signals
from run_stage32_final_guardrail_robustness import (
    ACTIVATION_CONFIRM_DAYS,
    ACTIVATION_THRESHOLDS,
    COST_BPS_GRID,
    DEACTIVATION_CONFIRM_DAYS,
    DEACTIVATION_THRESHOLDS,
    attach_deltas,
    baseline_slice,
    build_report,
    make_figures,
    robustness_summaries,
    run_hmm_grid,
    static_benchmark_metrics,
)
from stage12_hmm_comparison import Stage12Config
from stage9_simplified import Stage9Config, build_economic_axes, daily_returns_from_observations, observations_to_wide


LOGGER = logging.getLogger(__name__)
REMOVED_FEATURE = "macro_ted_spread"


def _save_table(df: pd.DataFrame, path: Path, index: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=index, encoding="utf-8-sig")


def load_no_ted_inputs(stage7_dir: Path) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    observations = pd.read_csv(
        stage7_dir / "mixed_frequency_observations.csv",
        parse_dates=["observation_timestamp", "release_timestamp", "availability_timestamp"],
    )
    kept_observations = observations[~observations["feature"].eq(REMOVED_FEATURE)].copy()
    returns = daily_returns_from_observations(kept_observations)
    wide = observations_to_wide(kept_observations)
    axes, axis_inputs = build_economic_axes(wide, Stage9Config())
    axes = axes.reset_index().rename(columns={"availability_timestamp": "date", "index": "date"}).set_index("date")
    common = returns.index.intersection(axes.index)
    returns = returns.loc[common].reindex(columns=[c for c in ASSETS if c in returns.columns]).sort_index()
    axes = axes.loc[common].sort_index()
    return axes, returns, axis_inputs


def compare_with_stage32(no_ted_results: pd.DataFrame, stage32_dir: Path) -> pd.DataFrame:
    original_path = stage32_dir / "stage32_guardrail_robustness_results.csv"
    if not original_path.exists():
        return pd.DataFrame()
    original = pd.read_csv(original_path)
    keys = ["base_portfolio", "activation_threshold", "deactivation_threshold", "cost_bps"]
    cols = keys + ["CAGR", "Sharpe", "max_drawdown", "Calmar", "cagr_delta_pct_points", "mdd_improvement_pct_points", "calmar_delta", "overall_guardrail_pass"]
    merged = no_ted_results[cols].merge(original[cols], on=keys, suffixes=("_no_ted", "_original"), how="inner")
    merged["CAGR_change_no_ted_minus_original"] = merged["CAGR_no_ted"] - merged["CAGR_original"]
    merged["mdd_change_no_ted_minus_original"] = merged["max_drawdown_no_ted"] - merged["max_drawdown_original"]
    merged["calmar_change_no_ted_minus_original"] = merged["Calmar_no_ted"] - merged["Calmar_original"]
    merged["pass_changed"] = merged["overall_guardrail_pass_no_ted"] != merged["overall_guardrail_pass_original"]
    return merged


def build_no_ted_report(
    results: pd.DataFrame,
    grid_summary: pd.DataFrame,
    cost_summary: pd.DataFrame,
    threshold_summary: pd.DataFrame,
    signal_summary: pd.DataFrame,
    baseline: pd.DataFrame,
    axis_inputs: pd.DataFrame,
    original_comparison: pd.DataFrame,
) -> str:
    total_pass_rate = results["overall_guardrail_pass"].mean()
    baseline_pass_rate = baseline["overall_guardrail_pass"].mean()
    lines = [
        "# Stage 34 No-TED Sensitivity",
        "",
        "## Purpose",
        "",
        "`TEDRATE` was discontinued after the LIBOR transition, so `macro_ted_spread` can become a stale feature after 2022 if carried forward. Stage 34 removes `macro_ted_spread`, rebuilds the economic axes, and reruns the Stage 32 final guardrail robustness grid.",
        "",
        "## Removed Feature",
        "",
        f"- Removed feature: `{REMOVED_FEATURE}`",
        "- Rebuilt axes: InflationPressure, GrowthWeakness, FinancialStress, PolicyTightness, TransitionInstability",
        "- HMM / guardrail / accounting assumptions: same as Stage 32",
        "",
        "## Axis Inputs After Removal",
        "",
        axis_inputs.to_markdown(index=False),
        "",
        "## Baseline Slice",
        "",
        "Baseline means activation `0.70`, deactivation `0.40`, and cost `2bps`.",
        "",
        baseline.to_markdown(index=False),
        "",
        "## Robustness Summary",
        "",
        f"Total no-TED guardrail pass rate: `{total_pass_rate:.1%}`.",
        "",
        f"Baseline no-TED pass rate across base portfolios: `{baseline_pass_rate:.1%}`.",
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
    ]
    if not original_comparison.empty:
        summary = original_comparison.agg(
            tests=("pass_changed", "size"),
            pass_changed_count=("pass_changed", "sum"),
            median_CAGR_change=("CAGR_change_no_ted_minus_original", "median"),
            median_mdd_change=("mdd_change_no_ted_minus_original", "median"),
            median_calmar_change=("calmar_change_no_ted_minus_original", "median"),
        )
        lines.extend(
            [
                "",
                "## Comparison to Original Stage 32",
                "",
                summary.to_markdown(),
            ]
        )
    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "If the no-TED pass rate remains broad and pass/fail decisions do not materially change, the final HMM guardrail conclusion does not depend on the discontinued TED spread series. In the paper, TED can be described as removed in a sensitivity check or excluded from the final reported axis construction.",
        ]
    )
    return "\n".join(lines)


def run_stage34(
    stage7_dir: str | Path = "outputs/stage7_mixed_frequency",
    stage32_dir: str | Path = "outputs/stage32_final_guardrail_robustness",
    output_dir: str | Path = "outputs/stage34_no_ted_sensitivity",
) -> dict[str, Path]:
    stage7_dir = Path(stage7_dir)
    stage32_dir = Path(stage32_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    config = Stage12Config(n_states=2)

    LOGGER.info("Rebuilding economic axes without macro_ted_spread.")
    axes, returns, axis_inputs = load_no_ted_inputs(stage7_dir)

    LOGGER.info("Building annual HMM signals without TED.")
    annual_signals, fold_audit = expanding_walkforward_signals(axes, config, refit_frequency="YS")

    LOGGER.info("Running no-TED Stage 32 robustness grid.")
    static_metrics = static_benchmark_metrics(returns, COST_BPS_GRID)
    hmm_metrics, signal_summary = run_hmm_grid(returns, annual_signals, COST_BPS_GRID)
    results = attach_deltas(hmm_metrics, static_metrics)
    grid_summary, cost_summary, threshold_summary = robustness_summaries(results)
    baseline = baseline_slice(results)
    original_comparison = compare_with_stage32(results, stage32_dir)
    figures = make_figures(results, grid_summary, output_dir)

    paths = {
        "config": output_dir / "stage34_config.json",
        "axis_inputs": output_dir / "stage34_no_ted_axis_inputs.csv",
        "economic_axes": output_dir / "stage34_no_ted_economic_axis_scores.csv",
        "static_metrics": output_dir / "stage34_static_benchmark_metrics.csv",
        "hmm_metrics": output_dir / "stage34_hmm_grid_metrics.csv",
        "results": output_dir / "stage34_no_ted_guardrail_results.csv",
        "grid_summary": output_dir / "stage34_no_ted_grid_summary.csv",
        "cost_summary": output_dir / "stage34_no_ted_cost_summary.csv",
        "threshold_summary": output_dir / "stage34_no_ted_threshold_summary.csv",
        "signal_summary": output_dir / "stage34_no_ted_signal_activation_summary.csv",
        "baseline": output_dir / "stage34_no_ted_baseline_slice.csv",
        "original_comparison": output_dir / "stage34_no_ted_vs_stage32_comparison.csv",
        "fold_audit": output_dir / "stage34_no_ted_annual_fold_audit.csv",
        "report": output_dir / "stage34_no_ted_sensitivity_report.md",
        **figures,
    }
    paths["config"].write_text(
        json.dumps(
            {
                "stage": 34,
                "purpose": "remove discontinued TEDRATE / macro_ted_spread and rerun final robustness grid",
                "removed_feature": REMOVED_FEATURE,
                "activation_thresholds": ACTIVATION_THRESHOLDS,
                "deactivation_thresholds": DEACTIVATION_THRESHOLDS,
                "activation_confirm_days": ACTIVATION_CONFIRM_DAYS,
                "deactivation_confirm_days": DEACTIVATION_CONFIRM_DAYS,
                "cost_bps_grid": COST_BPS_GRID,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    _save_table(axis_inputs, paths["axis_inputs"])
    _save_table(axes.reset_index(), paths["economic_axes"])
    _save_table(static_metrics, paths["static_metrics"])
    _save_table(hmm_metrics, paths["hmm_metrics"])
    _save_table(results, paths["results"])
    _save_table(grid_summary, paths["grid_summary"])
    _save_table(cost_summary, paths["cost_summary"])
    _save_table(threshold_summary, paths["threshold_summary"])
    _save_table(signal_summary, paths["signal_summary"])
    _save_table(baseline, paths["baseline"])
    _save_table(original_comparison, paths["original_comparison"])
    _save_table(fold_audit, paths["fold_audit"])
    paths["report"].write_text(
        build_no_ted_report(results, grid_summary, cost_summary, threshold_summary, signal_summary, baseline, axis_inputs, original_comparison),
        encoding="utf-8",
    )
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage7-dir", default="outputs/stage7_mixed_frequency")
    parser.add_argument("--stage32-dir", default="outputs/stage32_final_guardrail_robustness")
    parser.add_argument("--output-dir", default="outputs/stage34_no_ted_sensitivity")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    paths = run_stage34(args.stage7_dir, args.stage32_dir, args.output_dir)
    print("Stage 34 outputs:")
    for name, path in paths.items():
        print(f"- {name}: {path}")


if __name__ == "__main__":
    main()
