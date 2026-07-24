# Stage 33 Causal DAG Allocation Stress Test

## Status

This is a strong causal assumption stress test. It does not replace the Stage 32 canonical conclusion that the supported final model is the 2-state HMM guardrail. Stage 17-20 graph and DML results are treated here as if they were strong causal allocation priors only for this experiment.

## Design

- Base portfolio: `current_45` diversified policy.
- Benchmarks: static quarterly diversified, Stage 32 final HMM guardrail, DAG overlay, and DAG + HMM guardrail.
- Rebalance/accounting: quarterly, long-only, drift-aware, `2bps` transaction cost.
- DAG tilt: max total absolute tilt `15%`, max single-asset tilt `8%`.
- Uncertain graph-only edges are weakly weighted; Stage 20 fragile exclusions receive zero weight.

## DAG Edge Scorecard

| edge_id                            | theme                    | regime   | source            | target                       | target_asset   | target_type   |   edge_sign |   raw_strength |   robustness_multiplier | robustness_status     |   final_strength | allocation_relevance                                 |
|:-----------------------------------|:-------------------------|:---------|:------------------|:-----------------------------|:---------------|:--------------|------------:|---------------:|------------------------:|:----------------------|-----------------:|:-----------------------------------------------------|
| stress_to_dispersion_regime1_1d    | stress_to_dispersion     | 1        | FinancialStress   | daily_cross_asset_dispersion | risk_proxy     | risk_proxy    |           1 |       0.630964 |                    1    | targeted_dml_pass     |        0.630964  | cash floor and de-risking trigger validation         |
| stress_to_dispersion_regimeall_1d  | stress_to_dispersion     | all      | FinancialStress   | daily_cross_asset_dispersion | risk_proxy     | risk_proxy    |           1 |       1        |                    0.25 | diagnostic_graph_only |        0.25      | cash floor and de-risking trigger validation         |
| stress_to_dispersion_regimeall_5d  | stress_to_dispersion     | all      | FinancialStress   | daily_cross_asset_dispersion | risk_proxy     | risk_proxy    |           1 |       1        |                    0.25 | diagnostic_graph_only |        0.25      | full-sample stable lagged transmission candidate     |
| stress_to_dispersion_regimeall_21d | stress_to_dispersion     | all      | FinancialStress   | daily_cross_asset_dispersion | risk_proxy     | risk_proxy    |           1 |       1        |                    0.25 | diagnostic_graph_only |        0.25      | full-sample stable lagged transmission candidate     |
| policy_to_stress_regimeall_63d     | policy_to_stress         | all      | PolicyTightness   | FinancialStress              | risk_proxy     | risk_proxy    |          -1 |       0.87785  |                    0.25 | diagnostic_graph_only |        0.219463  | full-sample stable lagged transmission candidate     |
| stress_to_dispersion_regime0_5d    | stress_to_dispersion     | 0        | FinancialStress   | daily_cross_asset_dispersion | risk_proxy     | risk_proxy    |           1 |       0.781966 |                    0.25 | diagnostic_graph_only |        0.195491  | regime-specific stable lagged transmission candidate |
| stress_to_vix_regime1              | stress_to_vix            | 1        | FinancialStress   | daily_vix_level              | risk_proxy     | risk_proxy    |           1 |       0.41028  |                    0.25 | diagnostic_graph_only |        0.10257   | stress proxy redundancy check                        |
| inflation_to_commodities_regime1   | inflation_to_commodities | 1        | InflationPressure | daily_commodity_return       | DBC            | asset_return  |           1 |       0.402918 |                    0.25 | diagnostic_graph_only |        0.100729  | DBC inflation-hedge validation                       |
| inflation_to_commodities_regime0   | inflation_to_commodities | 0        | InflationPressure | daily_commodity_return       | DBC            | asset_return  |           1 |       0.36485  |                    0.25 | diagnostic_graph_only |        0.0912125 | DBC inflation-hedge validation                       |
| inflation_to_commodities_regimeall | inflation_to_commodities | all      | InflationPressure | daily_commodity_return       | DBC            | asset_return  |           1 |       0.342267 |                    0.25 | diagnostic_graph_only |        0.0855669 | DBC inflation-hedge validation                       |
| stress_to_vix_regimeall            | stress_to_vix            | all      | FinancialStress   | daily_vix_level              | risk_proxy     | risk_proxy    |           1 |       0.333715 |                    0.25 | diagnostic_graph_only |        0.0834287 | stress proxy redundancy check                        |
| stress_to_vix_regime0              | stress_to_vix            | 0        | FinancialStress   | daily_vix_level              | risk_proxy     | risk_proxy    |           1 |       0.323747 |                    0.25 | diagnostic_graph_only |        0.0809368 | stress proxy redundancy check                        |
| inflation_to_gold_regime0          | inflation_to_gold        | 0        | InflationPressure | daily_gold_return            | GLD            | asset_return  |           1 |       0.23254  |                    0.25 | diagnostic_graph_only |        0.0581351 | GLD inflation/stress hedge validation                |
| inflation_to_gold_regimeall        | inflation_to_gold        | all      | InflationPressure | daily_gold_return            | GLD            | asset_return  |           1 |       0.202017 |                    0.25 | diagnostic_graph_only |        0.0505044 | GLD inflation/stress hedge validation                |
| policy_to_duration_regime1         | policy_to_duration       | 1        | PolicyTightness   | daily_duration_return        | TLT            | asset_return  |          -1 |       0.193651 |                    0.25 | diagnostic_graph_only |        0.0484128 | TLT hedge/cap conditioning                           |
| policy_to_duration_regime0         | policy_to_duration       | 0        | PolicyTightness   | daily_duration_return        | TLT            | asset_return  |          -1 |       0.163064 |                    0.25 | diagnostic_graph_only |        0.0407659 | TLT hedge/cap conditioning                           |
| policy_to_duration_regimeall       | policy_to_duration       | all      | PolicyTightness   | daily_duration_return        | TLT            | asset_return  |          -1 |       0.121732 |                    0.25 | diagnostic_graph_only |        0.030433  | TLT hedge/cap conditioning                           |
| stress_to_equity_regime0           | stress_to_equity         | 0        | FinancialStress   | daily_equity_return          | SPY            | asset_return  |           1 |       0.1042   |                    0.25 | diagnostic_graph_only |        0.02605   | SPY risk throttle validation                         |

