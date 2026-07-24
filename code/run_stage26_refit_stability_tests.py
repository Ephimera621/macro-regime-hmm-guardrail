"""Run Stage 26: low-overfit refit stability tests for the 2-state overlay."""

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
from hmmlearn.hmm import GaussianHMM
from sklearn.preprocessing import StandardScaler

from run_stage21_2state_overlay_redesign import OVERLAY_SPECS, STATIC_PORTFOLIOS, probability_blend_weights, static_weights
from run_stage24_walkforward_oos_overlay import (
    ASSETS,
    INITIAL_TRAIN_END,
    OOS_START,
    _full_sample_signals,
    _oos_backtest_from_weights,
    _posterior_signal_frame,
    _risk_mapping,
    benchmark_deltas,
    crisis_oos_summary,
    expanding_walkforward_signals,
    oos_degradation,
    signal_stability,
)
from stage12_hmm_comparison import Stage12Config, _feature_matrix, backtest_weights, load_stage12_inputs, performance_metrics


LOGGER = logging.getLogger(__name__)


def _save_table(df: pd.DataFrame, path: Path, index: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=index, encoding="utf-8-sig")


def fixed_hmm_signals(
    axes: pd.DataFrame,
    config: Stage12Config,
    initial_train_end: str = INITIAL_TRAIN_END,
    oos_start: str = OOS_START,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    features, _, _ = _feature_matrix(axes)
    train = features.loc[features.index <= pd.Timestamp(initial_train_end)]
    test = features.loc[features.index >= pd.Timestamp(oos_start)]
    scaler = StandardScaler()
    x_train = scaler.fit_transform(train)
    x_test = scaler.transform(test)
    model = GaussianHMM(
        n_components=config.n_states,
        covariance_type="diag",
        min_covar=1e-4,
        n_iter=1000,
        random_state=config.random_state,
    )
    model.fit(x_train)
    train_raw = pd.Series(model.predict(x_train), index=train.index)
    mapping = _risk_mapping(train_raw, axes)
    raw_states = model.predict(x_test)
    raw_probs = model.predict_proba(x_test)
    signals = _posterior_signal_frame(
        test.index,
        raw_states,
        raw_probs,
        mapping,
        "fixed_initial_hmm",
        train.index.min(),
        train.index.max(),
    )
    fold = pd.DataFrame(
        [
            {
                "fold": "fixed_initial_hmm",
                "train_start": train.index.min(),
                "train_end": train.index.max(),
                "test_start": test.index.min(),
                "test_end": test.index.max(),
                "train_observations": len(train),
                "test_observations": len(test),
                "transition_00": model.transmat_[0, 0],
                "transition_01": model.transmat_[0, 1],
                "transition_10": model.transmat_[1, 0],
                "transition_11": model.transmat_[1, 1],
            }
        ]
    )
    return signals, fold


def run_allocations_for_signal_set(
    returns: pd.DataFrame,
    signal_sets: dict[str, pd.DataFrame],
    full_signals: pd.DataFrame,
    config: Stage12Config,
) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    start = pd.Timestamp(OOS_START)
    weights: dict[str, pd.DataFrame] = {}
    backtests: dict[str, pd.DataFrame] = {}

    for name, spec in STATIC_PORTFOLIOS.items():
        weights[name] = static_weights(returns, spec)
        backtests[name] = _oos_backtest_from_weights(returns, weights[name], config.transaction_cost_bps, start)

    for variant, spec in OVERLAY_SPECS.items():
        fs_name = f"fullsample_{variant}"
        weights[fs_name] = probability_blend_weights(returns, full_signals, spec)
        backtests[fs_name] = _oos_backtest_from_weights(returns, weights[fs_name], config.transaction_cost_bps, start)

    for signal_name, signals in signal_sets.items():
        for variant, spec in OVERLAY_SPECS.items():
            model = f"{signal_name}_{variant}"
            weights[model] = probability_blend_weights(returns, signals, spec)
            backtests[model] = _oos_backtest_from_weights(returns, weights[model], config.transaction_cost_bps, start)
    return weights, backtests


def signal_jump_summary(signal_sets: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for name, signals in signal_sets.items():
        s = signals.sort_values("date").copy()
        s["risk_prob_change"] = s["risk_probability"].diff().abs()
        s["regime_flip"] = s["regime"].ne(s["regime"].shift()).fillna(False)
        rows.append(
            {
                "signal_model": name,
                "days": len(s),
                "mean_abs_risk_prob_change": s["risk_prob_change"].mean(),
                "median_abs_risk_prob_change": s["risk_prob_change"].median(),
                "p95_abs_risk_prob_change": s["risk_prob_change"].quantile(0.95),
                "jump_gt_25pct_count": int((s["risk_prob_change"] > 0.25).sum()),
                "jump_gt_50pct_count": int((s["risk_prob_change"] > 0.50).sum()),
                "regime_flip_count": int(s["regime_flip"].sum()),
                "mean_risk_probability": s["risk_probability"].mean(),
                "high_stress_days": int((s["risk_probability"] > 0.5).sum()),
            }
        )
    return pd.DataFrame(rows)


def signal_stability_all(signal_sets: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for name, signals in signal_sets.items():
        tmp = signal_stability(signals)
        tmp["signal"] = name
        rows.append(tmp)
    return pd.concat(rows, ignore_index=True)


def performance_focus(performance: pd.DataFrame) -> pd.DataFrame:
    keep = ["static_diversified", "static_60_40_spy_tlt"]
    for prefix in ["fixed", "annual", "quarterly", "fullsample"]:
        keep.append(f"{prefix}_two_state_overlay_balanced")
    return performance[performance["model"].isin(keep)].copy()


def refit_method_deltas(performance: pd.DataFrame) -> pd.DataFrame:
    perf = performance.set_index("model")
    methods = ["fixed", "annual", "quarterly", "fullsample"]
    rows = []
    for method in methods:
        model = f"{method}_two_state_overlay_balanced"
        if model not in perf.index:
            continue
        static = perf.loc["static_diversified"]
        rows.append(
            {
                "method": method,
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
    return pd.DataFrame(rows)


def make_figures(backtests: dict[str, pd.DataFrame], signal_sets: dict[str, pd.DataFrame], output_dir: Path) -> dict[str, Path]:
    figure_dir = output_dir / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(10, 5))
    for name in [
        "static_diversified",
        "fixed_two_state_overlay_balanced",
        "annual_two_state_overlay_balanced",
        "quarterly_two_state_overlay_balanced",
        "fullsample_two_state_overlay_balanced",
    ]:
        if name in backtests:
            ax.plot(backtests[name].index, backtests[name]["equity_curve"], label=name)
    ax.set_title("Stage 26 refit stability OOS equity curves")
    ax.set_ylabel("Growth of $1")
    ax.legend(fontsize=8)
    fig.tight_layout()
    equity_path = figure_dir / "stage26_refit_method_equity_curves.png"
    fig.savefig(equity_path, dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 4))
    for name, signals in signal_sets.items():
        ax.plot(signals["date"], signals["risk_probability"], label=name, linewidth=1)
    ax.set_ylim(-0.02, 1.02)
    ax.set_title("Stage 26 stress probability by refit method")
    ax.legend(fontsize=8)
    fig.tight_layout()
    signal_path = figure_dir / "stage26_refit_method_stress_probability.png"
    fig.savefig(signal_path, dpi=150)
    plt.close(fig)
    return {"equity_curves": equity_path, "stress_probability": signal_path}


def build_report(
    performance: pd.DataFrame,
    method_deltas: pd.DataFrame,
    jump_summary: pd.DataFrame,
    stability: pd.DataFrame,
    crisis: pd.DataFrame,
) -> str:
    lines = [
        "# Stage 26 Refit Stability Tests",
        "",
        "## Purpose",
        "",
        "Stage 26 tests the Stage 25 diagnosis that quarterly refit instability, not the 2-state regime concept alone, caused OOS overlay degradation. Only low-overfit refit changes are tested: fixed initial HMM and annual expanding refit.",
        "",
        "## Refit Methods",
        "",
        "| method | HMM refit | signal update | portfolio target update |",
        "|:--|:--|:--|:--|",
        "| fixed | fit once through 2012 | daily posterior under frozen model | daily |",
        "| annual | expanding refit annually | daily posterior within each annual fold | daily |",
        "| quarterly | Stage 24 baseline | daily posterior within each quarterly fold | daily |",
        "| fullsample | lookahead context only | daily posterior | daily |",
        "",
        "## Focus Performance",
        "",
        performance_focus(performance).to_markdown(index=False),
        "",
        "## Balanced Overlay Deltas vs Static Diversified",
        "",
        method_deltas.to_markdown(index=False),
        "",
        "## Signal Jump Summary",
        "",
        jump_summary.to_markdown(index=False),
        "",
        "## Signal Stability",
        "",
        stability.to_markdown(index=False),
        "",
        "## Crisis Summary",
        "",
        crisis[crisis["model"].isin(["static_diversified", "fixed_two_state_overlay_balanced", "annual_two_state_overlay_balanced", "quarterly_two_state_overlay_balanced"])].to_markdown(index=False),
        "",
        "## Interpretation",
        "",
        "If fixed or annual refit improves OOS behavior materially versus quarterly refit, the failure mode is likely refit instability and posterior jumps. If all walk-forward variants still fail versus static diversified, the HMM overlay should be treated as a risk-monitoring or guardrail tool rather than a direct allocation engine.",
    ]
    return "\n".join(lines)


def run_stage26(
    stage7_dir: str | Path = "outputs/stage7_mixed_frequency",
    stage9_dir: str | Path = "outputs/stage9_simplified",
    output_dir: str | Path = "outputs/stage26_refit_stability_tests",
) -> dict[str, Path]:
    stage7_dir = Path(stage7_dir)
    stage9_dir = Path(stage9_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    config = Stage12Config(n_states=2)

    LOGGER.info("Loading availability-aware axes and returns.")
    axes, returns = load_stage12_inputs(stage7_dir, stage9_dir)
    returns = returns.reindex(columns=[c for c in ASSETS if c in returns.columns])

    LOGGER.info("Building fixed, annual, quarterly, and full-sample signal sets.")
    fixed_signals, fixed_fold = fixed_hmm_signals(axes, config)
    annual_signals, annual_folds = expanding_walkforward_signals(axes, config, refit_frequency="YS")
    quarterly_signals, quarterly_folds = expanding_walkforward_signals(axes, config, refit_frequency="QS")
    full_signals = _full_sample_signals(axes, config)
    signal_sets = {"fixed": fixed_signals, "annual": annual_signals, "quarterly": quarterly_signals}

    LOGGER.info("Running OOS allocation backtests for each refit method.")
    weights, backtests = run_allocations_for_signal_set(returns, signal_sets, full_signals, config)
    performance = performance_metrics(backtests)
    method_deltas = refit_method_deltas(performance)
    jump_summary = signal_jump_summary(signal_sets)
    stability = signal_stability_all(signal_sets)
    crisis = crisis_oos_summary(backtests, weights)
    degradation = oos_degradation(performance.rename(columns={"model": "model"}))
    figures = make_figures(backtests, signal_sets, output_dir)

    paths = {
        "config": output_dir / "stage26_config.json",
        "signals": output_dir / "stage26_refit_method_signals.csv",
        "fold_audit": output_dir / "stage26_refit_method_fold_audit.csv",
        "weights": output_dir / "stage26_oos_overlay_weights.csv",
        "backtests": output_dir / "stage26_oos_backtest_timeseries.csv",
        "performance": output_dir / "stage26_oos_performance_summary.csv",
        "method_deltas": output_dir / "stage26_balanced_method_deltas.csv",
        "jump_summary": output_dir / "stage26_signal_jump_summary.csv",
        "stability": output_dir / "stage26_signal_stability.csv",
        "crisis": output_dir / "stage26_crisis_summary.csv",
        "degradation": output_dir / "stage26_fullsample_degradation.csv",
        "report": output_dir / "stage26_refit_stability_tests_report.md",
        **figures,
    }
    paths["config"].write_text(
        json.dumps(
            {
                "initial_train_end": INITIAL_TRAIN_END,
                "oos_start": OOS_START,
                "methods": {
                    "fixed": "fit once through initial_train_end",
                    "annual": "expanding annual refit",
                    "quarterly": "expanding quarterly refit baseline",
                },
                "transaction_cost_bps": config.transaction_cost_bps,
                "purpose": "test refit instability diagnosis, not tune a new strategy",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    signal_table = pd.concat([df.assign(signal_model=name) for name, df in signal_sets.items()], ignore_index=True)
    fold_table = pd.concat(
        [
            fixed_fold.assign(signal_model="fixed"),
            annual_folds.assign(signal_model="annual"),
            quarterly_folds.assign(signal_model="quarterly"),
        ],
        ignore_index=True,
    )
    _save_table(signal_table, paths["signals"])
    _save_table(fold_table, paths["fold_audit"])
    _save_table(pd.concat(weights, names=["model", "date"]).reset_index(), paths["weights"])
    _save_table(pd.concat(backtests, names=["model", "date"]).reset_index(), paths["backtests"])
    _save_table(performance, paths["performance"])
    _save_table(method_deltas, paths["method_deltas"])
    _save_table(jump_summary, paths["jump_summary"])
    _save_table(stability, paths["stability"])
    _save_table(crisis, paths["crisis"])
    _save_table(degradation, paths["degradation"])
    paths["report"].write_text(build_report(performance, method_deltas, jump_summary, stability, crisis), encoding="utf-8")
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage7-dir", default="outputs/stage7_mixed_frequency")
    parser.add_argument("--stage9-dir", default="outputs/stage9_simplified")
    parser.add_argument("--output-dir", default="outputs/stage26_refit_stability_tests")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    paths = run_stage26(args.stage7_dir, args.stage9_dir, args.output_dir)
    print("Stage 26 outputs:")
    for name, path in paths.items():
        print(f"- {name}: {path}")


if __name__ == "__main__":
    main()
