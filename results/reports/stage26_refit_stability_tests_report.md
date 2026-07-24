# Stage 26 Refit Stability Tests

## Purpose

Stage 26 tests the Stage 25 diagnosis that quarterly refit instability, not the 2-state regime concept alone, caused OOS overlay degradation. Only low-overfit refit changes are tested: fixed initial HMM and annual expanding refit.

## Refit Methods

| method | HMM refit | signal update | portfolio target update |
|:--|:--|:--|:--|
| fixed | fit once through 2012 | daily posterior under frozen model | daily |
| annual | expanding refit annually | daily posterior within each annual fold | daily |
| quarterly | Stage 24 baseline | daily posterior within each quarterly fold | daily |
| fullsample | lookahead context only | daily posterior | daily |

## Focus Performance

| model                                 |   days |      CAGR |   Sharpe |   Sortino |   max_drawdown |   Calmar |   avg_turnover |   total_return |
|:--------------------------------------|-------:|----------:|---------:|----------:|---------------:|---------:|---------------:|---------------:|
| static_60_40_spy_tlt                  |   3462 | 0.0952909 | 0.890127 |   1.144   |      -0.308021 | 0.309365 |    0           |        2.49188 |
| static_diversified                    |   3462 | 0.0882986 | 0.959525 |   1.21816 |      -0.219565 | 0.402153 |    0           |        2.19778 |
| fullsample_two_state_overlay_balanced |   3462 | 0.0784552 | 0.984291 |   1.33195 |      -0.19486  | 0.402623 |    0.0022675   |        1.82253 |
| fixed_two_state_overlay_balanced      |   3462 | 0.0865215 | 0.981103 |   1.26155 |      -0.219565 | 0.394059 |    0.000970539 |        2.12678 |
| annual_two_state_overlay_balanced     |   3462 | 0.0816002 | 0.939046 |   1.21212 |      -0.21665  | 0.376645 |    0.00453144  |        1.93773 |
| quarterly_two_state_overlay_balanced  |   3462 | 0.075318  | 0.885844 |   1.14548 |      -0.219536 | 0.343078 |    0.0131395   |        1.7118  |

## Balanced Overlay Deltas vs Static Diversified

| method     | model                                 |      CAGR |   Sharpe |   max_drawdown |   Calmar |   avg_turnover |   cagr_delta_vs_static_pct_points |   sharpe_delta_vs_static |   mdd_improvement_vs_static_pct_points |   calmar_delta_vs_static |
|:-----------|:--------------------------------------|----------:|---------:|---------------:|---------:|---------------:|----------------------------------:|-------------------------:|---------------------------------------:|-------------------------:|
| fixed      | fixed_two_state_overlay_balanced      | 0.0865215 | 0.981103 |      -0.219565 | 0.394059 |    0.000970539 |                         -0.177709 |                0.0215778 |                            5.44122e-08 |             -0.00809367  |
| annual     | annual_two_state_overlay_balanced     | 0.0816002 | 0.939046 |      -0.21665  | 0.376645 |    0.00453144  |                         -0.669839 |               -0.0204792 |                            0.291444    |             -0.0255081   |
| quarterly  | quarterly_two_state_overlay_balanced  | 0.075318  | 0.885844 |      -0.219536 | 0.343078 |    0.0131395   |                         -1.29806  |               -0.073681  |                            0.00291604  |             -0.0590741   |
| fullsample | fullsample_two_state_overlay_balanced | 0.0784552 | 0.984291 |      -0.19486  | 0.402623 |    0.0022675   |                         -0.984337 |                0.024766  |                            2.47044     |              0.000469998 |

## Signal Jump Summary

| signal_model   |   days |   mean_abs_risk_prob_change |   median_abs_risk_prob_change |   p95_abs_risk_prob_change |   jump_gt_25pct_count |   jump_gt_50pct_count |   regime_flip_count |   mean_risk_probability |   high_stress_days |
|:---------------|-------:|----------------------------:|------------------------------:|---------------------------:|----------------------:|----------------------:|--------------------:|------------------------:|-------------------:|
| fixed          |   3462 |                  0.00144467 |                   2.6799e-39  |                5.19894e-11 |                     5 |                     5 |                   6 |               0.0153093 |                 53 |
| annual         |   3462 |                  0.00780526 |                   1.75512e-20 |                7.01265e-05 |                    29 |                    22 |                  28 |               0.0816201 |                285 |
| quarterly      |   3462 |                  0.0231812  |                   2.61141e-16 |                0.00800897  |                    86 |                    70 |                  80 |               0.146262  |                507 |

