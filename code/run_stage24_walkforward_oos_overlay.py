"""Run Stage 24: expanding walk-forward OOS test for the 2-state overlay."""

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

from run_stage21_2state_overlay_redesign import (
    OVERLAY_SPECS,
    STATIC_PORTFOLIOS,
    probability_blend_weights,
    static_weights,
)
from stage12_hmm_comparison import (
    Stage12Config,
    _feature_matrix,
    backtest_weights,
    baseline_hmm,
    load_stage12_inputs,
    performance_metrics,
)


LOGGER = logging.getLogger(__name__)

INITIAL_TRAIN_END = "2012-12-31"
OOS_START = "2013-01-01"
REFIT_FREQUENCY = "QS"
ASSETS = ["SPY", "TLT", "GLD", "DBC", "CASH"]


def _save_table(df: pd.DataFrame, path: Path, index: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=index, encoding="utf-8-sig")


def _risk_mapping(raw_states: pd.Series, axes: pd.DataFrame) -> dict[int, int]:
    risk = axes.loc[raw_states.index, "SystemicRiskScore"].groupby(raw_states).mean().sort_values()
    return {int(raw): rank for rank, raw in enumerate(risk.index)}


def _posterior_signal_frame(
    test_index: pd.Index,
    raw_states: np.ndarray,
    raw_probs: np.ndarray,
    mapping: dict[int, int],
    fold: str,
    train_start: pd.Timestamp,
    train_end: pd.Timestamp,
) -> pd.DataFrame:
    risk_raw_states = [raw for raw, rank in mapping.items() if rank == max(mapping.values())]
    risk_prob = raw_probs[:, risk_raw_states].sum(axis=1)
    regime = pd.Series(raw_states, index=test_index).map(mapping).astype(int)
    confidence = np.maximum(risk_prob, 1.0 - risk_prob)
    return pd.DataFrame(
        {
            "fold": fold,
            "train_start": train_start,
            "train_end": train_end,
            "date": test_index,
            "raw_state": raw_states.astype(int),
            "regime": regime.to_numpy(int),
            "risk_probability": risk_prob.astype(float),
            "posterior_confidence": confidence.astype(float),
        }
    )


