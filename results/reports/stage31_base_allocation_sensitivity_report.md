# Stage 31 Base-Allocation Sensitivity

## Purpose

Stage 31 tests whether the HMM guardrail survives when the static policy portfolio is changed. This is not a portfolio optimization step; the base allocations and defensive transformation are pre-declared and intentionally small in number.

## Shared Assumptions

- OOS start: `2013-01-01`
- HMM refit: annual expanding walk-forward
- Signal filter: Stage 29 hysteresis
- Rebalance: quarterly, drift-aware holdings accounting
- Transaction cost: 2bps per turnover unit
- Taxes: not included

## Base and Stress Specifications

| base_portfolio   | regime   |   SPY |      TLT |      GLD |   DBC |     CASH |
|:-----------------|:---------|------:|---------:|---------:|------:|---------:|
| defensive_35     | base     |  0.35 | 0.3      | 0.2      |  0.1  | 0.05     |
| defensive_35     | stress   |  0.2  | 0.332143 | 0.232143 |  0.07 | 0.165714 |
| balanced_40      | base     |  0.4  | 0.25     | 0.2      |  0.1  | 0.05     |
| balanced_40      | stress   |  0.2  | 0.291071 | 0.241071 |  0.07 | 0.197857 |
| current_45       | base     |  0.45 | 0.25     | 0.15     |  0.1  | 0.05     |
| current_45       | stress   |  0.2  | 0.3      | 0.2      |  0.07 | 0.23     |
| growth_50        | base     |  0.5  | 0.25     | 0.1      |  0.1  | 0.05     |
| growth_50        | stress   |  0.25 | 0.3      | 0.15     |  0.07 | 0.23     |
| aggressive_55    | base     |  0.55 | 0.2      | 0.1      |  0.1  | 0.05     |
| aggressive_55    | stress   |  0.3  | 0.25     | 0.15     |  0.07 | 0.23     |

## Performance

| model                                 |   days |      CAGR |   Sharpe |   Sortino |   max_drawdown |   Calmar |   avg_turnover |   total_return |
|:--------------------------------------|-------:|----------:|---------:|----------:|---------------:|---------:|---------------:|---------------:|
| defensive_35_static_quarterly         |   3462 | 0.0761576 | 0.892275 |   1.16833 |      -0.223157 | 0.341274 |    0.000712107 |        1.74103 |
| defensive_35_static_buy_hold          |   3462 | 0.0938986 | 0.916466 |   1.15038 |      -0.254839 | 0.368463 |    0           |        2.4314  |
| defensive_35_hmm_guardrail_quarterly  |   3462 | 0.0741394 | 0.888786 |   1.17254 |      -0.209534 | 0.353831 |    0.00121752  |        1.67125 |
| balanced_40_static_quarterly          |   3462 | 0.083586  | 0.946456 |   1.2178  |      -0.214864 | 0.389018 |    0.000698778 |        2.01271 |
| balanced_40_static_buy_hold           |   3462 | 0.100456  | 0.923201 |   1.15169 |      -0.251906 | 0.398784 |    0           |        2.72503 |
| balanced_40_hmm_guardrail_quarterly   |   3462 | 0.0813726 | 0.951793 |   1.23574 |      -0.196205 | 0.414732 |    0.00137497  |        1.92925 |
| current_45_static_quarterly           |   3462 | 0.0870933 | 0.962907 |   1.22548 |      -0.220911 | 0.394245 |    0.000688047 |        2.14947 |
| current_45_static_buy_hold            |   3462 | 0.104813  | 0.921368 |   1.14458 |      -0.256036 | 0.409368 |    0           |        2.93282 |
| current_45_hmm_guardrail_quarterly    |   3462 | 0.0846882 | 0.977084 |   1.25855 |      -0.191956 | 0.441187 |    0.00153113  |        2.05508 |
| growth_50_static_quarterly            |   3462 | 0.0905168 | 0.962975 |   1.21345 |      -0.226961 | 0.39882  |    0.000669785 |        2.28849 |
| growth_50_static_buy_hold             |   3462 | 0.108961  | 0.916645 |   1.13589 |      -0.259699 | 0.419566 |    0           |        3.14061 |
| growth_50_hmm_guardrail_quarterly     |   3462 | 0.0881366 | 0.983199 |   1.25504 |      -0.198056 | 0.445008 |    0.00151195  |        2.19125 |
| aggressive_55_static_quarterly        |   3462 | 0.0977953 | 0.975715 |   1.21813 |      -0.220538 | 0.44344  |    0.000636159 |        2.60319 |
| aggressive_55_static_buy_hold         |   3462 | 0.114505  | 0.910595 |   1.12512 |      -0.256997 | 0.445552 |    0           |        3.43424 |
| aggressive_55_hmm_guardrail_quarterly |   3462 | 0.0954349 | 1.00041  |   1.26227 |      -0.191366 | 0.498703 |    0.00148292  |        2.4982  |

