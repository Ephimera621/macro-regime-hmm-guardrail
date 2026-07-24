"""Stage 12 HMM structural-extension comparison utilities.

This module is intentionally additive: it reuses the Stage 9 point-in-time style
economic axes, execution timing, and transaction-cost assumptions, then compares
three modest HMM variants without changing any earlier stage artifacts.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from hmmlearn.hmm import GaussianHMM
from scipy.special import logsumexp
from sklearn.linear_model import LogisticRegression
from sklearn.preprocessing import StandardScaler

from stage9_simplified import Stage9Config, backtest_weights, daily_returns_from_observations, expanding_percentile


@dataclass(frozen=True)
class Stage12Config:
    n_states: int = 3
    transaction_cost_bps: float = 2.0
    random_state: int = 42
    min_persistence_days: int = 5
    confirmation_days: int = 3
    probability_hysteresis: float = 0.08
    activation_threshold: float = 0.65
    stress_features: tuple[str, ...] = (
        "FinancialStress",
        "GrowthWeakness",
        "PolicyTightness",
        "InflationPressure",
        "SystemicRiskScore",
    )


def load_stage12_inputs(stage7_dir, stage9_dir) -> tuple[pd.DataFrame, pd.DataFrame]:
    observations = pd.read_csv(
        stage7_dir / "mixed_frequency_observations.csv",
        parse_dates=["observation_timestamp", "release_timestamp", "availability_timestamp"],
    )
    returns = daily_returns_from_observations(observations)
    axes = pd.read_csv(stage9_dir / "economic_axis_scores.csv", parse_dates=["date"]).set_index("date")
    common = returns.index.intersection(axes.index)
    return axes.loc[common].sort_index(), returns.loc[common].sort_index()


def _feature_matrix(axes: pd.DataFrame) -> tuple[pd.DataFrame, StandardScaler, np.ndarray]:
    cols = ["InflationPressure", "GrowthWeakness", "FinancialStress", "PolicyTightness", "TransitionInstability"]
    features = axes[cols].replace([np.inf, -np.inf], np.nan).ffill().fillna(0.0)
    scaler = StandardScaler()
    values = scaler.fit_transform(features)
    return features, scaler, values


def _fit_baseline_hmm(values: np.ndarray, config: Stage12Config) -> GaussianHMM:
    model = GaussianHMM(
        n_components=config.n_states,
        covariance_type="diag",
        min_covar=1e-4,
        n_iter=1000,
        random_state=config.random_state,
    )
    model.fit(values)
    return model


def _risk_order_from_axes(labels: pd.Series, axes: pd.DataFrame) -> dict[int, int]:
    risk = axes["SystemicRiskScore"].groupby(labels).mean().sort_values()
    return {int(raw): rank for rank, raw in enumerate(risk.index)}


def _posteriors_to_frame(index: pd.Index, labels: np.ndarray, probs: np.ndarray, mapping: dict[int, int]) -> pd.DataFrame:
    rows = []
    for pos, date in enumerate(index):
        stable_probs = {f"prob_regime_{i}": 0.0 for i in sorted(mapping.values())}
        for raw_state, prob in enumerate(probs[pos]):
            stable_probs[f"prob_regime_{mapping.get(raw_state, raw_state)}"] += float(prob)
        rows.append(
            {
                "date": date,
                "raw_state": int(labels[pos]),
                "regime": int(mapping.get(int(labels[pos]), int(labels[pos]))),
                "posterior_confidence": float(np.max(list(stable_probs.values()))),
                **stable_probs,
            }
        )
    return pd.DataFrame(rows)


def baseline_hmm(axes: pd.DataFrame, config: Stage12Config) -> tuple[GaussianHMM, pd.DataFrame, np.ndarray]:
    _, _, values = _feature_matrix(axes)
    model = _fit_baseline_hmm(values, config)
    raw_labels = model.predict(values)
    raw_probs = model.predict_proba(values)
    mapping = _risk_order_from_axes(pd.Series(raw_labels, index=axes.index), axes)
    return model, _posteriors_to_frame(axes.index, raw_labels, raw_probs, mapping), values


def duration_aware_overlay(base: pd.DataFrame, config: Stage12Config) -> pd.DataFrame:
    prob_cols = sorted([c for c in base.columns if c.startswith("prob_regime_")])
    risk_col = prob_cols[-1]
    probs = base[prob_cols].to_numpy(float)
    raw = probs.argmax(axis=1)
    confirmed = []
    current = int(raw[0])
    last_change = 0
    for pos, candidate in enumerate(raw):
        recent = raw[max(0, pos - config.confirmation_days + 1) : pos + 1]
        current_prob = probs[pos, current]
        candidate_prob = probs[pos, candidate]
        enough_confirmation = len(recent) >= config.confirmation_days and np.all(recent == candidate)
        enough_hysteresis = candidate_prob >= current_prob + config.probability_hysteresis
        enough_holding = (pos - last_change) >= config.min_persistence_days
        if candidate != current and enough_confirmation and enough_holding and enough_hysteresis:
            current = int(candidate)
            last_change = pos
        confirmed.append(current)
    out = base.copy()
    out["regime"] = confirmed
    for col in prob_cols:
        out[col] = out[col].ewm(span=config.min_persistence_days, adjust=False).mean()
    out["posterior_confidence"] = out[prob_cols].max(axis=1)
    out["risk_probability"] = out[risk_col]
    return out


def conditional_hmm(
    axes: pd.DataFrame,
    values: np.ndarray,
    fitted_hmm: GaussianHMM,
    base: pd.DataFrame,
    config: Stage12Config,
) -> pd.DataFrame:
    raw_labels = base["raw_state"].to_numpy(int)
    cond = axes[list(config.stress_features)].replace([np.inf, -np.inf], np.nan).ffill().fillna(0.0)
    cond_scaled = StandardScaler().fit_transform(cond)
    x_rows = []
    y_rows = []
    for t in range(1, len(raw_labels)):
        prev_one_hot = np.zeros(config.n_states)
        prev_one_hot[raw_labels[t - 1]] = 1.0
        x_rows.append(np.r_[prev_one_hot, cond_scaled[t]])
        y_rows.append(raw_labels[t])
    clf = LogisticRegression(
        solver="lbfgs",
        C=1.0,
        max_iter=1000,
        random_state=config.random_state,
    )
    clf.fit(np.vstack(x_rows), np.array(y_rows))
    log_likelihood = fitted_hmm._compute_log_likelihood(values)
    log_alpha = np.log(fitted_hmm.startprob_ + 1e-12) + log_likelihood[0]
    log_alpha -= logsumexp(log_alpha)
    filtered = [np.exp(log_alpha)]
    for t in range(1, len(values)):
        trans = np.zeros((config.n_states, config.n_states))
        for prev in range(config.n_states):
            prev_one_hot = np.zeros(config.n_states)
            prev_one_hot[prev] = 1.0
            design = np.r_[prev_one_hot, cond_scaled[t]].reshape(1, -1)
            pred = clf.predict_proba(design)[0]
            row = np.full(config.n_states, 1e-8)
            for cls, prob in zip(clf.classes_, pred):
                row[int(cls)] = prob
            trans[prev] = row / row.sum()
        log_pred = logsumexp(log_alpha[:, None] + np.log(trans + 1e-12), axis=0)
        log_alpha = log_pred + log_likelihood[t]
        log_alpha -= logsumexp(log_alpha)
        filtered.append(np.exp(log_alpha))
    probs = np.vstack(filtered)
    raw_cond = probs.argmax(axis=1)
    mapping = _risk_order_from_axes(pd.Series(raw_labels, index=axes.index), axes)
    out = _posteriors_to_frame(axes.index, raw_cond, probs, mapping)
    out["conditional_transition_signal"] = cond["SystemicRiskScore"].to_numpy(float)
    return out


def _risk_probability(signals: pd.DataFrame) -> pd.Series:
    prob_cols = sorted([c for c in signals.columns if c.startswith("prob_regime_")])
    return signals[prob_cols[-1]].astype(float)


def overlay_weights(signals: pd.DataFrame, axes: pd.DataFrame, returns: pd.DataFrame, config: Stage12Config) -> pd.DataFrame:
    sig = signals.set_index("date").reindex(returns.index).ffill()
    risk = sig["risk_probability"] if "risk_probability" in sig else _risk_probability(sig)
    inflation = expanding_percentile(axes["InflationPressure"]).reindex(returns.index).ffill().fillna(0.5)
    base = pd.Series({"SPY": 0.45, "TLT": 0.30, "GLD": 0.10, "DBC": 0.05, "CASH": 0.10})
    base = base.reindex(returns.columns).fillna(0.0)
    base = base / base.sum()
    rows = []
    for date in returns.index:
        r = float(np.clip(risk.loc[date], 0.0, 1.0))
        target = base.copy()
        throttle = np.clip(1.15 - r, 0.25, 0.95)
        if "SPY" in target:
            target["SPY"] *= throttle
        if "TLT" in target:
            target["TLT"] += 0.20 * r
        if "GLD" in target:
            target["GLD"] += 0.08 * r
        if "DBC" in target:
            inf = float(inflation.loc[date])
            target["DBC"] *= max(0.35, 1 - 0.45 * inf)
            target["DBC"] += 0.08 * inf
        if "CASH" in target:
            target["CASH"] += 0.35 * r
        target = target.clip(lower=0)
        rows.append((target / target.sum()).rename(date))
    return pd.DataFrame(rows)


def performance_metrics(backtests: dict[str, pd.DataFrame]) -> pd.DataFrame:
    rows = []
    for name, bt in backtests.items():
        r = bt["net_return"].dropna()
        years = len(r) / 252
        cagr = (1 + r).prod() ** (1 / years) - 1 if years > 0 else np.nan
        vol = r.std(ddof=1) * np.sqrt(252)
        downside = r[r < 0].std(ddof=1) * np.sqrt(252)
        mdd = bt["drawdown"].min()
        rows.append(
            {
                "model": name,
                "days": len(r),
                "CAGR": cagr,
                "Sharpe": cagr / vol if vol > 0 else np.nan,
                "Sortino": cagr / downside if downside > 0 else np.nan,
                "max_drawdown": mdd,
                "Calmar": cagr / abs(mdd) if mdd < 0 else np.nan,
                "avg_turnover": bt["turnover"].mean(),
                "total_return": (1 + r).prod() - 1,
            }
        )
    return pd.DataFrame(rows)


def stability_metrics(signals: dict[str, pd.DataFrame], weights: dict[str, pd.DataFrame], config: Stage12Config) -> pd.DataFrame:
    rows = []
    for name, sig in signals.items():
        s = sig.set_index("date").sort_index()
        regimes = s["regime"].astype(int)
        flips = regimes.ne(regimes.shift()).sum() - 1
        run_id = regimes.ne(regimes.shift()).cumsum()
        durations = regimes.groupby(run_id).size()
        risk = s["risk_probability"] if "risk_probability" in s else _risk_probability(s)
        w = weights[name]
        rows.append(
            {
                "model": name,
                "regime_flips": int(max(flips, 0)),
                "flips_per_year": float(max(flips, 0) / (len(regimes) / 252)),
                "avg_regime_duration_days": float(durations.mean()),
                "median_regime_duration_days": float(durations.median()),
                "short_regime_share_lt_5d": float((durations < 5).mean()),
                "overlay_activation_frequency": float((risk > config.activation_threshold).mean()),
                "probability_smoothness": float(1 / (1 + risk.diff().abs().mean())),
                "avg_weight_turnover": float(w.diff().abs().sum(axis=1).mean()),
            }
        )
    return pd.DataFrame(rows)


def subperiod_metrics(backtests: dict[str, pd.DataFrame]) -> pd.DataFrame:
    periods = {
        "pre_gfc": ("2006-01-01", "2007-12-31"),
        "gfc": ("2008-01-01", "2009-06-30"),
        "post_gfc_expansion": ("2010-01-01", "2019-12-31"),
        "covid": ("2020-02-01", "2020-06-30"),
        "inflation_shock": ("2022-01-01", "2022-12-31"),
        "recent": ("2023-01-01", "2026-05-11"),
    }
    rows = []
    for name, bt in backtests.items():
        for period, (start, end) in periods.items():
            sub = bt.loc[(bt.index >= start) & (bt.index <= end)]
            if len(sub) < 20:
                continue
            rows.append({"model": name, "period": period, **performance_metrics({name: sub}).iloc[0].drop(["model"]).to_dict()})
    return pd.DataFrame(rows)


def sensitivity_metrics(
    base_signals: pd.DataFrame,
    axes: pd.DataFrame,
    returns: pd.DataFrame,
    config: Stage12Config,
) -> pd.DataFrame:
    rows = []
    for min_days in [3, 5, 10]:
        cfg = Stage12Config(
            n_states=config.n_states,
            transaction_cost_bps=config.transaction_cost_bps,
            random_state=config.random_state,
            min_persistence_days=min_days,
            confirmation_days=config.confirmation_days,
            probability_hysteresis=config.probability_hysteresis,
            activation_threshold=config.activation_threshold,
            stress_features=config.stress_features,
        )
        sig = duration_aware_overlay(base_signals, cfg)
        w = overlay_weights(sig, axes, returns, cfg)
        bt = backtest_weights(returns, w, cfg.transaction_cost_bps)
        perf = performance_metrics({f"duration_min_{min_days}d": bt}).iloc[0]
        stab = stability_metrics({perf["model"]: sig}, {perf["model"]: w}, cfg).iloc[0]
        rows.append(
            {
                "variant": perf["model"],
                "CAGR": perf["CAGR"],
                "Sharpe": perf["Sharpe"],
                "max_drawdown": perf["max_drawdown"],
                "regime_flips": stab["regime_flips"],
                "avg_turnover": perf["avg_turnover"],
            }
        )
    return pd.DataFrame(rows)


def compare_models(axes: pd.DataFrame, returns: pd.DataFrame, config: Stage12Config):
    hmm, baseline, values = baseline_hmm(axes, config)
    baseline["risk_probability"] = _risk_probability(baseline)
    duration = duration_aware_overlay(baseline, config)
    conditional = conditional_hmm(axes, values, hmm, baseline, config)
    conditional["risk_probability"] = _risk_probability(conditional)
    signals = {
        "model1_baseline_gaussian_hmm": baseline,
        "model2_duration_aware_overlay": duration,
        "model3_conditional_hmm": conditional,
    }
    weights = {name: overlay_weights(sig, axes, returns, config) for name, sig in signals.items()}
    backtests = {name: backtest_weights(returns, weights[name], config.transaction_cost_bps) for name in signals}
    return {
        "signals": signals,
        "weights": weights,
        "backtests": backtests,
        "performance": performance_metrics(backtests),
        "stability": stability_metrics(signals, weights, config),
        "subperiods": subperiod_metrics(backtests),
        "sensitivity": sensitivity_metrics(baseline, axes, returns, config),
    }
