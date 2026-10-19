# Input contracts

## Harmonized ACS person records

Use a CSV containing one person record per row. Apply the same extract and geographic/sample definitions consistently across years. This repository starts from harmonized variables: the column names below are not raw IPUMS variable names or guessed translations of its numeric codes.

| Column | Type and meaning |
| --- | --- |
| `state_fips` | Two-digit state code, preserving the leading zero. Geographic inclusions such as DC should be decided consistently before export. |
| `year` | Integer survey year. Defaults retain 2015–2024. |
| `age` | Integer age. The analytical sample retains 25–64. |
| `race` | `black`, `white`, or another label. Only `black` and `white` are retained. Document how multiracial responses are treated. |
| `sex` | `female` or `male` in the retained sample, reflecting the analytical grouping in the paper. |
| `hispanic` | `0` for non-Hispanic and `1` for Hispanic. Unknown status must be missing, not recoded to zero. Only zero is retained. |
| `person_weight` | Finite, strictly positive person weight in the retained sample. |
| `employed` | `0` or `1`, defined for every retained person. |
| `in_labour_force` | `0` or `1`, defined for every retained person. |
| `self_employed` | `0` or `1`, defined for every retained person. Code non-employed people as zero for this population rate. Document incorporated/unincorporated coverage. |
| `wage_income` | Annual wage-and-salary income; finite numeric values or missing. The wage outcome uses `log(wage_income)` among positive earners. Remove NIU/missing/top-code sentinel values according to the codebook before export. |

The three employment indicators must be nonmissing in the retained sample. Employment must imply labour-force participation; self-employment must imply employment. A value of zero for wage income does not imply that the wage observation is in the wage denominator. Wage income measures annual earnings, not an hourly wage. If income is converted to constant dollars, document the price series and base year.

The code does not impose additional restrictions such as citizenship, household type, civilian status, or education. Apply any such decisions during harmonization and document them. Record the treatment of ACS 2020 and sample comparability; the CSV schema cannot resolve survey-release differences.

### Optional occupation outcomes

Include `has_occupation` (`0` or `1`) and any subset of these columns:

- `managerial_professional`
- `customer_facing_top_quartile`
- `interpersonal_top_quartile`
- `managerial_onet_top_quartile`
- `subjective_evaluation_top_quartile`

Each supplied outcome must equal zero or one for all employed people with a valid occupation. Missing classifications among those people are rejected, so the denominator does not silently become the subset matched to O*NET. If a classification cannot be obtained, resolve the mapping or make an explicit sample restriction upstream. Values outside that denominator may be missing.

The occupation denominator is `employed == 1 and has_occupation == 1`. Supply and document the ACS occupation vintage, SOC/O*NET crosswalk, one-to-many mapping weights, index item definitions, normalization, reference population, quartile cutoffs, and treatment of unmatched codes. The pipeline does not manufacture these choices from the labels alone.

## Policy table

Supply exactly one row for every state represented in the cell panel, with:

| Column | Meaning |
| --- | --- |
| `state_fips` | Same two-digit code as in the person data. |
| `status` | `adopted` or `not_adopted`, for the specific broad employment protection being studied. |
| `effective_date` | `YYYY-MM-DD` for adopted states. Blank for `not_adopted`. Use the effective date, not the signature date. |
| `verified_through` | `YYYY-MM-DD`, at least December 31 of the final estimation year. Both statuses require this coverage date. |
| `source_url` | Nonempty HTTP(S) source reference supporting the coding. It is stored, not automatically verified by the program. |
| `scope_note` | Nonempty description of the covered employment scope and any exclusions. |

`not_adopted` means that no qualifying policy was in effect through the verification date. An absent row is unknown and causes an error; it is never treated as an untreated state. An adopted date may fall after the analytical window. The table represents a single absorbing adoption per state, so repeal, interrupted coverage, and changing scope require a richer policy panel before estimation.

The template deliberately contains no policy facts. Broad employment protection, school-only action, and public-agency orders must be distinguished in the source work. This implementation estimates the broad-employment definition supplied by the user; an “any-action” definition would require its own documented table and separate run.

Treatment choices:

- `any_exposure`: one if the policy is effective on or before December 31 of that year.
- `full_year`: one if the policy is effective on or before January 1 of that year.
- `fractional_year`: fraction of calendar days the policy is in effect, including the effective date. Leap years use 366 days.

Choose `--treatment` explicitly. These conventions can differ in the adoption year, so the program does not silently select one as the paper's original convention.

## Aggregated cells

`aggregate` produces one row per `state_fips, year, group, outcome`, with groups `BW`, `BM`, `WW`, and `WM`:

| Column | Meaning |
| --- | --- |
| `mean` | Weighted cell mean in natural units, or missing when no eligible records exist. |
| `denominator_weight` | Sum of person weights among outcome-eligible records; the regression weight. |
| `weighted_sum` | Sum of outcome × person weight among eligible records. |
| `n_eligible` | Unweighted eligible record count. |
| `weight_square_sum` | Sum of squared person weights among eligible records. |
| `effective_n` | Kish descriptive effective count, weight sum squared divided by sum of squared weights. This is not a survey-design-adjusted sample size. |
| `population_weight` | Weight of the full retained demographic cell. |
| `n_sample` | Unweighted count of the full retained demographic cell. |

Population rates use the full retained demographic cell. Positive-earner log wage uses positive income only. Occupational outcomes use the employed-with-occupation denominator. Empty outcome cells are retained with zero weight and missing means, then excluded explicitly from estimation. `--require-balanced` requires every state × year × selected-group combination to remain available for each model. Without that flag, cell coverage and excluded-cell counts remain in output metadata.

An independently prepared cell CSV must include at least `state_fips, year, group, outcome, mean, denominator_weight`. Duplicate keys, negative/nonfinite weights, positive-weight missing means, and invalid values for implemented outcomes cause an error.

## Keeping data private

Raw records, extracts, policy working notes, and generated outputs belong in ignored `data/` and `outputs/` directories. Follow the access and redistribution terms attached to each input. The repository contains no person records or manuscript PDFs.