def expanding_walkforward_signals(
    axes: pd.DataFrame,
    config: Stage12Config,
    initial_train_end: str = INITIAL_TRAIN_END,
    oos_start: str = OOS_START,
    refit_frequency: str = REFIT_FREQUENCY,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    features, _, _ = _feature_matrix(axes)
    oos_dates = features.loc[features.index >= pd.Timestamp(oos_start)].index
    quarter_starts = pd.date_range(oos_dates.min(), oos_dates.max(), freq=refit_frequency)
    if len(quarter_starts) == 0 or quarter_starts[0] > oos_dates.min():
        quarter_starts = quarter_starts.insert(0, oos_dates.min())

    signal_parts = []
    fold_rows = []
    for fold_no, start in enumerate(quarter_starts):
        start = pd.Timestamp(start)
        next_start = quarter_starts[fold_no + 1] if fold_no + 1 < len(quarter_starts) else oos_dates.max() + pd.Timedelta(days=1)
        test_index = features.loc[(features.index >= start) & (features.index < next_start)].index
        if test_index.empty:
            continue
        train_end = test_index.min() - pd.Timedelta(days=1)
        if train_end < pd.Timestamp(initial_train_end):
            train_end = pd.Timestamp(initial_train_end)
        train = features.loc[features.index <= train_end]
        test = features.loc[test_index]
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
        fold = f"wf_{fold_no:03d}"
        signal_parts.append(_posterior_signal_frame(test_index, raw_states, raw_probs, mapping, fold, train.index.min(), train_end))
        fold_rows.append(
            {
                "fold": fold,
                "train_start": train.index.min(),
                "train_end": train_end,
                "test_start": test_index.min(),
                "test_end": test_index.max(),
                "train_observations": len(train),
                "test_observations": len(test),
                "regime_0_mean_systemic_risk": axes.loc[train_raw[train_raw.map(mapping).eq(0)].index, "SystemicRiskScore"].mean(),
                "regime_1_mean_systemic_risk": axes.loc[train_raw[train_raw.map(mapping).eq(1)].index, "SystemicRiskScore"].mean(),
                "transition_00": model.transmat_[0, 0],
                "transition_01": model.transmat_[0, 1],
                "transition_10": model.transmat_[1, 0],
                "transition_11": model.transmat_[1, 1],
            }
        )
    signals = pd.concat(signal_parts, ignore_index=True).sort_values("date")
    return signals, pd.DataFrame(fold_rows)


def _full_sample_signals(axes: pd.DataFrame, config: Stage12Config) -> pd.DataFrame:
    _, signals, _ = baseline_hmm(axes, config)
    signals["risk_probability"] = signals["prob_regime_1"].astype(float)
    return signals


def _oos_backtest_from_weights(returns: pd.DataFrame, weights: pd.DataFrame, cost_bps: float, start: pd.Timestamp) -> pd.DataFrame:
    bt = backtest_weights(returns, weights, cost_bps)
    out = bt.loc[bt.index >= start].copy()
    out["equity_curve"] = (1.0 + out["net_return"]).cumprod()
    out["drawdown"] = out["equity_curve"] / out["equity_curve"].cummax() - 1.0
    return out


def run_oos_allocations(
    returns: pd.DataFrame,
    wf_signals: pd.DataFrame,
    full_signals: pd.DataFrame,
    config: Stage12Config,
    oos_start: str,
) -> tuple[dict[str, pd.DataFrame], dict[str, pd.DataFrame]]:
    start = pd.Timestamp(oos_start)
    weights: dict[str, pd.DataFrame] = {}
    backtests: dict[str, pd.DataFrame] = {}

    for name, spec in STATIC_PORTFOLIOS.items():
        weights[name] = static_weights(returns, spec)
        backtests[name] = _oos_backtest_from_weights(returns, weights[name], config.transaction_cost_bps, start)

    for name, spec in OVERLAY_SPECS.items():
        wf_name = f"walkforward_{name}"
        weights[wf_name] = probability_blend_weights(returns, wf_signals, spec)
        backtests[wf_name] = _oos_backtest_from_weights(returns, weights[wf_name], config.transaction_cost_bps, start)

        fs_name = f"fullsample_{name}"
        weights[fs_name] = probability_blend_weights(returns, full_signals, spec)
        backtests[fs_name] = _oos_backtest_from_weights(returns, weights[fs_name], config.transaction_cost_bps, start)

    return weights, backtests


def signal_stability(signals: pd.DataFrame) -> pd.DataFrame:
    s = signals.sort_values("date").set_index("date")
    regimes = s["regime"].astype(int)
    flips = int(regimes.ne(regimes.shift()).sum() - 1)
    run_id = regimes.ne(regimes.shift()).cumsum()
    durations = regimes.groupby(run_id).size()
    return pd.DataFrame(
        [
            {
                "signal": "walkforward",
                "start": s.index.min(),
                "end": s.index.max(),
                "observations": len(s),
                "regime_flips": max(flips, 0),
                "flips_per_year": max(flips, 0) / (len(s) / 252),
                "avg_regime_duration_days": durations.mean(),
                "median_regime_duration_days": durations.median(),
                "mean_risk_probability": s["risk_probability"].mean(),
                "median_risk_probability": s["risk_probability"].median(),
                "mean_posterior_confidence": s["posterior_confidence"].mean(),
            }
        ]
    )


def oos_degradation(performance: pd.DataFrame) -> pd.DataFrame:
    rows = []
    perf = performance.set_index("model")
    for variant in OVERLAY_SPECS:
        wf = f"walkforward_{variant}"
        fs = f"fullsample_{variant}"
        if wf not in perf.index or fs not in perf.index:
            continue
        rows.append(
            {
                "variant": variant,
                "CAGR_degradation": perf.loc[wf, "CAGR"] - perf.loc[fs, "CAGR"],
                "Sharpe_degradation": perf.loc[wf, "Sharpe"] - perf.loc[fs, "Sharpe"],
                "MDD_degradation": perf.loc[wf, "max_drawdown"] - perf.loc[fs, "max_drawdown"],
                "Calmar_degradation": perf.loc[wf, "Calmar"] - perf.loc[fs, "Calmar"],
                "turnover_delta": perf.loc[wf, "avg_turnover"] - perf.loc[fs, "avg_turnover"],
            }
        )
    return pd.DataFrame(rows)


def benchmark_deltas(performance: pd.DataFrame) -> pd.DataFrame:
    rows = []
    perf = performance.set_index("model")
    benchmarks = ["static_diversified", "static_60_40_spy_tlt"]
    overlays = [f"walkforward_{name}" for name in OVERLAY_SPECS]
    for overlay in overlays:
        for benchmark in benchmarks:
            rows.append(
                {
                    "overlay_model": overlay,
                    "benchmark": benchmark,
                    "cagr_delta_pct_points": (perf.loc[overlay, "CAGR"] - perf.loc[benchmark, "CAGR"]) * 100,
                    "sharpe_delta": perf.loc[overlay, "Sharpe"] - perf.loc[benchmark, "Sharpe"],
                    "mdd_improvement_pct_points": (perf.loc[overlay, "max_drawdown"] - perf.loc[benchmark, "max_drawdown"]) * 100,
                    "calmar_delta": perf.loc[overlay, "Calmar"] - perf.loc[benchmark, "Calmar"],
                    "turnover_delta": perf.loc[overlay, "avg_turnover"] - perf.loc[benchmark, "avg_turnover"],
                }
            )
    return pd.DataFrame(rows)


def crisis_oos_summary(backtests: dict[str, pd.DataFrame], weights: dict[str, pd.DataFrame]) -> pd.DataFrame:
    periods = {
        "covid": ("2020-02-01", "2020-06-30"),
        "inflation_shock": ("2022-01-01", "2022-12-31"),
        "recent": ("2023-01-01", "2026-05-15"),
    }
    rows = []
    for model, bt in backtests.items():
        w = weights[model]
        for period, (start, end) in periods.items():
            sub_bt = bt.loc[(bt.index >= start) & (bt.index <= end)]
            sub_w = w.loc[(w.index >= start) & (w.index <= end)]
            if len(sub_bt) < 20 or len(sub_w) < 20:
                continue
            rows.append(
                {
                    "model": model,
                    "period": period,
                    "period_return": (1.0 + sub_bt["net_return"]).prod() - 1.0,
                    "period_max_drawdown": sub_bt["drawdown"].min(),
                    "avg_turnover": sub_bt["turnover"].mean(),
                    "avg_SPY": sub_w["SPY"].mean() if "SPY" in sub_w else np.nan,
                    "avg_TLT": sub_w["TLT"].mean() if "TLT" in sub_w else np.nan,
                    "avg_GLD": sub_w["GLD"].mean() if "GLD" in sub_w else np.nan,
                    "avg_DBC": sub_w["DBC"].mean() if "DBC" in sub_w else np.nan,
                    "avg_CASH": sub_w["CASH"].mean() if "CASH" in sub_w else np.nan,
                }
            )
    return pd.DataFrame(rows)


def make_figures(backtests: dict[str, pd.DataFrame], wf_signals: pd.DataFrame, output_dir: Path) -> dict[str, Path]:
    figure_dir = output_dir / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(10, 5))
    for name in ["static_diversified", "walkforward_two_state_overlay_balanced", "fullsample_two_state_overlay_balanced"]:
        bt = backtests[name]
        ax.plot(bt.index, bt["equity_curve"], label=name)
    ax.set_title("Stage 24 OOS equity curves")
    ax.set_ylabel("Growth of $1 from OOS start")
    ax.legend(fontsize=8)
    fig.tight_layout()
    equity_path = figure_dir / "stage24_oos_equity_curves.png"
    fig.savefig(equity_path, dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 4))
    sig = wf_signals.sort_values("date")
    ax.plot(sig["date"], sig["risk_probability"], color="tab:red", linewidth=1)
    ax.set_title("Stage 24 walk-forward stress probability")
    ax.set_ylabel("p_stress")
    ax.set_ylim(-0.02, 1.02)
    fig.tight_layout()
    prob_path = figure_dir / "stage24_walkforward_stress_probability.png"
    fig.savefig(prob_path, dpi=150)
    plt.close(fig)

    return {"equity_curves": equity_path, "stress_probability": prob_path}