## Performance

| model                            |   days |      CAGR |   Sharpe |   Sortino |   max_drawdown |   Calmar |   avg_turnover |   total_return |
|:---------------------------------|-------:|----------:|---------:|----------:|---------------:|---------:|---------------:|---------------:|
| static_quarterly_diversified     |   3462 | 0.0870933 | 0.962907 |   1.22548 |      -0.220911 | 0.394245 |    0.000688047 |        2.14947 |
| stage32_hmm_guardrail_quarterly  |   3462 | 0.0846882 | 0.977084 |   1.25855 |      -0.191956 | 0.441187 |    0.00153113  |        2.05508 |
| dag_overlay_quarterly            |   3462 | 0.0841996 | 0.937234 |   1.17921 |      -0.213444 | 0.394481 |    0.00162119  |        2.03623 |
| dag_plus_hmm_guardrail_quarterly |   3462 | 0.0815549 | 0.938964 |   1.18816 |      -0.192332 | 0.424031 |    0.00214963  |        1.93604 |

## Benchmark Deltas

| model                            | benchmark                       |   cagr_delta_pct_points |   sharpe_delta |   sortino_delta |   mdd_improvement_pct_points |   calmar_delta |   turnover_delta |
|:---------------------------------|:--------------------------------|------------------------:|---------------:|----------------:|-----------------------------:|---------------:|-----------------:|
| stage32_hmm_guardrail_quarterly  | static_quarterly_diversified    |              -0.240505  |      0.0141772 |       0.0330721 |                    2.89558   |    0.0469412   |      0.000843084 |
| dag_overlay_quarterly            | static_quarterly_diversified    |              -0.289369  |     -0.0256732 |      -0.0462617 |                    0.74672   |    0.000235281 |      0.000933145 |
| dag_plus_hmm_guardrail_quarterly | static_quarterly_diversified    |              -0.553843  |     -0.0239432 |      -0.0373134 |                    2.8579    |    0.0297854   |      0.00146158  |
| dag_overlay_quarterly            | stage32_hmm_guardrail_quarterly |              -0.0488641 |     -0.0398503 |      -0.0793337 |                   -2.14886   |   -0.0467059   |      9.00617e-05 |
| dag_plus_hmm_guardrail_quarterly | stage32_hmm_guardrail_quarterly |              -0.313338  |     -0.0381204 |      -0.0703854 |                   -0.0376803 |   -0.0171558   |      0.000618496 |

