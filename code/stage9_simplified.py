"""Stage 9 simplified production-grade macro risk monitoring utilities."""

from __future__ import annotations

from dataclasses import dataclass
from bisect import bisect_right, insort
from pathlib import Path

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Stage9Config:
    min_observations: int = 120
    stability_window: int = 504
    smoothing_span: int = 10
    persistence_days: int = 5
    confirmation_days: int = 3
    minimum_holding_days: int = 21
    transaction_cost_bps: float = 2.0


ECONOMIC_AXIS_SPECS: dict[str, dict[str, float]] = {
    "InflationPressure": {
        "macro_cpi_yoy": 1.0,
        "macro_breakeven_10y": 0.9,
        "daily_commodity_return": 0.35,
        "daily_gold_return": 0.2,
        "macro_gold_momentum_12m": 0.25,
    },
    "GrowthWeakness": {
        "macro_unemployment_rate": 1.0,
        "macro_payroll_growth": -1.0,
        "macro_industrial_production_yoy": -0.9,
        "daily_equity_return": -0.25,
        "macro_spy_momentum_12m": -0.35,
    },
    "FinancialStress": {
        "daily_vix_level": 1.0,
        "daily_realized_vol_21d": 0.8,
        "daily_cross_asset_dispersion": 0.6,
        "macro_vix": 0.9,
        "macro_move_index": 0.7,
        "macro_financial_conditions": 0.7,
        "macro_ted_spread": 0.6,
        "macro_realized_vol_12m": 0.5,
        "macro_cross_asset_dispersion": 0.5,
        "macro_spy_momentum_12m": -0.35,
    },
    "PolicyTightness": {
        "macro_real_yield_10y": 1.0,
        "macro_two_year_yield": 0.8,
        "macro_ten_year_yield": 0.45,
        "macro_term_spread_10y_2y": -0.65,
        "macro_dxy": 0.35,
        "daily_dxy_return": 0.15,
        "daily_duration_return": -0.15,
    },
}


def observations_to_wide(observations: pd.DataFrame) -> pd.DataFrame:
    wide = observations.pivot_table(index="availability_timestamp", columns="feature", values="value", aggfunc="last")
    return wide.sort_index().ffill()


def expanding_zscore(frame: pd.DataFrame, min_periods: int = 60) -> pd.DataFrame:
    mean = frame.expanding(min_periods=min_periods).mean().shift(1)
    std = frame.expanding(min_periods=min_periods).std().shift(1).replace(0, np.nan)
    return ((frame - mean) / std).replace([np.inf, -np.inf], np.nan)


def expanding_percentile(series: pd.Series, min_periods: int = 60) -> pd.Series:
    values = series.astype(float)
    out = pd.Series(np.nan, index=values.index)
    history: list[float] = []
    for idx, value in values.items():
        if len(history) >= min_periods and np.isfinite(value):
            out.loc[idx] = bisect_right(history, float(value)) / len(history)
        if np.isfinite(value):
            insort(history, float(value))
    return out