## Deltas

| base_portfolio   | model                                 | benchmark                      |   cagr_delta_pct_points |   sharpe_delta |   mdd_improvement_pct_points |   calmar_delta |   turnover_delta |
|:-----------------|:--------------------------------------|:-------------------------------|------------------------:|---------------:|-----------------------------:|---------------:|-----------------:|
| defensive_35     | defensive_35_hmm_guardrail_quarterly  | defensive_35_static_quarterly  |               -0.201816 |    -0.0034885  |                      1.36233 |      0.012557  |      0.00050541  |
| defensive_35     | defensive_35_hmm_guardrail_quarterly  | defensive_35_static_buy_hold   |               -1.97592  |    -0.0276797  |                      4.5305  |     -0.0146326 |      0.00121752  |
| balanced_40      | balanced_40_hmm_guardrail_quarterly   | balanced_40_static_quarterly   |               -0.221344 |     0.00533651 |                      1.8659  |      0.0257141 |      0.000676189 |
| balanced_40      | balanced_40_hmm_guardrail_quarterly   | balanced_40_static_buy_hold    |               -1.90835  |     0.0285917  |                      5.57007 |      0.015948  |      0.00137497  |
| current_45       | current_45_hmm_guardrail_quarterly    | current_45_static_quarterly    |               -0.240505 |     0.0141772  |                      2.89558 |      0.0469412 |      0.000843084 |
| current_45       | current_45_hmm_guardrail_quarterly    | current_45_static_buy_hold     |               -2.01245  |     0.0557169  |                      6.40802 |      0.0318191 |      0.00153113  |
| growth_50        | growth_50_hmm_guardrail_quarterly     | growth_50_static_quarterly     |               -0.23802  |     0.0202243  |                      2.89052 |      0.0461878 |      0.000842163 |
| growth_50        | growth_50_hmm_guardrail_quarterly     | growth_50_static_buy_hold      |               -2.08244  |     0.0665542  |                      6.16429 |      0.0254417 |      0.00151195  |
| aggressive_55    | aggressive_55_hmm_guardrail_quarterly | aggressive_55_static_quarterly |               -0.236044 |     0.0246949  |                      2.91718 |      0.0552633 |      0.000846763 |
| aggressive_55    | aggressive_55_hmm_guardrail_quarterly | aggressive_55_static_buy_hold  |               -1.90705  |     0.0898148  |                      6.56308 |      0.0531515 |      0.00148292  |

## Fair Static Quarterly Pass/Fail

| base_portfolio   | model                                 | benchmark                      |   cagr_delta_pct_points |   sharpe_delta |   mdd_improvement_pct_points |   calmar_delta |   turnover_delta | mdd_pass   | calmar_pass   | cagr_cost_pass   | overall_guardrail_pass   |
|:-----------------|:--------------------------------------|:-------------------------------|------------------------:|---------------:|-----------------------------:|---------------:|-----------------:|:-----------|:--------------|:-----------------|:-------------------------|
| defensive_35     | defensive_35_hmm_guardrail_quarterly  | defensive_35_static_quarterly  |               -0.201816 |    -0.0034885  |                      1.36233 |      0.012557  |      0.00050541  | True       | True          | True             | True                     |
| balanced_40      | balanced_40_hmm_guardrail_quarterly   | balanced_40_static_quarterly   |               -0.221344 |     0.00533651 |                      1.8659  |      0.0257141 |      0.000676189 | True       | True          | True             | True                     |
| current_45       | current_45_hmm_guardrail_quarterly    | current_45_static_quarterly    |               -0.240505 |     0.0141772  |                      2.89558 |      0.0469412 |      0.000843084 | True       | True          | True             | True                     |
| growth_50        | growth_50_hmm_guardrail_quarterly     | growth_50_static_quarterly     |               -0.23802  |     0.0202243  |                      2.89052 |      0.0461878 |      0.000842163 | True       | True          | True             | True                     |
| aggressive_55    | aggressive_55_hmm_guardrail_quarterly | aggressive_55_static_quarterly |               -0.236044 |     0.0246949  |                      2.91718 |      0.0552633 |      0.000846763 | True       | True          | True             | True                     |

