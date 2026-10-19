# Estimation details

## Weighted cell means

For outcome `k`, the cell mean is the sum of `person_weight × outcome` over eligible people, divided by their summed person weights. Population-rate outcomes are employment, labour-force participation, and self-employment. Log wage income uses positive wage earners. Optional occupational shares use employed people with a valid occupation. Each cell's own outcome denominator becomes its regression weight.

The aggregation records sufficient sums across CSV chunks and combines them before taking ratios. It never averages chunk means. Empty outcome cells are represented by zero denominators and missing means.

## Saturated weighted least squares

The regressor of interest is the Black-woman indicator multiplied by state-year exposure. The nuisance design contains the full set of state-year, state-group, and year-group indicators; these blocks already span an intercept.

For numerical conditioning, regression weights are divided by their mean. Multiplying all weights by a constant leaves the coefficient and cluster covariance unchanged. The code then premultiplies outcome, regressor, and fixed effects by the square root of the normalized weight.

Least-squares projection removes the fixed effects from the weighted outcome and regressor. Let the resulting vectors be `y_tilde` and `d_tilde`. Then:

```text
beta = (d_tilde' y_tilde) / (d_tilde' d_tilde)
residual = y_tilde - beta × d_tilde
```

The fixed-effect blocks contain redundant columns. `numpy.linalg.lstsq` handles this with its rank-revealing singular-value solution; the effective fixed-effect rank, plus one for treatment, determines the model rank. The code rejects treatment with effectively zero residual variation after fixed effects. A `--require-balanced` option separately enforces a complete panel for each comparison and outcome.

## Inference

For state `s`, the treatment score is the sum of `d_tilde × residual` over that state's cells. With `G` states, `N` cells, and effective model rank `K`, the variance is:

```text
variance(beta) = [G / (G - 1)] × [(N - 1) / (N - K)]
                 × sum_s(score_s²) / (d_tilde' d_tilde)²
```

This is a one-way state-clustered sandwich variance with a CR1 finite-sample correction. P-values and confidence intervals use a Student t distribution with `G - 1` degrees of freedom. The denominator weight controls the WLS objective; it does not turn the regression into a complete ACS replicate-weight or survey-stratification analysis. This correction is an explicit implementation choice and can differ from software defaults used for manuscript tables.

All outcome means are multiplied by 100 immediately before estimation. The outputs therefore report percentage points for rates and 100 × log units for wage income. Standard errors and confidence limits use the same units.

## Comparisons and coverage

The `four_group` model contains `BW`, `BM`, `WW`, and `WM`. `--pairwise` adds `BW_vs_BM` and `BW_vs_WW`, each estimated independently with the same fixed-effect structure. These are coefficient estimates from their own samples; they are not mechanically averaged into the four-group coefficient.

The expected cell grid is constructed using all states and years found in the input panel. Missing cells, including zero-denominator cells, reduce observed coverage. The balanced-panel option rejects any such gap. The output records the actual state count, model rank, residual degrees of freedom, expected cells, observed cells, and the residual treatment sum of squares. Those diagnostics help distinguish a small coefficient from a specification with little identifying variation.

## Scope

This pipeline implements the paper's static saturated comparison. It does not implement an event study, a cohort-specific heterogeneous-treatment estimator, wild-cluster inference, occupation-index construction, or IPUMS extract downloading. The static coefficient can combine comparisons across adoption cohorts and treatment durations. Its causal interpretation is conditional on design assumptions and policy coding; a near-zero estimate is not a diagnostic that those assumptions hold.

The paper supplies the research question, sample window, grouping, outcome families, and fixed-effect structure. Exact extract identifiers, policy-source rows, detailed O*NET construction, some preparation choices, and the original estimation environment are not available in the repository. Current defaults and numerical conventions are documented here so a future run can be interpreted on its own terms.