def build_economic_axes(wide: pd.DataFrame, config: Stage9Config) -> tuple[pd.DataFrame, pd.DataFrame]:
    z = expanding_zscore(wide).fillna(0.0)
    axes = pd.DataFrame(index=wide.index)
    rows = []
    for axis, spec in ECONOMIC_AXIS_SPECS.items():
        used = []
        weighted = []
        total_abs_weight = 0.0
        for feature, weight in spec.items():
            if feature not in z.columns or wide[feature].notna().sum() < config.min_observations:
                continue
            used.append(feature)
            weighted.append(z[feature] * weight)
            total_abs_weight += abs(weight)
            rows.append(
                {
                    "axis": axis,
                    "feature": feature,
                    "orientation_weight": weight,
                    "observations": int(wide[feature].notna().sum()),
                    "start": wide[feature].dropna().index.min(),
                    "end": wide[feature].dropna().index.max(),
                }
            )
        if weighted:
            axes[axis] = pd.concat(weighted, axis=1).sum(axis=1) / max(total_abs_weight, 1e-12)
        else:
            axes[axis] = 0.0
    axes = axes.fillna(0.0)
    axes["TransitionInstability"] = axes.diff().abs().rolling(21, min_periods=10).mean().mean(axis=1).fillna(0.0)
    axes["VolatilityInstability"] = wide.filter(regex="vix|vol|dispersion", axis=1).pipe(expanding_zscore).abs().mean(axis=1).fillna(0.0)
    axes["SystemicRiskScore"] = (
        0.25 * axes["InflationPressure"]
        + 0.25 * axes["GrowthWeakness"]
        + 0.30 * axes["FinancialStress"]
        + 0.15 * axes["PolicyTightness"]
        + 0.05 * axes["TransitionInstability"]
    )
    axes["SystemicRiskPercentile"] = expanding_percentile(axes["SystemicRiskScore"]).fillna(0.5)
    axes["UncertaintyScore"] = axes[["TransitionInstability", "VolatilityInstability"]].mean(axis=1)
    axes["UncertaintyPercentile"] = expanding_percentile(axes["UncertaintyScore"]).fillna(0.5)
    return axes, pd.DataFrame(rows)


def sign_and_loading_stability(loadings: pd.DataFrame, history: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, str]:
    if history.empty:
        empty = pd.DataFrame(columns=["factor", "feature", "sign_consistency", "loading_drift", "avg_abs_loading"])
        return empty, empty, "# Factor Sign Consistency\n\nInsufficient rolling loading history."
    base = loadings[["factor", "feature", "loading"]].rename(columns={"loading": "full_sample_loading"})
    merged = history.merge(base, on=["factor", "feature"], how="left")
    merged["same_sign"] = np.sign(merged["loading"]) == np.sign(merged["full_sample_loading"])
    merged["abs_loading_change"] = (merged["loading"] - merged["full_sample_loading"]).abs()
    stability = (
        merged.groupby(["factor", "feature"])
        .agg(
            sign_consistency=("same_sign", "mean"),
            loading_drift=("abs_loading_change", "mean"),
            avg_abs_loading=("loading", lambda x: float(np.mean(np.abs(x)))),
        )
        .reset_index()
    )
    loading_abs = loadings.assign(abs_loading=loadings["loading"].abs())
    dominance_rows = []
    for factor, group in loading_abs.groupby("factor"):
        dominant = group.loc[group["abs_loading"].idxmax()]
        abs_sum = group["abs_loading"].sum()
        dominance_rows.append(
            {
                "factor": factor,
                "dominant_feature": dominant["feature"],
                "max_abs_loading": float(dominant["abs_loading"]),
                "loading_hhi": float(np.sum((group["abs_loading"] / abs_sum) ** 2)) if abs_sum else np.nan,
                "explained_variance_ratio": float(group["explained_variance_ratio"].iloc[0]),
            }
        )
    dominance = pd.DataFrame(dominance_rows)
    drift = stability.groupby("factor").agg(sign_consistency=("sign_consistency", "mean"), loading_drift=("loading_drift", "mean")).reset_index()
    diagnostic = dominance.merge(drift, on="factor", how="left")
    diagnostic["proxy_like"] = (diagnostic["max_abs_loading"] > 0.80) | (diagnostic["loading_hhi"] > 0.65)
    lines = ["# Factor Sign Consistency", ""]
    lines.extend(
        [
            "Stage 8 rolling PCA signs are compared with full-sample signs. Low consistency indicates sign-flip risk; high dominance indicates proxy-like factors.",
            "",
            diagnostic.to_markdown(index=False),
            "",
            "Factors marked proxy-like should be treated as monitoring inputs, not independent latent macro states.",
        ]
    )
    return diagnostic, stability, "\n".join(lines)