## Turnover and Cost

| model                                 |   avg_turnover |   total_turnover |   total_transaction_cost_drag |   rebalance_events |   days_turnover_gt_5pct |   days_turnover_gt_10pct |
|:--------------------------------------|---------------:|-----------------:|------------------------------:|-------------------:|------------------------:|-------------------------:|
| defensive_35_static_quarterly         |    0.000712107 |          2.46532 |                   0.000493063 |                 53 |                      20 |                        2 |
| defensive_35_static_buy_hold          |    0           |          0       |                   0           |                  0 |                       0 |                        0 |
| defensive_35_hmm_guardrail_quarterly  |    0.00121752  |          4.21505 |                   0.000843009 |                 53 |                      22 |                        7 |
| balanced_40_static_quarterly          |    0.000698778 |          2.41917 |                   0.000483834 |                 53 |                      20 |                        2 |
| balanced_40_static_buy_hold           |    0           |          0       |                   0           |                  0 |                       0 |                        0 |
| balanced_40_hmm_guardrail_quarterly   |    0.00137497  |          4.76014 |                   0.000952027 |                 53 |                      22 |                        7 |
| current_45_static_quarterly           |    0.000688047 |          2.38202 |                   0.000476404 |                 53 |                      18 |                        2 |
| current_45_static_buy_hold            |    0           |          0       |                   0           |                  0 |                       0 |                        0 |
| current_45_hmm_guardrail_quarterly    |    0.00153113  |          5.30077 |                   0.00106015  |                 53 |                      20 |                        7 |
| growth_50_static_quarterly            |    0.000669785 |          2.3188  |                   0.000463759 |                 53 |                      16 |                        2 |
| growth_50_static_buy_hold             |    0           |          0       |                   0           |                  0 |                       0 |                        0 |
| growth_50_hmm_guardrail_quarterly     |    0.00151195  |          5.23437 |                   0.00104687  |                 53 |                      18 |                        7 |
| aggressive_55_static_quarterly        |    0.000636159 |          2.20238 |                   0.000440476 |                 53 |                      14 |                        2 |
| aggressive_55_static_buy_hold         |    0           |          0       |                   0           |                  0 |                       0 |                        0 |
| aggressive_55_hmm_guardrail_quarterly |    0.00148292  |          5.13388 |                   0.00102678  |                 53 |                      16 |                        7 |

## Crisis Summary