def build_report(
    performance: pd.DataFrame,
    deltas: pd.DataFrame,
    degradation: pd.DataFrame,
    stability: pd.DataFrame,
    fold_audit: pd.DataFrame,
    crisis: pd.DataFrame,
) -> str:
    lines = [
        "# Stage 24 Walk-Forward OOS Overlay Validation",
        "",
        "## Purpose",
        "",
        "Stage 24 tests whether the 2-state HMM overlay remains useful when the HMM is fit only on past data. The model is re-estimated on an expanding window each quarter and applied to the next quarter.",
        "",
        "## Walk-Forward Setup",
        "",
        f"Initial training end: `{INITIAL_TRAIN_END}`. OOS start: `{OOS_START}`. Refit frequency: `{REFIT_FREQUENCY}`.",
        "",
        "## OOS Performance",
        "",
        performance.to_markdown(index=False),
        "",
        "## Walk-Forward Overlay Deltas",
        "",
        deltas.to_markdown(index=False),
        "",
        "## Walk-Forward vs Full-Sample Degradation",
        "",
        degradation.to_markdown(index=False),
        "",
        "## Signal Stability",
        "",
        stability.to_markdown(index=False),
        "",
        "## Crisis / Subperiod OOS Summary",
        "",
        crisis.to_markdown(index=False),
        "",
        "## Fold Audit",
        "",
        fold_audit.head(20).to_markdown(index=False),
        "",
        "## Interpretation",
        "",
        "The key comparison is not whether walk-forward beats the full-sample lookahead version. It should normally degrade. The relevant question is whether the walk-forward overlay preserves meaningful drawdown and risk-adjusted-performance benefits versus static portfolios after execution lag and transaction costs.",
    ]
    return "\n".join(lines)