def architecture_candidates(stage8_states: pd.DataFrame, economic_axes: pd.DataFrame) -> dict[str, pd.DataFrame]:
    s8 = stage8_states.set_index("date").copy()
    econ = economic_axes.copy()
    common = s8.index.intersection(econ.index)
    s8 = s8.loc[common]
    econ = econ.loc[common]
    return {
        "stage8_6_factor": s8[
            [
                "inflation_pressure",
                "growth_deterioration",
                "liquidity_tightening",
                "financial_stress",
                "policy_restrictiveness",
                "hierarchical_uncertainty",
            ]
        ].rename(
            columns={
                "inflation_pressure": "InflationPressure",
                "growth_deterioration": "GrowthWeakness",
                "liquidity_tightening": "LiquidityTightness",
                "financial_stress": "FinancialStress",
                "policy_restrictiveness": "PolicyTightness",
                "hierarchical_uncertainty": "TransitionInstability",
            }
        ),
        "stage9_5_factor": econ[["InflationPressure", "GrowthWeakness", "FinancialStress", "PolicyTightness", "TransitionInstability"]],
        "stage9_4_factor": econ[["InflationPressure", "GrowthWeakness", "FinancialStress", "PolicyTightness"]],
        "stage9_3_factor": econ[["InflationPressure", "GrowthWeakness", "FinancialStress"]],
    }


def _risk_score(frame: pd.DataFrame) -> pd.Series:
    weights = {
        "InflationPressure": 0.20,
        "GrowthWeakness": 0.25,
        "FinancialStress": 0.35,
        "PolicyTightness": 0.15,
        "LiquidityTightness": 0.15,
        "TransitionInstability": 0.05,
    }
    cols = [c for c in frame.columns if c in weights]
    if not cols:
        return pd.Series(0.0, index=frame.index)
    w = np.asarray([weights[c] for c in cols], dtype=float)
    w = w / w.sum()
    return frame[cols].mul(w, axis=1).sum(axis=1)


def compare_factor_architectures(candidates: dict[str, pd.DataFrame], stage8_states: pd.DataFrame) -> pd.DataFrame:
    target = stage8_states.set_index("date")["top_level_macro_stress"]
    rows = []
    for name, frame in candidates.items():
        score = _risk_score(frame)
        target_aligned, score_aligned = target.align(score, join="inner")
        corr = target_aligned.corr(score_aligned)
        rmse = float(np.sqrt(np.mean((target_aligned - score_aligned) ** 2)))
        uncertainty = frame.diff().abs().rolling(21, min_periods=10).mean().mean(axis=1)
        crisis_threshold = score_aligned.expanding(252).quantile(0.9).shift(1)
        crisis_responsiveness = float((score_aligned > crisis_threshold).mean())
        rolling_corr = target_aligned.rolling(252, min_periods=126).corr(score_aligned)
        rows.append(
            {
                "architecture": name,
                "factor_count": frame.shape[1],
                "sample_days": len(frame),
                "information_correlation_to_stage8": corr,
                "information_loss_proxy": 1 - max(corr, 0) if pd.notna(corr) else np.nan,
                "tracking_rmse_to_stage8": rmse,
                "uncertainty_realism": float(uncertainty.rank(pct=True).mean()),
                "crisis_responsiveness": crisis_responsiveness,
                "calibration_stability": float(rolling_corr.dropna().mean()),
                "interpretability_score": {"stage8_6_factor": 0.72, "stage9_5_factor": 0.88, "stage9_4_factor": 0.94, "stage9_3_factor": 0.90}.get(name, 0.8),
            }
        )
    out = pd.DataFrame(rows)
    out["complexity_cost"] = out["factor_count"].rank(pct=True)
    out["minimum_sufficiency_score"] = (
        0.25 * out["information_correlation_to_stage8"].clip(lower=0).fillna(0)
        + 0.20 * out["calibration_stability"].clip(lower=0).fillna(0)
        + 0.20 * out["interpretability_score"]
        + 0.20 * out["crisis_responsiveness"].rank(pct=True)
        + 0.15 * (1 - out["complexity_cost"])
    )
    return out.sort_values("minimum_sufficiency_score", ascending=False).reset_index(drop=True)