| model                                 | period          |   period_return |   period_max_drawdown |   avg_turnover |   avg_SPY |   avg_TLT |   avg_GLD |   avg_DBC |   avg_CASH |
|:--------------------------------------|:----------------|----------------:|----------------------:|---------------:|----------:|----------:|----------:|----------:|-----------:|
| defensive_35_static_quarterly         | covid           |       0.0739201 |             -0.139107 |    0.0013548   |  0.352265 | 0.305992  | 0.203462  | 0.0903448 |  0.0479358 |
| defensive_35_static_quarterly         | inflation_shock |      -0.177988  |             -0.223157 |    0.000888572 |  0.351505 | 0.286632  | 0.202595  | 0.108168  |  0.0511011 |
| defensive_35_static_quarterly         | recent          |       0.601757  |             -0.180919 |    0.000689192 |  0.352499 | 0.293384  | 0.205327  | 0.0996131 |  0.0491766 |
| defensive_35_static_buy_hold          | covid           |       0.0705038 |             -0.155843 |    0           |  0.516712 | 0.301199  | 0.125319  | 0.027207  |  0.0295624 |
| defensive_35_static_buy_hold          | inflation_shock |      -0.208657  |             -0.254839 |    0           |  0.630162 | 0.187244  | 0.109316  | 0.048432  |  0.0248456 |
| defensive_35_static_buy_hold          | recent          |       0.842616  |             -0.211687 |    0           |  0.683331 | 0.124458  | 0.133062  | 0.0389845 |  0.0201641 |
| defensive_35_hmm_guardrail_quarterly  | covid           |       0.0451118 |             -0.139107 |    0.00278508  |  0.260134 | 0.327026  | 0.225353  | 0.0739083 |  0.113578  |
| defensive_35_hmm_guardrail_quarterly  | inflation_shock |      -0.163572  |             -0.209534 |    0.00338858  |  0.279292 | 0.300682  | 0.218519  | 0.0902835 |  0.111222  |
| defensive_35_hmm_guardrail_quarterly  | recent          |       0.601757  |             -0.166555 |    0.000689192 |  0.352499 | 0.293384  | 0.205327  | 0.0996131 |  0.0491766 |
| balanced_40_static_quarterly          | covid           |       0.0682813 |             -0.149233 |    0.00126083  |  0.402561 | 0.255496  | 0.20362   | 0.09033   |  0.0479927 |
| balanced_40_static_quarterly          | inflation_shock |      -0.169093  |             -0.214864 |    0.000888425 |  0.400705 | 0.238284  | 0.202114  | 0.107918  |  0.0509796 |
| balanced_40_static_quarterly          | recent          |       0.663942  |             -0.168799 |    0.000665735 |  0.402245 | 0.24415   | 0.205035  | 0.0994663 |  0.0491042 |
| balanced_40_static_buy_hold           | covid           |       0.0659545 |             -0.1679   |    0           |  0.576768 | 0.245326  | 0.122444  | 0.0265735 |  0.0288881 |
| balanced_40_static_buy_hold           | inflation_shock |      -0.203549  |             -0.251906 |    0           |  0.68016  | 0.147398  | 0.103243  | 0.0457359 |  0.0234628 |
| balanced_40_static_buy_hold           | recent          |       0.882962  |             -0.207972 |    0           |  0.725098 | 0.0964326 | 0.123495  | 0.03623   |  0.0187443 |
| balanced_40_hmm_guardrail_quarterly   | covid           |       0.0312411 |             -0.149233 |    0.003462    |  0.280466 | 0.28183   | 0.231649  | 0.0742231 |  0.131832  |
| balanced_40_hmm_guardrail_quarterly   | inflation_shock |      -0.146458  |             -0.196205 |    0.00416974  |  0.304388 | 0.256133  | 0.222179  | 0.0899027 |  0.127398  |
| balanced_40_hmm_guardrail_quarterly   | recent          |       0.663942  |             -0.149045 |    0.000665735 |  0.402245 | 0.24415   | 0.205035  | 0.0994663 |  0.0491042 |
| current_45_static_quarterly           | covid           |       0.0683922 |             -0.153004 |    0.00130845  |  0.453009 | 0.255786  | 0.152817  | 0.0903548 |  0.0480318 |
| current_45_static_quarterly           | inflation_shock |      -0.177898  |             -0.220911 |    0.000878357 |  0.450906 | 0.238379  | 0.151686  | 0.108018  |  0.0510108 |
| current_45_static_quarterly           | recent          |       0.647564  |             -0.178692 |    0.000655874 |  0.452942 | 0.244399  | 0.153942  | 0.0995655 |  0.0491521 |
| current_45_static_buy_hold            | covid           |       0.0652338 |             -0.173612 |    0           |  0.62295  | 0.235611  | 0.0881832 | 0.0255141 |  0.0277417 |
| current_45_static_buy_hold            | inflation_shock |      -0.208016  |             -0.256036 |    0           |  0.722392 | 0.139159  | 0.0731103 | 0.0431861 |  0.0221527 |
| current_45_static_buy_hold            | recent          |       0.88023   |             -0.213242 |    0           |  0.769721 | 0.0909623 | 0.0874525 | 0.0341828 |  0.017681  |
| current_45_hmm_guardrail_quarterly    | covid           |       0.0228465 |             -0.153004 |    0.00420522  |  0.300713 | 0.288036  | 0.186261  | 0.0745135 |  0.150476  |
| current_45_hmm_guardrail_quarterly    | inflation_shock |      -0.147344  |             -0.191956 |    0.00494948  |  0.329904 | 0.259948  | 0.176322  | 0.0897724 |  0.144053  |
| current_45_hmm_guardrail_quarterly    | recent          |       0.647564  |             -0.148167 |    0.000655874 |  0.452942 | 0.244399  | 0.153942  | 0.0995655 |  0.0491521 |
| growth_50_static_quarterly            | covid           |       0.0684704 |             -0.15765  |    0.00134694  |  0.503506 | 0.256088  | 0.101951  | 0.0903828 |  0.048073  |
| growth_50_static_quarterly            | inflation_shock |      -0.186666  |             -0.226961 |    0.000854668 |  0.501153 | 0.238484  | 0.101195  | 0.108123  |  0.0510442 |
| growth_50_static_quarterly            | recent          |       0.630969  |             -0.18852  |    0.000644342 |  0.503741 | 0.244652  | 0.10274   | 0.0996665 |  0.0492008 |
| growth_50_static_buy_hold             | covid           |       0.0645713 |             -0.182261 |    0           |  0.665598 | 0.226639  | 0.0565427 | 0.0245365 |  0.0266833 |
| growth_50_static_buy_hold             | inflation_shock |      -0.211981  |             -0.259699 |    0           |  0.760156 | 0.131793  | 0.0461637 | 0.0409059 |  0.0209813 |
| growth_50_static_buy_hold             | recent          |       0.87778   |             -0.217918 |    0           |  0.809608 | 0.0860819 | 0.0552224 | 0.0323557 |  0.0167323 |
| growth_50_hmm_guardrail_quarterly     | covid           |       0.0230593 |             -0.15765  |    0.00419729  |  0.352438 | 0.288251  | 0.134447  | 0.0745688 |  0.150295  |
| growth_50_hmm_guardrail_quarterly     | inflation_shock |      -0.156255  |             -0.198056 |    0.00496344  |  0.37932  | 0.260131  | 0.126283  | 0.089793  |  0.144473  |
| growth_50_hmm_guardrail_quarterly     | recent          |       0.630969  |             -0.158177 |    0.000644342 |  0.503741 | 0.244652  | 0.10274   | 0.0996665 |  0.0492008 |
| aggressive_55_static_quarterly        | covid           |       0.0621914 |             -0.169227 |    0.00123223  |  0.554019 | 0.205362  | 0.10207   | 0.0904004 |  0.0481494 |
| aggressive_55_static_quarterly        | inflation_shock |      -0.177883  |             -0.220538 |    0.00084057  |  0.549902 | 0.190336  | 0.100959  | 0.107878  |  0.0509251 |
| aggressive_55_static_quarterly        | recent          |       0.693439  |             -0.181512 |    0.000610579 |  0.553292 | 0.195458  | 0.102597  | 0.0995228 |  0.0491301 |
| aggressive_55_static_buy_hold         | covid           |       0.060665  |             -0.201403 |    0           |  0.716835 | 0.177628  | 0.055377  | 0.0240235 |  0.0261364 |
| aggressive_55_static_buy_hold         | inflation_shock |      -0.2075    |             -0.256997 |    0           |  0.796603 | 0.100464  | 0.0439796 | 0.0389666 |  0.019987  |
| aggressive_55_static_buy_hold         | recent          |       0.910409  |             -0.214491 |    0           |  0.837125 | 0.064807  | 0.0518876 | 0.0304366 |  0.0157436 |
| aggressive_55_hmm_guardrail_quarterly | covid           |       0.0174453 |             -0.169227 |    0.00414393  |  0.404744 | 0.23652   | 0.134343  | 0.0746708 |  0.149723  |
| aggressive_55_hmm_guardrail_quarterly | inflation_shock |      -0.147115  |             -0.191366 |    0.00497012  |  0.427878 | 0.212275  | 0.126021  | 0.089566  |  0.14426   |
| aggressive_55_hmm_guardrail_quarterly | recent          |       0.693439  |             -0.15088  |    0.000610579 |  0.553292 | 0.195458  | 0.102597  | 0.0995228 |  0.0491301 |

