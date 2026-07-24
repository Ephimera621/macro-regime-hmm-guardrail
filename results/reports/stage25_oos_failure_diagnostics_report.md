# Stage 25 OOS Failure Diagnostics

## Purpose

Stage 25 diagnoses why the Stage 24 walk-forward overlay failed to preserve the full-sample advantage versus static diversified allocation. It does not introduce a new tuned model.

## Rebalancing Clarification

The Stage 24 HMM is refit quarterly, but portfolio targets are recomputed daily from the current walk-forward posterior. Execution occurs with the existing one-period lag. Therefore realized rebalancing is event/posterior-driven on daily data, not fixed monthly or quarterly rebalancing.

## Signal Jump Diagnostics

| sample              |   days |   mean_abs_risk_prob_change |   median_abs_risk_prob_change |   p95_abs_risk_prob_change |   jump_gt_25pct_count |   jump_gt_50pct_count |   regime_flip_count |   mean_risk_probability |
|:--------------------|-------:|----------------------------:|------------------------------:|---------------------------:|----------------------:|----------------------:|--------------------:|------------------------:|
| all_days            |   3462 |                   0.0231812 |                   2.61141e-16 |                 0.00800897 |                    86 |                    70 |                  80 |                0.146262 |
| refit_boundary_days |     54 |                   0.685985  |                   0.999982    |                 1          |                    37 |                    36 |                  37 |                0.766355 |
| within_fold_days    |   3408 |                   0.0128735 |                   1.0965e-16  |                 0.00170717 |                    49 |                    34 |                  43 |                0.136436 |
| regime_flip_days    |     80 |                   0.923358  |                   1           |                 1          |                    79 |                    70 |                  80 |                0.524549 |

## Turnover Decomposition

| model                                   |   avg_turnover |   total_turnover |   estimated_total_cost_return_drag |   avg_cost_drag_per_day |   turnover_on_refit_days |   turnover_on_regime_flip_days |   share_turnover_refit_days |   share_turnover_regime_flip_days |   days_turnover_gt_10pct |   days_turnover_gt_25pct |
|:----------------------------------------|---------------:|-----------------:|-----------------------------------:|------------------------:|-------------------------:|-------------------------------:|----------------------------:|----------------------------------:|-------------------------:|-------------------------:|
| fullsample_two_state_overlay_balanced   |     0.0022675  |          7.85009 |                        0.00157002  |             4.535e-07   |               0.185759   |                       0.177939 |                 0.0236632   |                         0.0226672 |                       27 |                        5 |
| fullsample_two_state_overlay_defensive  |     0.0031583  |         10.9341  |                        0.00218681  |             6.31661e-07 |               0.258735   |                       0.247844 |                 0.0236632   |                         0.0226672 |                       32 |                       14 |
| fullsample_two_state_overlay_mild       |     0.0013767  |          4.76612 |                        0.000953225 |             2.75339e-07 |               0.112782   |                       0.108035 |                 0.0236632   |                         0.0226672 |                       15 |                        2 |
| walkforward_two_state_overlay_balanced  |     0.0131395  |         45.4889  |                        0.00909778  |             2.6279e-06  |               0.00580994 |                      18.5857   |                 0.000127722 |                         0.408577  |                       93 |                       75 |
| walkforward_two_state_overlay_defensive |     0.0183014  |         63.3595  |                        0.0126719   |             3.66028e-06 |               0.00809242 |                      25.8872   |                 0.000127722 |                         0.408577  |                       98 |                       81 |
| walkforward_two_state_overlay_mild      |     0.00797754 |         27.6183  |                        0.00552365  |             1.59551e-06 |               0.00352747 |                      11.2842   |                 0.000127722 |                         0.408577  |                       84 |                       70 |

## Walk-Forward vs Full-Sample Signal Alignment

|   days |   probability_correlation |   mean_abs_probability_gap |   median_abs_probability_gap |   p95_abs_probability_gap |   high_stress_flag_agreement |   walkforward_high_stress_days |   fullsample_high_stress_days |
|-------:|--------------------------:|---------------------------:|-----------------------------:|--------------------------:|-----------------------------:|-------------------------------:|------------------------------:|
|   3462 |                  0.583588 |                   0.125988 |                  3.60442e-07 |                  0.999943 |                     0.874928 |                            507 |                           690 |

## Crisis Timing

| window          | start      | end        |   days |   mean_risk_probability |   median_risk_probability |   high_stress_day_share | first_high_stress_date   | last_high_stress_date   |   risk_probability_at_window_start |   max_risk_probability |
|:----------------|:-----------|:-----------|-------:|------------------------:|--------------------------:|------------------------:|:-------------------------|:------------------------|-----------------------------------:|-----------------------:|
| covid           | 2020-02-01 | 2020-06-30 |    108 |               0.722231  |               1           |                0.722222 | 2020-03-13 00:00:00      | 2020-06-30 00:00:00     |                         3.3771e-15 |                      1 |
| inflation_shock | 2022-01-01 | 2022-12-31 |    258 |               0.543018  |               0.884672    |                0.550388 | 2022-01-03 00:00:00      | 2022-10-14 00:00:00     |                         1          |                      1 |
| recent          | 2023-01-01 | 2026-05-15 |    870 |               0.0162066 |               3.86345e-11 |                0.016092 | 2023-01-03 00:00:00      | 2026-04-01 00:00:00     |                         1          |                      1 |

## Benchmark Strength

| benchmark          |      CAGR |   Sharpe |   max_drawdown |   Calmar |   avg_SPY |   avg_defensive_plus_cash |   avg_non_equity |
|:-------------------|----------:|---------:|---------------:|---------:|----------:|--------------------------:|-----------------:|
| static_diversified | 0.0882986 | 0.959525 |      -0.219565 | 0.402153 |      0.45 |                      0.45 |             0.55 |

## Improvement Candidates

| option                  | description                                                                                                                | targets_failure_mode               | overfit_risk   |   next_test_priority |
|:------------------------|:---------------------------------------------------------------------------------------------------------------------------|:-----------------------------------|:---------------|---------------------:|
| A_fixed_hmm_update_only | Fit the 2-state HMM on a long initial sample, freeze emission/state mapping, and update posterior without quarterly refit. | state boundary instability         | low            |                    1 |
| B_annual_refit          | Refit annually instead of quarterly to reduce boundary churn.                                                              | refit-induced posterior jumps      | low            |                    2 |
| C_posterior_ewma        | Apply EWMA smoothing to walk-forward p_stress before mapping to weights.                                                   | daily posterior jumps and turnover | medium         |                    3 |
| D_activation_hysteresis | Require p_stress to exceed an activation threshold and fall below a lower deactivation threshold.                          | short-lived regime activations     | medium         |                    4 |
| E_weight_change_cap     | Limit daily target weight change to reduce execution churn.                                                                | turnover drag                      | medium         |                    5 |
| F_guardrail_only        | Use HMM only to raise a cash floor or cap SPY in high stress, rather than continuously blending all weights.               | direct allocation mismatch         | low            |                    6 |

## Interpretation

The main diagnostic question is whether OOS failure comes from the regime concept itself, the quarterly refit procedure, or the direct daily mapping from posterior probability to portfolio weights. If instability and turnover are concentrated around posterior jumps/refit boundaries, the next stage should test lower-frequency or frozen-parameter variants before changing the economic thesis.