def run_stage24(
    stage7_dir: str | Path = "outputs/stage7_mixed_frequency",
    stage9_dir: str | Path = "outputs/stage9_simplified",
    output_dir: str | Path = "outputs/stage24_walkforward_oos_overlay",
) -> dict[str, Path]:
    stage7_dir = Path(stage7_dir)
    stage9_dir = Path(stage9_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    config = Stage12Config(n_states=2)

    LOGGER.info("Loading availability-aware axes and returns.")
    axes, returns = load_stage12_inputs(stage7_dir, stage9_dir)
    returns = returns.reindex(columns=[c for c in ASSETS if c in returns.columns])

    LOGGER.info("Building expanding walk-forward HMM signals.")
    wf_signals, fold_audit = expanding_walkforward_signals(axes, config)
    full_signals = _full_sample_signals(axes, config)

    LOGGER.info("Running OOS static, full-sample, and walk-forward overlay backtests.")
    weights, backtests = run_oos_allocations(returns, wf_signals, full_signals, config, OOS_START)
    performance = performance_metrics(backtests)
    deltas = benchmark_deltas(performance)
    degradation = oos_degradation(performance)
    stability = signal_stability(wf_signals)
    crisis = crisis_oos_summary(backtests, weights)
    figures = make_figures(backtests, wf_signals, output_dir)

    paths = {
        "config": output_dir / "stage24_config.json",
        "walkforward_signals": output_dir / "stage24_walkforward_regime_signals.csv",
        "fold_audit": output_dir / "stage24_walkforward_fold_audit.csv",
        "weights": output_dir / "stage24_oos_overlay_weights.csv",
        "backtests": output_dir / "stage24_oos_backtest_timeseries.csv",
        "performance": output_dir / "stage24_oos_performance_summary.csv",
        "benchmark_deltas": output_dir / "stage24_oos_benchmark_deltas.csv",
        "degradation": output_dir / "stage24_fullsample_degradation.csv",
        "signal_stability": output_dir / "stage24_signal_stability.csv",
        "crisis": output_dir / "stage24_oos_crisis_summary.csv",
        "report": output_dir / "stage24_walkforward_oos_overlay_report.md",
        **figures,
    }
    paths["config"].write_text(
        json.dumps(
            {
                "initial_train_end": INITIAL_TRAIN_END,
                "oos_start": OOS_START,
                "refit_frequency": REFIT_FREQUENCY,
                "hmm_states": config.n_states,
                "transaction_cost_bps": config.transaction_cost_bps,
                "overlay_specs": OVERLAY_SPECS,
                "purpose": "walk-forward OOS validation, not parameter tuning",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    _save_table(wf_signals, paths["walkforward_signals"])
    _save_table(fold_audit, paths["fold_audit"])
    _save_table(pd.concat(weights, names=["model", "date"]).reset_index(), paths["weights"])
    _save_table(pd.concat(backtests, names=["model", "date"]).reset_index(), paths["backtests"])
    _save_table(performance, paths["performance"])
    _save_table(deltas, paths["benchmark_deltas"])
    _save_table(degradation, paths["degradation"])
    _save_table(stability, paths["signal_stability"])
    _save_table(crisis, paths["crisis"])
    paths["report"].write_text(build_report(performance, deltas, degradation, stability, fold_audit, crisis), encoding="utf-8")
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage7-dir", default="outputs/stage7_mixed_frequency")
    parser.add_argument("--stage9-dir", default="outputs/stage9_simplified")
    parser.add_argument("--output-dir", default="outputs/stage24_walkforward_oos_overlay")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    paths = run_stage24(args.stage7_dir, args.stage9_dir, args.output_dir)
    print("Stage 24 outputs:")
    for name, path in paths.items():
        print(f"- {name}: {path}")


if __name__ == "__main__":
    main()
