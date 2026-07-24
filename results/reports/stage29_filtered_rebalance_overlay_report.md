# Stage 29 Filtered Signal / Rebalance-Frequency Overlay

## Purpose

Stage 29 tests whether annual HMM signals become more usable when weak regime changes are filtered and actual portfolio trading is limited to monthly or quarterly schedules.

## Implementation

HMM refit is annual. Raw posterior is observed daily. Hysteresis activates stress only after `p_stress >= 0.70` for 5 trading days and deactivates after `p_stress <= 0.40` for 10 trading days. Rebalance-limited variants update target weights only at the first trading day of each month or quarter.

## Performance

| model                                |   days |      CAGR |   Sharpe |   Sortino |   max_drawdown |   Calmar |   avg_turnover |   total_return |
|:-------------------------------------|-------:|----------:|---------:|----------:|---------------:|---------:|---------------:|---------------:|
| static_60_40_spy_tlt                 |   3462 | 0.0952909 | 0.890127 |   1.144   |      -0.308021 | 0.309365 |    0           |        2.49188 |
| static_equal_weight                  |   3462 | 0.0566361 | 0.762082 |   1.00207 |      -0.165555 | 0.342098 |    0           |        1.13152 |
| static_diversified                   |   3462 | 0.0882986 | 0.959525 |   1.21816 |      -0.219565 | 0.402153 |    0           |        2.19778 |
| annual_direct_daily_balanced         |   3462 | 0.0816002 | 0.939046 |   1.21212 |      -0.21665  | 0.376645 |    0.00453144  |        1.93773 |
| annual_direct_monthly_balanced       |   3462 | 0.0796246 | 0.900932 |   1.14237 |      -0.202014 | 0.394154 |    0.00388477  |        1.86487 |
| annual_hysteresis_daily_balanced     |   3462 | 0.0827825 | 0.941577 |   1.19374 |      -0.192114 | 0.430903 |    0.00129405  |        1.98216 |
| annual_hysteresis_monthly_balanced   |   3462 | 0.0832369 | 0.936998 |   1.19637 |      -0.190575 | 0.436767 |    0.00129405  |        1.9994  |
| annual_hysteresis_quarterly_balanced |   3462 | 0.0844237 | 0.954593 |   1.22158 |      -0.190575 | 0.442995 |    0.000970537 |        2.04486 |

## Deltas vs Static Diversified

| model                                |      CAGR |   Sharpe |   max_drawdown |   Calmar |   avg_turnover |   cagr_delta_vs_static_pct_points |   sharpe_delta_vs_static |   mdd_improvement_vs_static_pct_points |   calmar_delta_vs_static |
|:-------------------------------------|----------:|---------:|---------------:|---------:|---------------:|----------------------------------:|-------------------------:|---------------------------------------:|-------------------------:|
| annual_hysteresis_quarterly_balanced | 0.0844237 | 0.954593 |      -0.190575 | 0.442995 |    0.000970537 |                         -0.387488 |              -0.00493196 |                               2.899    |               0.0408424  |
| annual_hysteresis_daily_balanced     | 0.0827825 | 0.941577 |      -0.192114 | 0.430903 |    0.00129405  |                         -0.551605 |              -0.0179477  |                               2.74509  |               0.0287506  |
| annual_direct_daily_balanced         | 0.0816002 | 0.939046 |      -0.21665  | 0.376645 |    0.00453144  |                         -0.669839 |              -0.0204792  |                               0.291444 |              -0.0255081  |
| annual_hysteresis_monthly_balanced   | 0.0832369 | 0.936998 |      -0.190575 | 0.436767 |    0.00129405  |                         -0.506169 |              -0.0225264  |                               2.899    |               0.0346148  |
| annual_direct_monthly_balanced       | 0.0796246 | 0.900932 |      -0.202014 | 0.394154 |    0.00388477  |                         -0.867395 |              -0.0585933  |                               1.7551   |              -0.00799826 |

## Signal Filter Diagnostics

| signal            |   days |   mean_risk_probability |   high_stress_days |   high_stress_share |   regime_flips |   flips_per_year |   jump_gt_50pct_count |
|:------------------|-------:|------------------------:|-------------------:|--------------------:|---------------:|-----------------:|----------------------:|
| annual_raw        |   3462 |               0.0816201 |                285 |           0.0823224 |             28 |         2.03813  |                    22 |
| annual_hysteresis |   3462 |               0.0860774 |                298 |           0.0860774 |              9 |         0.655113 |                     8 |

## Turnover Summary

| model                                |   avg_turnover |   total_turnover |   days_turnover_gt_5pct |   days_turnover_gt_10pct |   estimated_total_cost_drag |
|:-------------------------------------|---------------:|-----------------:|------------------------:|-------------------------:|----------------------------:|
| static_60_40_spy_tlt                 |    0           |           0      |                       0 |                        0 |                  0          |
| static_equal_weight                  |    0           |           0      |                       0 |                        0 |                  0          |
| static_diversified                   |    0           |           0      |                       0 |                        0 |                  0          |
| annual_direct_daily_balanced         |    0.00453144  |          15.6878 |                      48 |                       32 |                  0.00313757 |
| annual_direct_monthly_balanced       |    0.00388477  |          13.4491 |                      24 |                       24 |                  0.00268982 |
| annual_hysteresis_daily_balanced     |    0.00129405  |           4.48   |                       8 |                        8 |                  0.000896   |
| annual_hysteresis_monthly_balanced   |    0.00129405  |           4.48   |                       8 |                        8 |                  0.000896   |
| annual_hysteresis_quarterly_balanced |    0.000970537 |           3.36   |                       6 |                        6 |                  0.000672   |

