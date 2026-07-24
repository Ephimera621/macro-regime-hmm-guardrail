"""Run Stage 14: rebuild the HMM overlay comparison around a canonical 2-state HMM."""

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

import numpy as np
import pandas as pd

from stage12_hmm_comparison import (
    Stage12Config,
    _feature_matrix,
    _risk_order_from_axes,
    baseline_hmm,
    compare_models,
    load_stage12_inputs,
)


LOGGER = logging.getLogger(__name__)


def _save_table(df: pd.DataFrame, path: Path, index: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=index, encoding="utf-8-sig")


def _transition_matrix(states: pd.Series) -> pd.DataFrame:
    prev = states.shift().dropna().astype(int)
    nxt = states.loc[prev.index].astype(int)
    labels = sorted(set(prev.unique()).union(set(nxt.unique())))
    mat = pd.DataFrame(0.0, index=labels, columns=labels)
    for i, j in zip(prev, nxt):
        mat.loc[int(i), int(j)] += 1
    return mat.div(mat.sum(axis=1).replace(0, np.nan), axis=0).fillna(0.0)


def _emission_profile(axes: pd.DataFrame, config: Stage12Config) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    features, scaler, _ = _feature_matrix(axes)
    hmm, signals, _ = baseline_hmm(axes, config)
    labels = signals.set_index("date")["raw_state"].astype(int)
    mapping = _risk_order_from_axes(labels, axes)

    means = pd.DataFrame(scaler.inverse_transform(hmm.means_), columns=features.columns)
    means.insert(0, "raw_state", range(len(means)))
    means["risk_ranked_regime"] = means["raw_state"].map(mapping)

    covars = hmm.covars_
    diag = np.diagonal(covars, axis1=1, axis2=2) if covars.ndim == 3 else covars
    variances = pd.DataFrame(diag, columns=[f"{col}_var_z" for col in features.columns])
    variances.insert(0, "raw_state", range(len(variances)))
    variances["risk_ranked_regime"] = variances["raw_state"].map(mapping)

    trans = pd.DataFrame(hmm.transmat_, columns=[f"to_raw_state_{i}" for i in range(config.n_states)])
    trans.insert(0, "raw_state", range(len(trans)))
    trans["risk_ranked_regime"] = trans["raw_state"].map(mapping)
    return (
        means.sort_values("risk_ranked_regime").reset_index(drop=True),
        variances.sort_values("risk_ranked_regime").reset_index(drop=True),
        trans.sort_values("risk_ranked_regime").reset_index(drop=True),
    )


def _state_quality(results: dict) -> pd.DataFrame:
    rows = []
    for model, signals in results["signals"].items():
        s = signals.sort_values("date")
        for col in ["raw_state", "regime"]:
            states = s[col].astype(int)
            flips = int(states.ne(states.shift()).sum() - 1)
            run_id = states.ne(states.shift()).cumsum()
            durations = states.groupby(run_id).size()
            rows.append(
                {
                    "model": model,
                    "state_column": col,
                    "flips": flips,
                    "flips_per_year": flips / (len(states) / 252),
                    "avg_duration_days": durations.mean(),
                    "median_duration_days": durations.median(),
                    "short_spell_share_lt_5d": (durations < 5).mean(),
                    "state_count": states.nunique(),
                }
            )
    return pd.DataFrame(rows)


def _three_state_comparison(stage12_dir: Path, two_state_results: dict) -> pd.DataFrame:
    two_perf = two_state_results["performance"].copy()
    two_stab = two_state_results["stability"].copy()
    two = two_perf.merge(two_stab, on="model", how="left")
    two.insert(0, "state_spec", "2_state")
    if not (stage12_dir / "model_performance_summary.csv").exists():
        return two
    three_perf = pd.read_csv(stage12_dir / "model_performance_summary.csv")
    three_stab = pd.read_csv(stage12_dir / "regime_overlay_stability.csv")
    three = three_perf.merge(three_stab, on="model", how="left")
    three.insert(0, "state_spec", "3_state_stage12")
    return pd.concat([two, three], ignore_index=True, sort=False)


