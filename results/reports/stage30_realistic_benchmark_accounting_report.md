# Stage 30 Realistic Benchmark Accounting

## Purpose

Stage 30 replaces target-diff-only turnover with drift-aware holdings accounting. Static benchmarks are now tested as true buy-and-hold and monthly/quarterly/annual rebalanced portfolios with 2bps transaction costs.

## Rebalance Policies

| model                                    | rebalance_frequency   |
|:-----------------------------------------|:----------------------|
| static_buy_hold_diversified              | buy_hold              |
| static_monthly_diversified               | monthly               |
| static_quarterly_diversified             | quarterly             |
| static_annual_diversified                | annual                |
| static_ideal_daily_diversified           | daily                 |
| hmm_annual_hysteresis_monthly_balanced   | monthly               |
| hmm_annual_hysteresis_quarterly_balanced | quarterly             |

## Performance

| model                                    |   days |      CAGR |   Sharpe |   Sortino |   max_drawdown |   Calmar |   avg_turnover |   total_return |
|:-----------------------------------------|-------:|----------:|---------:|----------:|---------------:|---------:|---------------:|---------------:|
| static_buy_hold_diversified              |   3462 | 0.104813  | 0.921368 |   1.14458 |      -0.256036 | 0.409368 |    0           |        2.93282 |
| static_monthly_diversified               |   3462 | 0.0859047 | 0.942186 |   1.1905  |      -0.222013 | 0.386936 |    0.00112702  |        2.10249 |
| static_quarterly_diversified             |   3462 | 0.0870933 | 0.962907 |   1.22548 |      -0.220911 | 0.394245 |    0.000688047 |        2.14947 |
| static_annual_diversified                |   3462 | 0.0885722 | 0.985643 |   1.25425 |      -0.212591 | 0.416632 |    0.00037953  |        2.20884 |
| static_ideal_daily_diversified           |   3462 | 0.08799   | 0.956169 |   1.21414 |      -0.219838 | 0.40025  |    0.00562666  |        2.18535 |
| hmm_annual_hysteresis_monthly_balanced   |   3462 | 0.0815937 | 0.928783 |   1.18208 |      -0.193347 | 0.422007 |    0.0023538   |        1.93749 |
| hmm_annual_hysteresis_quarterly_balanced |   3462 | 0.0846882 | 0.977084 |   1.25855 |      -0.191956 | 0.441187 |    0.00153113  |        2.05508 |

## Fair Comparison Deltas

| model                                    | benchmark                      |   cagr_delta_pct_points |   sharpe_delta |   mdd_improvement_pct_points |   calmar_delta |   turnover_delta |
|:-----------------------------------------|:-------------------------------|------------------------:|---------------:|-----------------------------:|---------------:|-----------------:|
| hmm_annual_hysteresis_monthly_balanced   | static_monthly_diversified     |               -0.4311   |    -0.0134028  |                      2.86659 |      0.035071  |      0.00122678  |
| hmm_annual_hysteresis_quarterly_balanced | static_quarterly_diversified   |               -0.240505 |     0.0141772  |                      2.89558 |      0.0469412 |      0.000843084 |
| hmm_annual_hysteresis_quarterly_balanced | static_buy_hold_diversified    |               -2.01245  |     0.0557169  |                      6.40802 |      0.0318191 |      0.00153113  |
| hmm_annual_hysteresis_quarterly_balanced | static_annual_diversified      |               -0.388391 |    -0.00855902 |                      2.06355 |      0.0245551 |      0.0011516   |
| hmm_annual_hysteresis_quarterly_balanced | static_ideal_daily_diversified |               -0.33018  |     0.0209155  |                      2.78822 |      0.0409368 |     -0.00409553  |

## Turnover and Cost

| model                                    |   avg_turnover |   total_turnover |   total_transaction_cost_drag |   rebalance_events |   days_turnover_gt_5pct |   days_turnover_gt_10pct |
|:-----------------------------------------|---------------:|-----------------:|------------------------------:|-------------------:|------------------------:|-------------------------:|
| static_buy_hold_diversified              |    0           |          0       |                   0           |                  0 |                       0 |                        0 |
| static_monthly_diversified               |    0.00112702  |          3.90173 |                   0.000780346 |                160 |                      12 |                        0 |
| static_quarterly_diversified             |    0.000688047 |          2.38202 |                   0.000476404 |                 53 |                      18 |                        2 |
| static_annual_diversified                |    0.00037953  |          1.31393 |                   0.000262787 |                 13 |                      11 |                        6 |
| static_ideal_daily_diversified           |    0.00562666  |         19.4795  |                   0.0038959   |               3457 |                       1 |                        0 |
| hmm_annual_hysteresis_monthly_balanced   |    0.0023538   |          8.14886 |                   0.00162977  |                160 |                      19 |                        8 |
| hmm_annual_hysteresis_quarterly_balanced |    0.00153113  |          5.30077 |                   0.00106015  |                 53 |                      20 |                        7 |

