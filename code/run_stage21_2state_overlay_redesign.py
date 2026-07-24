"""Run Stage 21: redesign the allocation overlay around canonical 2-state HMM probabilities.

The stage intentionally avoids the legacy 3-state-style overlay formula. It uses
the 2-state stress posterior directly to blend between pre-declared base and
stress portfolios.
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

from stage12_hmm_comparison import (
    Stage12Config,
    backtest_weights,
    baseline_hmm,
    load_stage12_inputs,
    performance_metrics,
    subperiod_metrics,
)


LOGGER = logging.getLogger(__name__)

ASSETS = ["SPY", "TLT", "GLD", "DBC", "CASH"]

STATIC_PORTFOLIOS = {
    "static_60_40_spy_tlt": {"SPY": 0.60, "TLT": 0.40, "GLD": 0.00, "DBC": 0.00, "CASH": 0.00},
    "static_equal_weight": {"SPY": 0.20, "TLT": 0.20, "GLD": 0.20, "DBC": 0.20, "CASH": 0.20},
    "static_diversified": {"SPY": 0.45, "TLT": 0.25, "GLD": 0.15, "DBC": 0.10, "CASH": 0.05},
}

OVERLAY_SPECS = {
    "two_state_overlay_mild": {
        "description": "Light stress response; intended to test whether regime information adds value without materially changing the policy portfolio.",
        "base": {"SPY": 0.45, "TLT": 0.25, "GLD": 0.15, "DBC": 0.10, "CASH": 0.05},
        "stress": {"SPY": 0.30, "TLT": 0.30, "GLD": 0.17, "DBC": 0.08, "CASH": 0.15},
    },
    "two_state_overlay_balanced": {
        "description": "Balanced risk overlay; equity risk is cut meaningfully while defensive ballast and cash rise.",
        "base": {"SPY": 0.45, "TLT": 0.25, "GLD": 0.15, "DBC": 0.10, "CASH": 0.05},
        "stress": {"SPY": 0.20, "TLT": 0.30, "GLD": 0.20, "DBC": 0.07, "CASH": 0.23},
    },
    "two_state_overlay_defensive": {
        "description": "High-conviction drawdown-control variant; useful as an upper bound on defensive behavior, not as a tuned optimum.",
        "base": {"SPY": 0.45, "TLT": 0.25, "GLD": 0.15, "DBC": 0.10, "CASH": 0.05},
        "stress": {"SPY": 0.12, "TLT": 0.32, "GLD": 0.22, "DBC": 0.04, "CASH": 0.30},
    },
}


def _normalize_weights(weights: dict[str, float], columns: pd.Index) -> pd.Series:
    out = pd.Series(weights, dtype=float).reindex(columns).fillna(0.0)
    total = out.sum()
    if total <= 0:
        raise ValueError("Portfolio weights must have positive total weight.")
    return out / total


def _save_table(df: pd.DataFrame, path: Path, index: bool = False) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=index, encoding="utf-8-sig")


def static_weights(returns: pd.DataFrame, spec: dict[str, float]) -> pd.DataFrame:
    row = _normalize_weights(spec, returns.columns)
    return pd.DataFrame(np.tile(row.to_numpy(), (len(returns), 1)), index=returns.index, columns=returns.columns)


def probability_blend_weights(returns: pd.DataFrame, signals: pd.DataFrame, spec: dict) -> pd.DataFrame:
    sig = signals.set_index("date").reindex(returns.index).ffill()
    p_stress = sig["risk_probability"].clip(0.0, 1.0).fillna(0.0)
    base = _normalize_weights(spec["base"], returns.columns)
    stress = _normalize_weights(spec["stress"], returns.columns)
    rows = []
    for date, p in p_stress.items():
        target = (1.0 - float(p)) * base + float(p) * stress
        rows.append(target.rename(date))
    return pd.DataFrame(rows)


def overlay_diagnostics(signals: pd.DataFrame, weights: dict[str, pd.DataFrame]) -> pd.DataFrame:
    risk = signals.set_index("date")["risk_probability"].sort_index()
    rows = []
    for name, w in weights.items():
        aligned_risk = risk.reindex(w.index).ffill()
        dw = w.diff().abs().sum(axis=1).fillna(0.0)
        spy_corr = np.nan
        cash_corr = np.nan
        if "SPY" in w and w["SPY"].std(ddof=1) > 1e-12:
            spy_corr = float(aligned_risk.corr(w["SPY"]))
        if "CASH" in w and w["CASH"].std(ddof=1) > 1e-12:
            cash_corr = float(aligned_risk.corr(w["CASH"]))
        rows.append(
            {
                "model": name,
                "avg_daily_turnover_proxy": float(dw.mean()),
                "median_daily_turnover_proxy": float(dw.median()),
                "max_daily_turnover_proxy": float(dw.max()),
                "avg_spy_weight": float(w.get("SPY", pd.Series(index=w.index, dtype=float)).mean()),
                "min_spy_weight": float(w.get("SPY", pd.Series(index=w.index, dtype=float)).min()),
                "max_spy_weight": float(w.get("SPY", pd.Series(index=w.index, dtype=float)).max()),
                "avg_cash_weight": float(w.get("CASH", pd.Series(index=w.index, dtype=float)).mean()),
                "max_cash_weight": float(w.get("CASH", pd.Series(index=w.index, dtype=float)).max()),
                "stress_prob_corr_with_spy": spy_corr,
                "stress_prob_corr_with_cash": cash_corr,
            }
        )
    return pd.DataFrame(rows)


def crisis_exposure(weights: dict[str, pd.DataFrame], backtests: dict[str, pd.DataFrame]) -> pd.DataFrame:
    periods = {
        "gfc": ("2008-01-01", "2009-06-30"),
        "covid": ("2020-02-01", "2020-06-30"),
        "inflation_shock": ("2022-01-01", "2022-12-31"),
        "recent": ("2023-01-01", "2026-05-15"),
    }
    rows = []
    for name, w in weights.items():
        bt = backtests[name]
        for period, (start, end) in periods.items():
            ww = w.loc[(w.index >= start) & (w.index <= end)]
            bb = bt.loc[(bt.index >= start) & (bt.index <= end)]
            if len(ww) < 20 or len(bb) < 20:
                continue
            rows.append(
                {
                    "model": name,
                    "period": period,
                    "avg_SPY": float(ww["SPY"].mean()) if "SPY" in ww else np.nan,
                    "avg_TLT": float(ww["TLT"].mean()) if "TLT" in ww else np.nan,
                    "avg_GLD": float(ww["GLD"].mean()) if "GLD" in ww else np.nan,
                    "avg_DBC": float(ww["DBC"].mean()) if "DBC" in ww else np.nan,
                    "avg_CASH": float(ww["CASH"].mean()) if "CASH" in ww else np.nan,
                    "period_return": float((1.0 + bb["net_return"]).prod() - 1.0),
                    "period_max_drawdown": float(bb["drawdown"].min()),
                    "avg_turnover": float(bb["turnover"].mean()),
                }
            )
    return pd.DataFrame(rows)


def build_figures(backtests: dict[str, pd.DataFrame], weights: dict[str, pd.DataFrame], output_dir: Path) -> dict[str, Path]:
    figure_dir = output_dir / "figures"
    figure_dir.mkdir(parents=True, exist_ok=True)

    fig, ax = plt.subplots(figsize=(10, 5))
    for name, bt in backtests.items():
        if name in {"static_diversified", "two_state_overlay_balanced", "two_state_overlay_defensive"}:
            ax.plot(bt.index, bt["equity_curve"], label=name)
    ax.set_title("Stage 21 equity curves")
    ax.set_ylabel("Growth of $1")
    ax.legend(fontsize=8)
    fig.tight_layout()
    equity_path = figure_dir / "stage21_equity_curves.png"
    fig.savefig(equity_path, dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(10, 5))
    for name, w in weights.items():
        if name.startswith("two_state_overlay"):
            ax.plot(w.index, w["SPY"], label=f"{name} SPY")
    ax.set_title("Stage 21 SPY exposure by 2-state overlay variant")
    ax.set_ylabel("SPY weight")
    ax.legend(fontsize=8)
    fig.tight_layout()
    spy_path = figure_dir / "stage21_spy_exposure.png"
    fig.savefig(spy_path, dpi=150)
    plt.close(fig)

    return {"equity_curves": equity_path, "spy_exposure": spy_path}


def build_report(
    signals: pd.DataFrame,
    performance: pd.DataFrame,
    diagnostics: pd.DataFrame,
    crisis: pd.DataFrame,
    legacy_performance: pd.DataFrame | None,
) -> str:
    risk = signals["risk_probability"]
    lines = [
        "# Stage 21 2-State Regime-Aware Overlay Redesign",
        "",
        "## Purpose",
        "",
        "This stage replaces the legacy 3-state-style overlay formula with a simple 2-state posterior-probability allocation rule. The HMM supplies only `p_stress`; allocation is a transparent blend between pre-declared base and stress portfolios.",
        "",
        "## Stress Probability",
        "",
        f"Stress probability range: min `{risk.min():.4f}`, median `{risk.median():.4f}`, mean `{risk.mean():.4f}`, max `{risk.max():.4f}`.",
        "",
        "## Overlay Specifications",
        "",
        pd.DataFrame(
            [
                {"model": name, "portfolio": "base", **spec["base"]}
                for name, spec in OVERLAY_SPECS.items()
            ]
            + [
                {"model": name, "portfolio": "stress", **spec["stress"]}
                for name, spec in OVERLAY_SPECS.items()
            ]
        ).to_markdown(index=False),
        "",
        "## Performance Summary",
        "",
        performance.to_markdown(index=False),
        "",
        "## Overlay Diagnostics",
        "",
        diagnostics.to_markdown(index=False),
        "",
        "## Crisis Exposure and Drawdown",
        "",
        crisis.to_markdown(index=False),
        "",
        "## Legacy Context",
        "",
        legacy_performance.to_markdown(index=False) if legacy_performance is not None else "Legacy Stage 14 performance file was not found.",
        "",
        "## Interpretation",
        "",
        "The three stress portfolios are intentionally pre-declared policy variants, not optimized weights. Stage 21 should be read as a clean prototype: if these broad variants do not improve drawdown or tail behavior versus static portfolios, the HMM regime signal is not yet useful as an implementable overlay.",
        "",
        "The next step should be parameter robustness around these policy variants, not selecting the single best in-sample result.",
    ]
    return "\n".join(lines)


def run_stage21(
    stage7_dir: str | Path = "outputs/stage7_mixed_frequency",
    stage9_dir: str | Path = "outputs/stage9_simplified",
    stage14_dir: str | Path = "outputs/stage14_2state_rebuild",
    output_dir: str | Path = "outputs/stage21_2state_overlay_redesign",
) -> dict[str, Path]:
    stage7_dir = Path(stage7_dir)
    stage9_dir = Path(stage9_dir)
    stage14_dir = Path(stage14_dir)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    config = Stage12Config(n_states=2)

    LOGGER.info("Loading Stage 7/9 point-in-time inputs.")
    axes, returns = load_stage12_inputs(stage7_dir, stage9_dir)
    returns = returns.reindex(columns=[c for c in ASSETS if c in returns.columns])

    LOGGER.info("Fitting canonical 2-state HMM and extracting stress posterior.")
    _, signals, _ = baseline_hmm(axes, config)
    signals["risk_probability"] = signals["prob_regime_1"].astype(float)

    weights = {}
    for name, spec in STATIC_PORTFOLIOS.items():
        weights[name] = static_weights(returns, spec)
    for name, spec in OVERLAY_SPECS.items():
        weights[name] = probability_blend_weights(returns, signals, spec)

    backtests = {name: backtest_weights(returns, w, config.transaction_cost_bps) for name, w in weights.items()}
    performance = performance_metrics(backtests)
    subperiods = subperiod_metrics(backtests)
    diagnostics = overlay_diagnostics(signals, weights)
    crisis = crisis_exposure(weights, backtests)
    figures = build_figures(backtests, weights, output_dir)

    legacy_path = stage14_dir / "two_state_model_performance_summary.csv"
    legacy = pd.read_csv(legacy_path) if legacy_path.exists() else None

    paths = {
        "config": output_dir / "stage21_config.json",
        "signals": output_dir / "stage21_two_state_regime_signals.csv",
        "weights": output_dir / "stage21_overlay_weights.csv",
        "backtests": output_dir / "stage21_backtest_timeseries.csv",
        "performance": output_dir / "stage21_performance_summary.csv",
        "subperiods": output_dir / "stage21_subperiod_summary.csv",
        "diagnostics": output_dir / "stage21_overlay_diagnostics.csv",
        "crisis": output_dir / "stage21_crisis_exposure_summary.csv",
        "report": output_dir / "stage21_2state_overlay_redesign_report.md",
        **figures,
    }

    paths["config"].write_text(
        json.dumps(
            {
                "method": "transparent posterior blend between pre-declared base and stress portfolios",
                "transaction_cost_bps": config.transaction_cost_bps,
                "hmm_states": 2,
                "static_portfolios": STATIC_PORTFOLIOS,
                "overlay_specs": OVERLAY_SPECS,
                "legacy_overlay_reused": False,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    _save_table(signals, paths["signals"])
    _save_table(pd.concat(weights, names=["model", "date"]).reset_index(), paths["weights"])
    _save_table(pd.concat(backtests, names=["model", "date"]).reset_index(), paths["backtests"])
    _save_table(performance, paths["performance"])
    _save_table(subperiods, paths["subperiods"])
    _save_table(diagnostics, paths["diagnostics"])
    _save_table(crisis, paths["crisis"])
    paths["report"].write_text(build_report(signals, performance, diagnostics, crisis, legacy), encoding="utf-8")
    return paths


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--stage7-dir", default="outputs/stage7_mixed_frequency")
    parser.add_argument("--stage9-dir", default="outputs/stage9_simplified")
    parser.add_argument("--stage14-dir", default="outputs/stage14_2state_rebuild")
    parser.add_argument("--output-dir", default="outputs/stage21_2state_overlay_redesign")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s - %(message)s")
    paths = run_stage21(args.stage7_dir, args.stage9_dir, args.stage14_dir, args.output_dir)
    print("Stage 21 outputs:")
    for name, path in paths.items():
        print(f"- {name}: {path}")


if __name__ == "__main__":
    main()