def build_report(
    config: Stage12Config,
    results: dict,
    emission_means: pd.DataFrame,
    transition: pd.DataFrame,
    state_quality: pd.DataFrame,
    comparison: pd.DataFrame,
) -> str:
    perf = results["performance"].merge(results["stability"], on="model", how="left")
    baseline = perf[perf["model"].eq("model1_baseline_gaussian_hmm")].iloc[0]
    duration = perf[perf["model"].eq("model2_duration_aware_overlay")].iloc[0]
    lines = [
        "# Stage 14 Canonical 2-State HMM Rebuild",
        "",
        "## Purpose",
        "",
        "This stage re-establishes the HMM comparison around a 2-state Gaussian HMM because the earlier BIC-selected Stage 3/4 lineage favored two states, while later research stages reintroduced 3-state configurations by convention.",
        "",
        "All data, availability-lag handling, one-period execution delay, and transaction-cost assumptions are inherited from the Stage 12 comparison path.",
        "",
        "## 2-State Model Definition",
        "",
        f"`n_states={config.n_states}` with Gaussian emissions on the Stage 9 availability-aware macro-financial axes. The higher-risk state is identified by average `SystemicRiskScore`.",
        "",
        "## Emission Means",
        "",
        emission_means.to_markdown(index=False),
        "",
        "## Learned Transition Matrix",
        "",
        transition.to_markdown(index=False),
        "",
        "## Performance and Stability",
        "",
        perf.to_markdown(index=False),
        "",
        "## State Quality",
        "",
        state_quality.to_markdown(index=False),
        "",
        "## 2-State vs Prior 3-State Comparison",
        "",
        comparison[
            [
                "state_spec",
                "model",
                "CAGR",
                "Sharpe",
                "Sortino",
                "max_drawdown",
                "Calmar",
                "regime_flips",
                "avg_regime_duration_days",
                "avg_turnover",
            ]
        ].to_markdown(index=False),
        "",
        "## Interpretation",
        "",
        f"The 2-state baseline has {int(baseline['regime_flips'])} effective regime flips and average duration {baseline['avg_regime_duration_days']:.2f} days. The duration-aware version has {int(duration['regime_flips'])} flips and average duration {duration['avg_regime_duration_days']:.2f} days.",
        "",
        "Compared with the 3-state audit, the 2-state specification removes the artificial low-risk state splitting problem. It is therefore the cleaner canonical HMM baseline unless a future test shows that a third state has stable, economically distinct emissions and materially better out-of-sample behavior.",
        "",
        "The practical conclusion is not that 3 states are impossible, but that the current 3-state version lacks enough emission separability to justify the added state. The project should treat the 2-state rebuild as the default HMM lineage going forward.",
    ]
    return "\n".join(lines)


def run_stage14(
    stage7_dir: str | Path = "outputs/stage7_mixed_frequency",
    stage9_dir: str | Path = "outputs/stage9_simplified",
    stage12_dir: str | Path = "outputs/stage12_hmm_comparison",
    output_dir: str | Path = "outputs/stage14_2state_rebuild",
) -> dict[str, Path]:
    stage7_dir = Path(stage7_dir)
    stage9_dir = Path(stage9_dir)
    stage12_dir = Path(stage12_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    config = Stage12Config(n_states=2)

    LOGGER.info("Loading availability-aware Stage 7/9 inputs.")
    axes, returns = load_stage12_inputs(stage7_dir, stage9_dir)
    LOGGER.info("Running canonical 2-state HMM comparison.")
    results = compare_models(axes, returns, config)
    emission_means, emission_variances, learned_transition = _emission_profile(axes, config)
    state_quality = _state_quality(results)
    comparison = _three_state_comparison(stage12_dir, results)

    paths = {
        "config": output_dir / "stage14_config.json",
        "performance": output_dir / "two_state_model_performance_summary.csv",
        "stability": output_dir / "two_state_regime_overlay_stability.csv",
        "subperiods": output_dir / "two_state_subperiod_consistency.csv",
        "sensitivity": output_dir / "two_state_duration_parameter_sensitivity.csv",
        "signals": output_dir / "two_state_model_regime_signals.csv",
        "weights": output_dir / "two_state_model_overlay_weights.csv",
        "backtests": output_dir / "two_state_model_backtest_timeseries.csv",
        "emission_means": output_dir / "two_state_emission_means.csv",
        "emission_variances": output_dir / "two_state_emission_variances.csv",
        "learned_transition": output_dir / "two_state_learned_transition_matrix.csv",
        "empirical_state_quality": output_dir / "two_state_empirical_state_quality.csv",
        "two_vs_three": output_dir / "two_state_vs_three_state_comparison.csv",
        "report": output_dir / "two_state_canonical_rebuild_report.md",
    }

    paths["config"].write_text(json.dumps(config.__dict__, indent=2), encoding="utf-8")
    _save_table(results["performance"], paths["performance"])
    _save_table(results["stability"], paths["stability"])
    _save_table(results["subperiods"], paths["subperiods"])
    _save_table(results["sensitivity"], paths["sensitivity"])
    _save_table(pd.concat(results["signals"], names=["model"]).reset_index(level=0).reset_index(drop=True), paths["signals"])
    _save_table(pd.concat(results["weights"], names=["model", "date"]).reset_index(), paths["weights"])
    _save_table(pd.concat(results["backtests"], names=["model", "date"]).reset_index(), paths["backtests"])
    _save_table(emission_means, paths["emission_means"])
    _save_table(emission_variances, paths["emission_variances"])
    _save_table(learned_transition, paths["learned_transition"])
    _save_table(state_quality, paths["empirical_state_quality"])
    _save_table(comparison, paths["two_vs_three"])
    paths["report"].write_text(
        build_report(config, results, emission_means, learned_transition, state_quality, comparison),
        encoding="utf-8",
    )
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage7-dir", default="outputs/stage7_mixed_frequency")
    parser.add_argument("--stage9-dir", default="outputs/stage9_simplified")
    parser.add_argument("--stage12-dir", default="outputs/stage12_hmm_comparison")
    parser.add_argument("--output-dir", default="outputs/stage14_2state_rebuild")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    paths = run_stage14(args.stage7_dir, args.stage9_dir, args.stage12_dir, args.output_dir)
    print("Stage 14 outputs:")
    for name, path in paths.items():
        print(f"- {name}: {path}")


if __name__ == "__main__":
    main()