## Crisis Summary

| model                                    | period          |   period_return |   period_max_drawdown |   avg_turnover |   avg_SPY |   avg_TLT |   avg_GLD |   avg_DBC |   avg_CASH |
|:-----------------------------------------|:----------------|----------------:|----------------------:|---------------:|----------:|----------:|----------:|----------:|-----------:|
| static_buy_hold_diversified              | covid           |       0.0652338 |             -0.173612 |    0           |  0.62295  | 0.235611  | 0.0881832 | 0.0255141 |  0.0277417 |
| static_buy_hold_diversified              | inflation_shock |      -0.208016  |             -0.256036 |    0           |  0.722392 | 0.139159  | 0.0731103 | 0.0431861 |  0.0221527 |
| static_buy_hold_diversified              | recent          |       0.88023   |             -0.213242 |    0           |  0.769721 | 0.0909623 | 0.0874525 | 0.0341828 |  0.017681  |
| static_monthly_diversified               | covid           |       0.057869  |             -0.158177 |    0.00206254  |  0.450556 | 0.249953  | 0.151637  | 0.0980924 |  0.0497618 |
| static_monthly_diversified               | inflation_shock |      -0.17807   |             -0.222013 |    0.00156837  |  0.448868 | 0.246258  | 0.151713  | 0.102662  |  0.0504983 |
| static_monthly_diversified               | recent          |       0.642389  |             -0.178803 |    0.00103366  |  0.450864 | 0.247867  | 0.151529  | 0.100053  |  0.0496876 |
| static_quarterly_diversified             | covid           |       0.0683922 |             -0.153004 |    0.00130845  |  0.453009 | 0.255786  | 0.152817  | 0.0903548 |  0.0480318 |
| static_quarterly_diversified             | inflation_shock |      -0.177898  |             -0.220911 |    0.000878357 |  0.450906 | 0.238379  | 0.151686  | 0.108018  |  0.0510108 |
| static_quarterly_diversified             | recent          |       0.647564  |             -0.178692 |    0.000655874 |  0.452942 | 0.244399  | 0.153942  | 0.0995655 |  0.0491521 |
| static_annual_diversified                | covid           |       0.0574485 |             -0.153004 |    0           |  0.427603 | 0.294125  | 0.154014  | 0.0750559 |  0.049202  |
| static_annual_diversified                | inflation_shock |      -0.169792  |             -0.212591 |    0.000532812 |  0.428117 | 0.211651  | 0.163018  | 0.141078  |  0.0561369 |
| static_annual_diversified                | recent          |       0.66591   |             -0.170939 |    0.000586692 |  0.461944 | 0.231707  | 0.162825  | 0.0969325 |  0.0465921 |
| static_ideal_daily_diversified           | covid           |       0.0732292 |             -0.15063  |    0.0135372   |  0.450001 | 0.25023   | 0.150001  | 0.0997953 |  0.0499721 |
| static_ideal_daily_diversified           | inflation_shock |      -0.175381  |             -0.219838 |    0.00808746  |  0.449938 | 0.249758  | 0.150102  | 0.100163  |  0.0500393 |
| static_ideal_daily_diversified           | recent          |       0.6542    |             -0.176069 |    0.00540393  |  0.450114 | 0.249846  | 0.150077  | 0.099991  |  0.0499719 |
| hmm_annual_hysteresis_monthly_balanced   | covid           |       0.0164912 |             -0.158177 |    0.0111378   |  0.352904 | 0.269764  | 0.172004  | 0.0867207 |  0.118607  |
| hmm_annual_hysteresis_monthly_balanced   | inflation_shock |      -0.147785  |             -0.193347 |    0.00584893  |  0.32563  | 0.269963  | 0.176658  | 0.086718  |  0.14103   |
| hmm_annual_hysteresis_monthly_balanced   | recent          |       0.642389  |             -0.148544 |    0.00103366  |  0.450864 | 0.247867  | 0.151529  | 0.100053  |  0.0496876 |
| hmm_annual_hysteresis_quarterly_balanced | covid           |       0.0228465 |             -0.153004 |    0.00420522  |  0.300713 | 0.288036  | 0.186261  | 0.0745135 |  0.150476  |
| hmm_annual_hysteresis_quarterly_balanced | inflation_shock |      -0.147344  |             -0.191956 |    0.00494948  |  0.329904 | 0.259948  | 0.176322  | 0.0897724 |  0.144053  |
| hmm_annual_hysteresis_quarterly_balanced | recent          |       0.647564  |             -0.148167 |    0.000655874 |  0.452942 | 0.244399  | 0.153942  | 0.0995655 |  0.0491521 |

## Interpretation

The key comparison is HMM quarterly versus static quarterly, and HMM monthly versus static monthly. Buy-and-hold and ideal daily constant-weight are included as boundary cases. This stage is pre-tax and includes only the 2bps transaction-cost assumption.