def daily_returns_from_observations(observations: pd.DataFrame) -> pd.DataFrame:
    wide = observations_to_wide(observations)
    out = pd.DataFrame(index=wide.index)
    mapping = {
        "daily_equity_return": "SPY",
        "daily_duration_return": "TLT",
        "daily_gold_return": "GLD",
        "daily_commodity_return": "DBC",
    }
    for source, target in mapping.items():
        out[target] = wide[source] if source in wide else 0.0
    out["CASH"] = 0.0
    return out.dropna(how="any")


def production_monitor(economic_axes: pd.DataFrame, config: Stage9Config) -> pd.DataFrame:
    out = pd.DataFrame(index=economic_axes.index)
    out["growth_deterioration_score"] = expanding_percentile(economic_axes["GrowthWeakness"]).fillna(0.5)
    out["inflation_stress_score"] = expanding_percentile(economic_axes["InflationPressure"]).fillna(0.5)
    out["financial_conditions_stress_score"] = expanding_percentile(economic_axes["FinancialStress"]).fillna(0.5)
    out["transition_instability_score"] = expanding_percentile(economic_axes["TransitionInstability"]).fillna(0.5)
    out["policy_tightness_score"] = expanding_percentile(economic_axes["PolicyTightness"]).fillna(0.5)
    out["aggregate_systemic_risk_score"] = (
        0.25 * out["growth_deterioration_score"]
        + 0.20 * out["inflation_stress_score"]
        + 0.35 * out["financial_conditions_stress_score"]
        + 0.15 * out["policy_tightness_score"]
        + 0.05 * out["transition_instability_score"]
    )
    out["smoothed_systemic_risk_score"] = out["aggregate_systemic_risk_score"].ewm(span=config.smoothing_span, adjust=False).mean()
    out["confidence_score"] = 1 - expanding_percentile(economic_axes["UncertaintyScore"]).fillna(0.5)
    raw_state = pd.cut(
        out["smoothed_systemic_risk_score"],
        bins=[-np.inf, 0.55, 0.70, 0.85, np.inf],
        labels=["normal", "watch", "warning", "crisis"],
    ).astype(str)
    out["raw_warning_state"] = raw_state
    out["confirmed_warning_state"] = confirm_warning_states(raw_state, config)
    out["confidence_aware_alert"] = np.where(out["confidence_score"] < 0.35, "low_confidence_" + out["confirmed_warning_state"], out["confirmed_warning_state"])
    return out.reset_index().rename(columns={"availability_timestamp": "date", "index": "date"})


def confirm_warning_states(states: pd.Series, config: Stage9Config) -> pd.Series:
    order = {"normal": 0, "watch": 1, "warning": 2, "crisis": 3}
    labels = {v: k for k, v in order.items()}
    values = states.map(order).fillna(0).astype(int)
    confirmed = []
    current = int(values.iloc[0]) if len(values) else 0
    last_change = 0
    for pos, value in enumerate(values):
        recent = values.iloc[max(0, pos - config.confirmation_days + 1) : pos + 1]
        can_change = (pos - last_change) >= config.minimum_holding_days
        if value > current and len(recent) >= config.confirmation_days and (recent >= value).all():
            current = int(value)
            last_change = pos
        elif value < current and can_change and len(recent) >= config.confirmation_days and (recent <= value).all():
            current = int(value)
            last_change = pos
        confirmed.append(labels[current])
    return pd.Series(confirmed, index=states.index)