## Signal Stability

| signal    | start               | end                 |   observations |   regime_flips |   flips_per_year |   avg_regime_duration_days |   median_regime_duration_days |   mean_risk_probability |   median_risk_probability |   mean_posterior_confidence |
|:----------|:--------------------|:--------------------|---------------:|---------------:|-----------------:|---------------------------:|------------------------------:|------------------------:|--------------------------:|----------------------------:|
| fixed     | 2013-01-02 00:00:00 | 2026-05-15 00:00:00 |           3462 |              5 |         0.363951 |                    577     |                          26   |               0.0153093 |               2.04735e-40 |                    0.999834 |
| annual    | 2013-01-02 00:00:00 | 2026-05-15 00:00:00 |           3462 |             27 |         1.96534  |                    123.643 |                          43.5 |               0.0816201 |               2.96965e-20 |                    0.996698 |
| quarterly | 2013-01-02 00:00:00 | 2026-05-15 00:00:00 |           3462 |             79 |         5.75043  |                     43.275 |                          29.5 |               0.146262  |               9.94232e-16 |                    0.99581  |

## Crisis Summary

| model                                | period          |   period_return |   period_max_drawdown |   avg_turnover |   avg_SPY |   avg_TLT |   avg_GLD |   avg_DBC |   avg_CASH |
|:-------------------------------------|:----------------|----------------:|----------------------:|---------------:|----------:|----------:|----------:|----------:|-----------:|
| static_diversified                   | covid           |       0.0735431 |             -0.150532 |    0           |  0.45     |  0.25     |  0.15     | 0.1       |  0.05      |
| static_diversified                   | inflation_shock |      -0.175036  |             -0.219565 |    0           |  0.45     |  0.25     |  0.15     | 0.1       |  0.05      |
| static_diversified                   | recent          |       0.655756  |             -0.175721 |    0           |  0.45     |  0.25     |  0.15     | 0.1       |  0.05      |
| fixed_two_state_overlay_balanced     | covid           |       0.0504411 |             -0.140874 |    0.0207407   |  0.329628 |  0.274074 |  0.174074 | 0.0855554 |  0.136668  |
| fixed_two_state_overlay_balanced     | inflation_shock |      -0.175036  |             -0.219565 |    6.3052e-09  |  0.45     |  0.25     |  0.15     | 0.1       |  0.05      |
| fixed_two_state_overlay_balanced     | recent          |       0.655756  |             -0.175721 |    1.59515e-20 |  0.45     |  0.25     |  0.15     | 0.1       |  0.05      |
| annual_two_state_overlay_balanced    | covid           |       0.0419196 |             -0.147843 |    0.01038     |  0.345831 |  0.270834 |  0.170834 | 0.0874997 |  0.125002  |
| annual_two_state_overlay_balanced    | inflation_shock |      -0.164589  |             -0.21665  |    0.00495139  |  0.345725 |  0.270855 |  0.170855 | 0.087487  |  0.125078  |
| annual_two_state_overlay_balanced    | recent          |       0.649371  |             -0.173011 |    0.00515077  |  0.448849 |  0.25023  |  0.15023  | 0.0998619 |  0.0508286 |
| quarterly_two_state_overlay_balanced | covid           |       0.0177358 |             -0.147843 |    0.0051948   |  0.269442 |  0.286112 |  0.186112 | 0.0783331 |  0.180002  |
| quarterly_two_state_overlay_balanced | inflation_shock |      -0.175346  |             -0.219536 |    0.0144655   |  0.314246 |  0.277151 |  0.177151 | 0.0837095 |  0.147743  |
| quarterly_two_state_overlay_balanced | recent          |       0.643904  |             -0.176398 |    0.0180248   |  0.445948 |  0.25081  |  0.15081  | 0.0995138 |  0.0529172 |

## Interpretation

If fixed or annual refit improves OOS behavior materially versus quarterly refit, the failure mode is likely refit instability and posterior jumps. If all walk-forward variants still fail versus static diversified, the HMM overlay should be treated as a risk-monitoring or guardrail tool rather than a direct allocation engine.