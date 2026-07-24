"""Run Stage 25: diagnose why walk-forward OOS overlay performance degraded."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


OVERLAY_MODELS = [
    "walkforward_two_state_overlay_mild",
    "walkforward_two_state_overlay_balanced",
    "walkforward_two_state_overlay_defensive",
]
FULLSAMPLE_MODELS = [
    "fullsample_two_state_overlay_mild",
    "fullsample_two_state_overlay_balanced",
    "fullsample_two_state_overlay_defensive",
]
STATIC_BENCHMARK = "static_diversified"
ASSETS = ["SPY", "TLT", "GLD", "DBC", "CASH"]


def _save_table(df: pd.DataFrame, path: Path, index: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=index, encoding="utf-8-sig")


def load_stage24(stage24_dir: Path) -> dict[str, pd.DataFrame]:
    return {
        "signals": pd.read_csv(stage24_dir / "stage24_walkforward_regime_signals.csv", parse_dates=["date", "train_start", "train_end"]),
        "weights": pd.read_csv(stage24_dir / "stage24_oos_overlay_weights.csv", parse_dates=["date"]),
        "backtests": pd.read_csv(stage24_dir / "stage24_oos_backtest_timeseries.csv", parse_dates=["date"]),
        "folds": pd.read_csv(stage24_dir / "stage24_walkforward_fold_audit.csv", parse_dates=["train_start", "train_end", "test_start", "test_end"]),
        "performance": pd.read_csv(stage24_dir / "stage24_oos_performance_summary.csv"),
    }


def signal_jump_diagnostics(signals: pd.DataFrame) -> pd.DataFrame:
    s = signals.sort_values("date").copy()
    s["risk_prob_change"] = s["risk_probability"].diff().abs()
    s["regime_flip"] = s["regime"].ne(s["regime"].shift()).fillna(False)
    s["new_fold"] = s["fold"].ne(s["fold"].shift()).fillna(False)
    rows = []
    for label, group in {
        "all_days": s,
        "refit_boundary_days": s[s["new_fold"]],
        "within_fold_days": s[~s["new_fold"]],
        "regime_flip_days": s[s["regime_flip"]],
    }.items():
        if group.empty:
            continue
        rows.append(
            {
                "sample": label,
                "days": len(group),
                "mean_abs_risk_prob_change": group["risk_prob_change"].mean(),
                "median_abs_risk_prob_change": group["risk_prob_change"].median(),
                "p95_abs_risk_prob_change": group["risk_prob_change"].quantile(0.95),
                "jump_gt_25pct_count": int((group["risk_prob_change"] > 0.25).sum()),
                "jump_gt_50pct_count": int((group["risk_prob_change"] > 0.50).sum()),
                "regime_flip_count": int(group["regime_flip"].sum()),
                "mean_risk_probability": group["risk_probability"].mean(),
            }
        )
    return pd.DataFrame(rows)


def turnover_decomposition(backtests: pd.DataFrame, weights: pd.DataFrame, signals: pd.DataFrame) -> pd.DataFrame:
    sig = signals[["date", "fold", "regime", "risk_probability"]].copy()
    sig["new_fold"] = sig["fold"].ne(sig["fold"].shift()).fillna(False)
    sig["regime_flip"] = sig["regime"].ne(sig["regime"].shift()).fillna(False)
    rows = []
    bt = backtests.merge(sig[["date", "new_fold", "regime_flip"]], on="date", how="left")
    for model, group in bt.groupby("model"):
        if model not in OVERLAY_MODELS + FULLSAMPLE_MODELS:
            continue
        turnover = group["turnover"].fillna(0.0)
        cost = turnover * 2.0 / 10000
        rows.append(
            {
                "model": model,
                "avg_turnover": turnover.mean(),
                "total_turnover": turnover.sum(),
                "estimated_total_cost_return_drag": cost.sum(),
                "avg_cost_drag_per_day": cost.mean(),
                "turnover_on_refit_days": group.loc[group["new_fold"].fillna(False), "turnover"].sum(),
                "turnover_on_regime_flip_days": group.loc[group["regime_flip"].fillna(False), "turnover"].sum(),
                "share_turnover_refit_days": group.loc[group["new_fold"].fillna(False), "turnover"].sum() / turnover.sum() if turnover.sum() > 0 else np.nan,
                "share_turnover_regime_flip_days": group.loc[group["regime_flip"].fillna(False), "turnover"].sum() / turnover.sum() if turnover.sum() > 0 else np.nan,
                "days_turnover_gt_10pct": int((turnover > 0.10).sum()),
                "days_turnover_gt_25pct": int((turnover > 0.25).sum()),
            }
        )
    return pd.DataFrame(rows)


def fullsample_signal_proxy(weights: pd.DataFrame) -> pd.DataFrame:
    # Recover p_stress from the balanced full-sample SPY blend:
    # SPY = 0.45 + p * (0.20 - 0.45)
    w = weights[weights["model"].eq("fullsample_two_state_overlay_balanced")][["date", "SPY"]].copy()
    w["fullsample_risk_probability_proxy"] = ((0.45 - w["SPY"]) / 0.25).clip(0.0, 1.0)
    return w[["date", "fullsample_risk_probability_proxy"]]


def signal_alignment(signals: pd.DataFrame, weights: pd.DataFrame) -> pd.DataFrame:
    wf = signals[["date", "risk_probability", "regime"]].rename(columns={"risk_probability": "walkforward_risk_probability"})
    fs = fullsample_signal_proxy(weights)
    merged = wf.merge(fs, on="date", how="inner").sort_values("date")
    merged["abs_probability_gap"] = (merged["walkforward_risk_probability"] - merged["fullsample_risk_probability_proxy"]).abs()
    merged["same_high_stress_flag"] = (merged["walkforward_risk_probability"] > 0.5).eq(
        merged["fullsample_risk_probability_proxy"] > 0.5
    )
    summary = pd.DataFrame(
        [
            {
                "days": len(merged),
                "probability_correlation": merged["walkforward_risk_probability"].corr(merged["fullsample_risk_probability_proxy"]),
                "mean_abs_probability_gap": merged["abs_probability_gap"].mean(),
                "median_abs_probability_gap": merged["abs_probability_gap"].median(),
                "p95_abs_probability_gap": merged["abs_probability_gap"].quantile(0.95),
                "high_stress_flag_agreement": merged["same_high_stress_flag"].mean(),
                "walkforward_high_stress_days": int((merged["walkforward_risk_probability"] > 0.5).sum()),
                "fullsample_high_stress_days": int((merged["fullsample_risk_probability_proxy"] > 0.5).sum()),
            }
        ]
    )
    return summary, merged


def crisis_timing(signals: pd.DataFrame) -> pd.DataFrame:
    windows = {
        "covid": ("2020-02-01", "2020-06-30"),
        "inflation_shock": ("2022-01-01", "2022-12-31"),
        "recent": ("2023-01-01", "2026-05-15"),
    }
    rows = []
    s = signals.sort_values("date")
    for name, (start, end) in windows.items():
        sub = s[(s["date"] >= pd.Timestamp(start)) & (s["date"] <= pd.Timestamp(end))]
        if sub.empty:
            continue
        high = sub[sub["risk_probability"] > 0.5]
        rows.append(
            {
                "window": name,
                "start": start,
                "end": end,
                "days": len(sub),
                "mean_risk_probability": sub["risk_probability"].mean(),
                "median_risk_probability": sub["risk_probability"].median(),
                "high_stress_day_share": len(high) / len(sub),
                "first_high_stress_date": high["date"].min() if len(high) else pd.NaT,
                "last_high_stress_date": high["date"].max() if len(high) else pd.NaT,
                "risk_probability_at_window_start": sub.iloc[0]["risk_probability"],
                "max_risk_probability": sub["risk_probability"].max(),
            }
        )
    return pd.DataFrame(rows)


def benchmark_strength(performance: pd.DataFrame, weights: pd.DataFrame) -> pd.DataFrame:
    perf = performance.set_index("model")
    static = weights[weights["model"].eq(STATIC_BENCHMARK)]
    rows = [
        {
            "benchmark": STATIC_BENCHMARK,
            "CAGR": perf.loc[STATIC_BENCHMARK, "CAGR"],
            "Sharpe": perf.loc[STATIC_BENCHMARK, "Sharpe"],
            "max_drawdown": perf.loc[STATIC_BENCHMARK, "max_drawdown"],
            "Calmar": perf.loc[STATIC_BENCHMARK, "Calmar"],
            "avg_SPY": static["SPY"].mean(),
            "avg_defensive_plus_cash": static[["TLT", "GLD", "CASH"]].sum(axis=1).mean(),
            "avg_non_equity": static[["TLT", "GLD", "DBC", "CASH"]].sum(axis=1).mean(),
        }
    ]
    return pd.DataFrame(rows)


def improvement_options() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "option": "A_fixed_hmm_update_only",
                "description": "Fit the 2-state HMM on a long initial sample, freeze emission/state mapping, and update posterior without quarterly refit.",
                "targets_failure_mode": "state boundary instability",
                "overfit_risk": "low",
                "next_test_priority": 1,
            },
            {
                "option": "B_annual_refit",
                "description": "Refit annually instead of quarterly to reduce boundary churn.",
                "targets_failure_mode": "refit-induced posterior jumps",
                "overfit_risk": "low",
                "next_test_priority": 2,
            },
            {
                "option": "C_posterior_ewma",
                "description": "Apply EWMA smoothing to walk-forward p_stress before mapping to weights.",
                "targets_failure_mode": "daily posterior jumps and turnover",
                "overfit_risk": "medium",
                "next_test_priority": 3,
            },
            {
                "option": "D_activation_hysteresis",
                "description": "Require p_stress to exceed an activation threshold and fall below a lower deactivation threshold.",
                "targets_failure_mode": "short-lived regime activations",
                "overfit_risk": "medium",
                "next_test_priority": 4,
            },
            {
                "option": "E_weight_change_cap",
                "description": "Limit daily target weight change to reduce execution churn.",
                "targets_failure_mode": "turnover drag",
                "overfit_risk": "medium",
                "next_test_priority": 5,
            },
            {
                "option": "F_guardrail_only",
                "description": "Use HMM only to raise a cash floor or cap SPY in high stress, rather than continuously blending all weights.",
                "targets_failure_mode": "direct allocation mismatch",
                "overfit_risk": "low",
                "next_test_priority": 6,
            },
        ]
    )


def make_figures(alignment_series: pd.DataFrame, signals: pd.DataFrame, output_dir: Path) -> dict[str, Path]:
    figure_dir = output_dir / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(alignment_series["date"], alignment_series["walkforward_risk_probability"], label="walk-forward", linewidth=1)
    ax.plot(alignment_series["date"], alignment_series["fullsample_risk_probability_proxy"], label="full-sample proxy", linewidth=1)
    ax.set_title("Stage 25 walk-forward vs full-sample stress probability")
    ax.set_ylim(-0.02, 1.02)
    ax.legend()
    fig.tight_layout()
    alignment_path = figure_dir / "stage25_signal_alignment.png"
    fig.savefig(alignment_path, dpi=150)
    plt.close(fig)

    s = signals.sort_values("date").copy()
    s["risk_prob_change"] = s["risk_probability"].diff().abs()
    fig, ax = plt.subplots(figsize=(8, 4))
    ax.hist(s["risk_prob_change"].dropna(), bins=50, color="tab:blue", alpha=0.8)
    ax.set_title("Stage 25 walk-forward posterior jump distribution")
    ax.set_xlabel("|Delta p_stress|")
    ax.set_ylabel("Days")
    fig.tight_layout()
    jump_path = figure_dir / "stage25_posterior_jump_histogram.png"
    fig.savefig(jump_path, dpi=150)
    plt.close(fig)

    return {"signal_alignment_figure": alignment_path, "posterior_jump_histogram": jump_path}


def build_report(
    jump_diag: pd.DataFrame,
    turnover: pd.DataFrame,
    alignment: pd.DataFrame,
    crisis: pd.DataFrame,
    benchmark: pd.DataFrame,
    options: pd.DataFrame,
) -> str:
    lines = [
        "# Stage 25 OOS Failure Diagnostics",
        "",
        "## Purpose",
        "",
        "Stage 25 diagnoses why the Stage 24 walk-forward overlay failed to preserve the full-sample advantage versus static diversified allocation. It does not introduce a new tuned model.",
        "",
        "## Rebalancing Clarification",
        "",
        "The Stage 24 HMM is refit quarterly, but portfolio targets are recomputed daily from the current walk-forward posterior. Execution occurs with the existing one-period lag. Therefore realized rebalancing is event/posterior-driven on daily data, not fixed monthly or quarterly rebalancing.",
        "",
        "## Signal Jump Diagnostics",
        "",
        jump_diag.to_markdown(index=False),
        "",
        "## Turnover Decomposition",
        "",
        turnover.to_markdown(index=False),
        "",
        "## Walk-Forward vs Full-Sample Signal Alignment",
        "",
        alignment.to_markdown(index=False),
        "",
        "## Crisis Timing",
        "",
        crisis.to_markdown(index=False),
        "",
        "## Benchmark Strength",
        "",
        benchmark.to_markdown(index=False),
        "",
        "## Improvement Candidates",
        "",
        options.to_markdown(index=False),
        "",
        "## Interpretation",
        "",
        "The main diagnostic question is whether OOS failure comes from the regime concept itself, the quarterly refit procedure, or the direct daily mapping from posterior probability to portfolio weights. If instability and turnover are concentrated around posterior jumps/refit boundaries, the next stage should test lower-frequency or frozen-parameter variants before changing the economic thesis.",
    ]
    return "\n".join(lines)


def run_stage25(
    stage24_dir: str | Path = "outputs/stage24_walkforward_oos_overlay",
    output_dir: str | Path = "outputs/stage25_oos_failure_diagnostics",
) -> dict[str, Path]:
    stage24_dir = Path(stage24_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    data = load_stage24(stage24_dir)
    jump_diag = signal_jump_diagnostics(data["signals"])
    turnover = turnover_decomposition(data["backtests"], data["weights"], data["signals"])
    alignment, alignment_series = signal_alignment(data["signals"], data["weights"])
    crisis = crisis_timing(data["signals"])
    benchmark = benchmark_strength(data["performance"], data["weights"])
    options = improvement_options()
    figures = make_figures(alignment_series, data["signals"], output_dir)

    paths = {
        "config": output_dir / "stage25_config.json",
        "signal_jumps": output_dir / "stage25_signal_jump_diagnostics.csv",
        "turnover_decomposition": output_dir / "stage25_turnover_decomposition.csv",
        "signal_alignment_summary": output_dir / "stage25_signal_alignment_summary.csv",
        "signal_alignment_series": output_dir / "stage25_signal_alignment_series.csv",
        "crisis_timing": output_dir / "stage25_crisis_timing.csv",
        "benchmark_strength": output_dir / "stage25_benchmark_strength.csv",
        "improvement_options": output_dir / "stage25_improvement_options.csv",
        "report": output_dir / "stage25_oos_failure_diagnostics_report.md",
        **figures,
    }
    paths["config"].write_text(
        json.dumps(
            {
                "source_stage": str(stage24_dir),
                "scope": "failure diagnostics only, no tuned replacement model",
                "rebalancing_clarification": "quarterly HMM refit, daily posterior-driven target weights, one-period execution lag",
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    _save_table(jump_diag, paths["signal_jumps"])
    _save_table(turnover, paths["turnover_decomposition"])
    _save_table(alignment, paths["signal_alignment_summary"])
    _save_table(alignment_series, paths["signal_alignment_series"])
    _save_table(crisis, paths["crisis_timing"])
    _save_table(benchmark, paths["benchmark_strength"])
    _save_table(options, paths["improvement_options"])
    paths["report"].write_text(build_report(jump_diag, turnover, alignment, crisis, benchmark, options), encoding="utf-8")
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage24-dir", default="outputs/stage24_walkforward_oos_overlay")
    parser.add_argument("--output-dir", default="outputs/stage25_oos_failure_diagnostics")
    args = parser.parse_args()
    paths = run_stage25(args.stage24_dir, args.output_dir)
    print("Stage 25 outputs:")
    for name, path in paths.items():
        print(f"- {name}: {path}")


if __name__ == "__main__":
    main()