## Turnover and Cost

| model                            |   avg_turnover |   total_turnover |   total_transaction_cost_drag |   rebalance_events |   days_turnover_gt_5pct |   days_turnover_gt_10pct |
|:---------------------------------|---------------:|-----------------:|------------------------------:|-------------------:|------------------------:|-------------------------:|
| static_quarterly_diversified     |    0.000688047 |          2.38202 |                   0.000476404 |                 53 |                      18 |                        2 |
| stage32_hmm_guardrail_quarterly  |    0.00153113  |          5.30077 |                   0.00106015  |                 53 |                      20 |                        7 |
| dag_overlay_quarterly            |    0.00162119  |          5.61257 |                   0.00112251  |                 53 |                      33 |                       20 |
| dag_plus_hmm_guardrail_quarterly |    0.00214963  |          7.44201 |                   0.0014884   |                 53 |                      33 |                       23 |

## Crisis Behavior

| model                            | period          |   period_return |   period_max_drawdown |   avg_turnover |   avg_SPY |   avg_TLT |   avg_GLD |   avg_DBC |   avg_CASH |
|:---------------------------------|:----------------|----------------:|----------------------:|---------------:|----------:|----------:|----------:|----------:|-----------:|
| static_quarterly_diversified     | covid           |      0.0683922  |             -0.153004 |    0.00130845  |  0.453009 |  0.255786 |  0.152817 | 0.0903548 |  0.0480318 |
| static_quarterly_diversified     | inflation_shock |     -0.177898   |             -0.220911 |    0.000878357 |  0.450906 |  0.238379 |  0.151686 | 0.108018  |  0.0510108 |
| static_quarterly_diversified     | recent          |      0.647564   |             -0.178692 |    0.000655874 |  0.452942 |  0.244399 |  0.153942 | 0.0995655 |  0.0491521 |
| stage32_hmm_guardrail_quarterly  | covid           |      0.0228465  |             -0.153004 |    0.00420522  |  0.300713 |  0.288036 |  0.186261 | 0.0745135 |  0.150476  |
| stage32_hmm_guardrail_quarterly  | inflation_shock |     -0.147344   |             -0.191956 |    0.00494948  |  0.329904 |  0.259948 |  0.176322 | 0.0897724 |  0.144053  |
| stage32_hmm_guardrail_quarterly  | recent          |      0.647564   |             -0.148167 |    0.000655874 |  0.452942 |  0.244399 |  0.153942 | 0.0995655 |  0.0491521 |
| dag_overlay_quarterly            | covid           |      0.0445541  |             -0.168138 |    0.00204567  |  0.448871 |  0.260849 |  0.156357 | 0.0809877 |  0.0529348 |
| dag_overlay_quarterly            | inflation_shock |     -0.169424   |             -0.213444 |    0.00129523  |  0.398622 |  0.251564 |  0.175978 | 0.0879965 |  0.0858395 |
| dag_overlay_quarterly            | recent          |      0.6618     |             -0.168538 |    0.001691    |  0.464683 |  0.220962 |  0.153605 | 0.126226  |  0.0345239 |
| dag_plus_hmm_guardrail_quarterly | covid           |      0.00537222 |             -0.168138 |    0.00593436  |  0.319156 |  0.28553  |  0.183276 | 0.0634591 |  0.148579  |
| dag_plus_hmm_guardrail_quarterly | inflation_shock |     -0.146673   |             -0.192332 |    0.00422479  |  0.307526 |  0.264272 |  0.192213 | 0.067194  |  0.168795  |
| dag_plus_hmm_guardrail_quarterly | recent          |      0.6618     |             -0.14622  |    0.001691    |  0.464683 |  0.220962 |  0.153605 | 0.126226  |  0.0345239 |

## Subperiod Consistency