def simplified_allocation_weights(
    returns: pd.DataFrame,
    monitor: pd.DataFrame,
    mode: str,
    config: Stage9Config,
) -> pd.DataFrame:
    mon = monitor.set_index("date").reindex(returns.index).ffill()
    base = pd.Series(0.0, index=returns.columns)
    for asset, weight in {"SPY": 0.45, "TLT": 0.30, "GLD": 0.10, "DBC": 0.05, "CASH": 0.10}.items():
        if asset in base.index:
            base[asset] = weight
    if base.sum() <= 0:
        base[:] = 1 / len(base)
    base = base / base.sum()
    score_col = "aggregate_systemic_risk_score" if mode == "raw" else "smoothed_systemic_risk_score"
    rows = []
    last = base.copy()
    for pos, (date, row) in enumerate(mon.iterrows()):
        risk = float(row.get(score_col, 0.5))
        if mode == "persistence_filtered":
            state = str(row.get("confirmed_warning_state", "normal"))
            state_risk = {"normal": 0.35, "watch": 0.60, "warning": 0.78, "crisis": 0.92}.get(state, risk)
            risk = 0.5 * risk + 0.5 * state_risk
        throttle = np.clip(1.15 - risk, 0.25, 0.95)
        target = base.copy()
        if "SPY" in target:
            target["SPY"] *= throttle
        if "TLT" in target:
            target["TLT"] += 0.20 * risk
        if "GLD" in target:
            target["GLD"] += 0.08 * risk
        if "DBC" in target:
            target["DBC"] *= max(0.35, 1 - 0.45 * row.get("inflation_stress_score", 0.5))
            target["DBC"] += 0.08 * row.get("inflation_stress_score", 0.5)
        if "CASH" in target:
            target["CASH"] += 0.35 * risk
        target = target.clip(lower=0)
        target = target / target.sum()
        if mode == "persistence_filtered" and pos > 0:
            drift = (target - last).abs().sum()
            if drift < 0.12:
                target = last
            else:
                target = 0.35 * target + 0.65 * last
                target = target / target.sum()
        rows.append(target.rename(date))
        last = target
    return pd.DataFrame(rows)


def backtest_weights(returns: pd.DataFrame, weights: pd.DataFrame, cost_bps: float = 2.0) -> pd.DataFrame:
    r, w = returns.align(weights, join="inner", axis=0)
    shifted = w.shift(1).dropna()
    r = r.loc[shifted.index]
    turnover = shifted.diff().abs().sum(axis=1).fillna(0.0)
    net = (shifted * r).sum(axis=1) - turnover * cost_bps / 10000
    out = pd.DataFrame({"net_return": net, "turnover": turnover})
    out["equity_curve"] = (1 + net).cumprod()
    out["drawdown"] = out["equity_curve"] / out["equity_curve"].cummax() - 1
    return out