## Crisis Summary

| model                                | period          |   period_return |   period_max_drawdown |   avg_turnover |   avg_SPY |   avg_TLT |   avg_GLD |   avg_DBC |   avg_CASH |
|:-------------------------------------|:----------------|----------------:|----------------------:|---------------:|----------:|----------:|----------:|----------:|-----------:|
| static_60_40_spy_tlt                 | covid           |       0.11643   |             -0.137312 |     0          |  0.6      |  0.4      |  0        | 0         |  0         |
| static_60_40_spy_tlt                 | inflation_shock |      -0.270562  |             -0.308021 |     0          |  0.6      |  0.4      |  0        | 0         |  0         |
| static_60_40_spy_tlt                 | recent          |       0.520613  |             -0.272174 |     0          |  0.6      |  0.4      |  0        | 0         |  0         |
| static_equal_weight                  | covid           |       0.0332361 |             -0.132526 |     0          |  0.2      |  0.2      |  0.2      | 0.2       |  0.2       |
| static_equal_weight                  | inflation_shock |      -0.0878005 |             -0.165555 |     0          |  0.2      |  0.2      |  0.2      | 0.2       |  0.2       |
| static_equal_weight                  | recent          |       0.512746  |             -0.133887 |     0          |  0.2      |  0.2      |  0.2      | 0.2       |  0.2       |
| static_diversified                   | covid           |       0.0735431 |             -0.150532 |     0          |  0.45     |  0.25     |  0.15     | 0.1       |  0.05      |
| static_diversified                   | inflation_shock |      -0.175036  |             -0.219565 |     0          |  0.45     |  0.25     |  0.15     | 0.1       |  0.05      |
| static_diversified                   | recent          |       0.655756  |             -0.175721 |     0          |  0.45     |  0.25     |  0.15     | 0.1       |  0.05      |
| annual_direct_daily_balanced         | covid           |       0.0419196 |             -0.147843 |     0.01038    |  0.345831 |  0.270834 |  0.170834 | 0.0874997 |  0.125002  |
| annual_direct_daily_balanced         | inflation_shock |      -0.164589  |             -0.21665  |     0.00495139 |  0.345725 |  0.270855 |  0.170855 | 0.087487  |  0.125078  |
| annual_direct_daily_balanced         | recent          |       0.649371  |             -0.173011 |     0.00515077 |  0.448849 |  0.25023  |  0.15023  | 0.0998619 |  0.0508286 |
| annual_direct_monthly_balanced       | covid           |       0.0142678 |             -0.150532 |     0.0155556  |  0.352778 |  0.269444 |  0.169444 | 0.0883333 |  0.12      |
| annual_direct_monthly_balanced       | inflation_shock |      -0.147349  |             -0.202014 |     0.00224279 |  0.325989 |  0.274802 |  0.174802 | 0.0851187 |  0.139288  |
| annual_direct_monthly_balanced       | recent          |       0.602322  |             -0.157184 |     0.00514952 |  0.425574 |  0.254885 |  0.154885 | 0.0970689 |  0.0675865 |
| annual_hysteresis_daily_balanced     | covid           |       0.0198349 |             -0.150532 |     0.0103704  |  0.334259 |  0.273148 |  0.173148 | 0.0861111 |  0.133333  |
| annual_hysteresis_daily_balanced     | inflation_shock |      -0.140975  |             -0.192114 |     0.00217054 |  0.33469  |  0.273062 |  0.173062 | 0.0861628 |  0.133023  |
| annual_hysteresis_daily_balanced     | recent          |       0.655756  |             -0.146728 |     0          |  0.45     |  0.25     |  0.15     | 0.1       |  0.05      |
| annual_hysteresis_monthly_balanced   | covid           |       0.0160743 |             -0.150532 |     0.0103704  |  0.352778 |  0.269444 |  0.169444 | 0.0883333 |  0.12      |
| annual_hysteresis_monthly_balanced   | inflation_shock |      -0.144392  |             -0.190575 |     0.00434109 |  0.325969 |  0.274806 |  0.174806 | 0.0851163 |  0.139302  |
| annual_hysteresis_monthly_balanced   | recent          |       0.655756  |             -0.145102 |     0          |  0.45     |  0.25     |  0.15     | 0.1       |  0.05      |
| annual_hysteresis_quarterly_balanced | covid           |       0.0128929 |             -0.150532 |     0.00518519 |  0.301852 |  0.27963  |  0.17963  | 0.0822222 |  0.156667  |
| annual_hysteresis_quarterly_balanced | inflation_shock |      -0.144392  |             -0.190575 |     0.00434109 |  0.325969 |  0.274806 |  0.174806 | 0.0851163 |  0.139302  |
| annual_hysteresis_quarterly_balanced | recent          |       0.655756  |             -0.145102 |     0          |  0.45     |  0.25     |  0.15     | 0.1       |  0.05      |

## Interpretation

This stage tests implementation filtering, not a new alpha model. If filtering and rebalance limits reduce turnover but still fail to improve static diversified performance, the HMM should be used as a dashboard or limited guardrail rather than a direct allocation engine.