| model                            | subperiod     |   days |      CAGR |   Sharpe |   Sortino |   max_drawdown |   Calmar |   avg_turnover |   total_return |
|:---------------------------------|:--------------|-------:|----------:|---------:|----------:|---------------:|---------:|---------------:|---------------:|
| static_quarterly_diversified     | oos_2013_2016 |   1038 | 0.0499567 | 0.73321  |  1.00703  |     -0.101527  | 0.492053 |    0.000616348 |      0.222379  |
| static_quarterly_diversified     | oos_2017_2019 |    776 | 0.105118  | 1.68137  |  2.31986  |     -0.0964652 | 1.0897   |    0.000607341 |      0.360414  |
| static_quarterly_diversified     | oos_2020_2022 |    778 | 0.0461696 | 0.36224  |  0.454396 |     -0.220911  | 0.208996 |    0.000900184 |      0.149523  |
| static_quarterly_diversified     | oos_2023_2026 |    870 | 0.155605  | 1.63974  |  2.2872   |     -0.178692  | 0.870803 |    0.000655874 |      0.647564  |
| stage32_hmm_guardrail_quarterly  | oos_2013_2016 |   1038 | 0.0499567 | 0.73321  |  1.00703  |     -0.101527  | 0.492053 |    0.000616348 |      0.222379  |
| stage32_hmm_guardrail_quarterly  | oos_2017_2019 |    776 | 0.105118  | 1.68137  |  2.31986  |     -0.0964652 | 1.0897   |    0.000607341 |      0.360414  |
| stage32_hmm_guardrail_quarterly  | oos_2020_2022 |    778 | 0.0359096 | 0.311796 |  0.386377 |     -0.191956  | 0.187072 |    0.0046518   |      0.115073  |
| stage32_hmm_guardrail_quarterly  | oos_2023_2026 |    870 | 0.155605  | 1.63974  |  2.2872   |     -0.148167  | 1.0502   |    0.000655874 |      0.647564  |
| dag_overlay_quarterly            | oos_2013_2016 |   1038 | 0.0535529 | 0.791966 |  1.07866  |     -0.0766811 | 0.698385 |    0.0012367   |      0.239717  |
| dag_overlay_quarterly            | oos_2017_2019 |    776 | 0.0983936 | 1.52514  |  2.01604  |     -0.113258  | 0.868759 |    0.00162545  |      0.335084  |
| dag_overlay_quarterly            | oos_2020_2022 |    778 | 0.0325318 | 0.258334 |  0.315676 |     -0.213444  | 0.152414 |    0.00205187  |      0.103886  |
| dag_overlay_quarterly            | oos_2023_2026 |    870 | 0.158489  | 1.69266  |  2.38403  |     -0.168538  | 0.940376 |    0.001691    |      0.6618    |
| dag_plus_hmm_guardrail_quarterly | oos_2013_2016 |   1038 | 0.0535529 | 0.791966 |  1.07866  |     -0.0766811 | 0.698385 |    0.0012367   |      0.239717  |
| dag_plus_hmm_guardrail_quarterly | oos_2017_2019 |    776 | 0.0983936 | 1.52514  |  2.01604  |     -0.113258  | 0.868759 |    0.00162545  |      0.335084  |
| dag_plus_hmm_guardrail_quarterly | oos_2020_2022 |    778 | 0.021371  | 0.183889 |  0.220505 |     -0.192332  | 0.111115 |    0.00440334  |      0.0674616 |
| dag_plus_hmm_guardrail_quarterly | oos_2023_2026 |    870 | 0.158489  | 1.69266  |  2.38403  |     -0.14622   | 1.0839   |    0.001691    |      0.6618    |

## Interpretation

Against static quarterly diversified, the DAG overlay changed CAGR by `-0.29` percentage points and max drawdown by `0.75` percentage points.
Against the Stage 32 HMM guardrail, the standalone DAG overlay changed CAGR by `-0.05` percentage points and max drawdown by `-2.15` percentage points.
The combined DAG + HMM variant changed CAGR by `-0.31` percentage points and max drawdown by `-0.04` percentage points versus the HMM guardrail.

The correct reading is diagnostic: if performance improves, the result says the strong causal assumption is worth further scrutiny, not that the DAG has been validated as causal or that the final guardrail model should be replaced.