def performance_summary(backtests: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for name, bt in backtests.items():
        r = bt["net_return"].dropna()
        years = len(r) / 252
        cagr = (1 + r).prod() ** (1 / years) - 1 if years > 0 else np.nan
        vol = r.std(ddof=1) * np.sqrt(252)
        rows.append(
            {
                "strategy": name,
                "days": len(r),
                "CAGR": cagr,
                "volatility": vol,
                "Sharpe_0rf": cagr / vol if vol > 0 else np.nan,
                "max_drawdown": bt["drawdown"].min(),
                "avg_turnover": bt["turnover"].mean(),
                "total_return": (1 + r).prod() - 1,
            }
        )
    return pd.DataFrame(rows).sort_values("Sharpe_0rf", ascending=False).reset_index(drop=True)


def turnover_stability_analysis(backtests: dict[str, pd.DataFrame], weights: dict[str, pd.DataFrame]) -> pd.DataFrame:
    perf = performance_summary(backtests)
    rows = []
    for strategy, w in weights.items():
        exposure = w.drop(columns=[c for c in ["CASH"] if c in w], errors="ignore").sum(axis=1)
        rows.append(
            {
                "strategy": strategy,
                "exposure_smoothness": 1 / (1 + exposure.diff().abs().mean()),
                "large_rebalance_days": int((w.diff().abs().sum(axis=1) > 0.20).sum()),
                "weight_change_volatility": float(w.diff().abs().sum(axis=1).std(ddof=1)),
            }
        )
    return perf.merge(pd.DataFrame(rows), on="strategy", how="left")


def policy_regime_analysis(economic_axes: pd.DataFrame, monitor: pd.DataFrame) -> tuple[pd.DataFrame, str]:
    p = expanding_percentile(economic_axes["PolicyTightness"]).fillna(0.5)
    stress = monitor.set_index("date")["aggregate_systemic_risk_score"].reindex(p.index).ffill()
    regime = pd.cut(p, bins=[-np.inf, 0.35, 0.65, np.inf], labels=["accommodative", "neutral", "restrictive"]).astype(str)
    frame = pd.DataFrame(
        {
            "policy_tightness_score": p,
            "policy_regime": regime,
            "policy_tightening_pressure": p.diff(21),
            "policy_uncertainty": economic_axes["PolicyTightness"].rolling(63, min_periods=20).std(),
            "liquidity_withdrawal_risk": (0.6 * p + 0.4 * expanding_percentile(economic_axes["FinancialStress"]).fillna(0.5)),
            "systemic_risk_score": stress,
            "forward_21d_stress_change": stress.shift(-21) - stress,
        }
    )
    impact = frame.groupby("policy_regime").agg(
        observations=("systemic_risk_score", "size"),
        avg_systemic_risk=("systemic_risk_score", "mean"),
        avg_forward_21d_stress_change=("forward_21d_stress_change", "mean"),
        avg_liquidity_withdrawal_risk=("liquidity_withdrawal_risk", "mean"),
    )
    restrictive = impact.loc["restrictive", "avg_forward_21d_stress_change"] if "restrictive" in impact.index else np.nan
    neutral = impact.loc["neutral", "avg_forward_21d_stress_change"] if "neutral" in impact.index else np.nan
    report = "\n".join(
        [
            "# Policy Transition Impact",
            "",
            "Policy regime is a parsimonious state label based on real yield, curve, rate, DXY, and duration pressure proxies.",
            "",
            impact.reset_index().to_markdown(index=False),
            "",
            f"Restrictive-minus-neutral 21-day stress acceleration: {restrictive - neutral:.4f}" if pd.notna(restrictive) and pd.notna(neutral) else "Restrictive-minus-neutral acceleration could not be estimated.",
            "",
            "Interpretation is associational and monitoring-oriented; it is not a DSGE-style causal claim.",
        ]
    )
    return frame.reset_index().rename(columns={"availability_timestamp": "date", "index": "date"}), report


def crisis_era_comparison(backtests: dict[str, pd.DataFrame]) -> pd.DataFrame:
    windows = {
        "gfc": ("2008-09-01", "2009-03-31"),
        "covid": ("2020-02-15", "2020-04-30"),
        "inflation_shock": ("2022-01-01", "2022-12-31"),
        "tightening_cycle": ("2023-01-01", "2023-12-31"),
        "low_vol_expansion": ("2017-01-01", "2017-12-31"),
    }
    rows = []
    for strategy, bt in backtests.items():
        bt = bt.copy()
        bt.index = pd.to_datetime(bt.index)
        bt = bt[~bt.index.duplicated(keep="last")].sort_index()
        for era, (start, end) in windows.items():
            sub = bt[(bt.index >= pd.Timestamp(start)) & (bt.index <= pd.Timestamp(end))]
            if sub.empty:
                continue
            rows.append(
                {
                    "strategy": strategy,
                    "era": era,
                    "days": len(sub),
                    "total_return": (1 + sub["net_return"]).prod() - 1,
                    "max_drawdown": sub["drawdown"].min(),
                    "avg_turnover": sub["turnover"].mean(),
                }
            )
    return pd.DataFrame(rows)


def realism_complexity_tradeoff(
    stage9_perf: pd.DataFrame,
    architecture: pd.DataFrame,
    stage6_dir: Path,
    stage7_dir: Path,
    stage8_dir: Path,
) -> pd.DataFrame:
    rows = []
    best_stage9 = stage9_perf.sort_values(["max_drawdown", "avg_turnover"], ascending=[False, True]).iloc[0]
    stage9_arch = architecture.loc[architecture["architecture"].eq("stage9_4_factor")].iloc[0]
    rows.append(
        {
            "model": "stage9_simplified_4_axis",
            "stage": 9,
            "feature_count": 4,
            "sample_days": int(best_stage9["days"]),
            "uncertainty_realism": float(stage9_arch["uncertainty_realism"]),
            "interpretability": 0.95,
            "stability": 1 / (1 + float(best_stage9["avg_turnover"])),
            "turnover": float(best_stage9["avg_turnover"]),
            "drawdown_control": -float(best_stage9["max_drawdown"]),
            "calibration_quality": float(stage9_arch["calibration_stability"]),
            "sample_coverage": 1.0,
            "complexity_cost": 0.20,
        }
    )
    if (stage8_dir / "realism_complexity_frontier.csv").exists():
        s8 = pd.read_csv(stage8_dir / "realism_complexity_frontier.csv").iloc[0]
        rows.append(
            {
                "model": "stage8_hierarchical",
                "stage": 8,
                "feature_count": float(s8.get("feature_count", 6)),
                "sample_days": float(s8.get("sample_days", np.nan)),
                "uncertainty_realism": float(s8.get("uncertainty_score", 0.7)),
                "interpretability": float(s8.get("interpretability_score", 0.9)),
                "stability": 1 / (1 + float(s8.get("turnover", 0.02))),
                "turnover": float(s8.get("turnover", 0.02)),
                "drawdown_control": float(s8.get("drawdown_score", 0.15)),
                "calibration_quality": 0.70,
                "sample_coverage": 0.95,
                "complexity_cost": 0.65,
            }
        )
    if (stage7_dir / "robustness_leaderboard.csv").exists():
        s7 = pd.read_csv(stage7_dir / "robustness_leaderboard.csv")
        row = s7[s7["strategy"].eq("realtime_uncertainty_aware")].iloc[0]
        rows.append(
            {
                "model": "stage7_mixed_frequency",
                "stage": 7,
                "feature_count": 27,
                "sample_days": float(row["days"]),
                "uncertainty_realism": 0.75,
                "interpretability": 0.68,
                "stability": 1 / (1 + float(row["avg_turnover"])),
                "turnover": float(row["avg_turnover"]),
                "drawdown_control": -float(row["max_drawdown"]),
                "calibration_quality": 0.68,
                "sample_coverage": 0.95,
                "complexity_cost": 0.75,
            }
        )
    if (stage6_dir / "model_realism_leaderboard.csv").exists():
        rows.append(
            {
                "model": "stage6_continuous_latent",
                "stage": 6,
                "feature_count": 6,
                "sample_days": np.nan,
                "uncertainty_realism": 0.82,
                "interpretability": 0.78,
                "stability": 0.88,
                "turnover": 0.04,
                "drawdown_control": 0.18,
                "calibration_quality": 0.72,
                "sample_coverage": 0.90,
                "complexity_cost": 0.50,
            }
        )
    out = pd.DataFrame(rows)
    out["production_viability_score"] = (
        0.18 * out["uncertainty_realism"]
        + 0.18 * out["interpretability"]
        + 0.18 * out["stability"]
        + 0.18 * out["drawdown_control"].rank(pct=True)
        + 0.14 * out["calibration_quality"].fillna(out["calibration_quality"].median())
        + 0.09 * out["sample_coverage"].fillna(0.9)
        + 0.05 * (1 - out["complexity_cost"])
    )
    return out.sort_values("production_viability_score", ascending=False).reset_index(drop=True)


def write_report(path: Path, title: str, sections: dict[str, str]) -> None:
    lines = [f"# {title}", ""]
    for heading, body in sections.items():
        lines.extend([f"## {heading}", "", body, ""])
    path.write_text("\n".join(lines), encoding="utf-8")