## Interpretation

The guardrail pass rate across base portfolios is 100.0% under the rule: positive MDD improvement, positive Calmar delta, and CAGR drag no worse than 0.75 percentage points versus the same base portfolio rebalanced quarterly.

If this pass rate is broad, the HMM guardrail is not merely an artifact of the current 45/25/15/10/5 allocation. If it concentrates in only one base, the static allocation choice is doing most of the work.

## Rebalance Policies

| model                                 | rebalance_frequency   |
|:--------------------------------------|:----------------------|
| defensive_35_static_quarterly         | quarterly             |
| defensive_35_static_buy_hold          | buy_hold              |
| defensive_35_hmm_guardrail_quarterly  | quarterly             |
| balanced_40_static_quarterly          | quarterly             |
| balanced_40_static_buy_hold           | buy_hold              |
| balanced_40_hmm_guardrail_quarterly   | quarterly             |
| current_45_static_quarterly           | quarterly             |
| current_45_static_buy_hold            | buy_hold              |
| current_45_hmm_guardrail_quarterly    | quarterly             |
| growth_50_static_quarterly            | quarterly             |
| growth_50_static_buy_hold             | buy_hold              |
| growth_50_hmm_guardrail_quarterly     | quarterly             |
| aggressive_55_static_quarterly        | quarterly             |
| aggressive_55_static_buy_hold         | buy_hold              |
| aggressive_55_hmm_guardrail_quarterly | quarterly             |