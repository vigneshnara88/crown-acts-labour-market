# CROWN Acts and labour-market outcomes

This project studies whether state protections against hair discrimination are associated with changes in Black women's employment, earnings, and occupational access. It implements the specification described in *A Narrow Law and Broad Outcomes: Hair-Discrimination Protections and Black Women's Labor Market* (Vignesh, April 2026).

The analysis uses IPUMS American Community Survey records for non-Hispanic Black and White adults aged 25–64, over 2015–2024. Person weights form state–year–race/sex cells. Weighted regressions compare Black women with the other groups while absorbing state-year, state-group, and year-group fixed effects. Standard errors are clustered by state.

## Reported in the paper

The manuscript's main estimates show small differential changes in employment, participation, and self-employment. The wage estimate is negative; that outcome conditions on positive earnings and can also reflect changes in the composition of earners.

| Outcome | Estimate | State-clustered SE | Reported p-value |
| --- | ---: | ---: | ---: |
| Employment rate | 0.004 | 0.355 | 0.99 |
| Labour-force participation | 0.006 | 0.342 | 0.99 |
| Self-employment rate | −0.021 | 0.150 | 0.89 |
| Log wage income × 100 | −2.210 | 1.128 | 0.05 |

Rates are in percentage points; wage income is in log points multiplied by 100. The [reported-estimates CSV](results/reported_estimates.csv) records manuscript Tables 1–3, including occupational outcomes and pairwise comparisons.

## Analysis pipeline

1. Supply harmonized person records with explicit employment, earnings, and demographic fields.
2. Aggregate population rates, positive-earner log income, and optional occupational shares using their respective denominators.
3. Join a source-documented policy table and choose an annual or fractional-year treatment definition.
4. Estimate the four-group specification and, optionally, Black women/Black men and Black women/White women comparisons.
5. Export estimates, state-clustered standard errors, confidence intervals, cell coverage, and the estimation settings.

```text
harmonized ACS records ──> weighted cells ──┐
                                         ├──> saturated WLS ──> estimates + metadata
documented state policy dates ────────────┘
```

## Setup and use

Python 3.11 or later is recommended. Install the analysis dependencies in an environment of your choice:

```bash
python -m pip install -r requirements.txt
```

Put private inputs in `data/`, following [the input contracts](docs/data.md). The files in `templates/` contain headers only. They are templates, not datasets.

```bash
python -m crown aggregate \
  --people data/acs_harmonized.csv \
  --output outputs/cells.csv

python -m crown estimate \
  --cells outputs/cells.csv \
  --policy data/policy_dates.csv \
  --treatment fractional_year \
  --pairwise \
  --require-balanced \
  --output outputs/estimates.csv
```

These examples use shell continuation characters for Bash; in PowerShell, enter each command on one line. The aggregation command reads person records in chunks and retains only cell summaries in memory. Estimation uses a dense fixed-effect design intended for a state-year-group panel, rather than individual records.

Each command also writes a JSON metadata file beside its CSV. Rate estimates are in percentage points and wage estimates in log points multiplied by 100. For example, an employment coefficient of `0.5` represents a change of half a percentage point. `--help` describes all options.

## Specification

For state `s`, year `t`, and race/sex group `g`:

```text
Y[s,t,g] = beta × BlackWoman[g] × Post[s,t]
           + state-year FE + state-group FE + year-group FE + error[s,t,g]
```

The four groups are Black women, Black men, White women, and White men. Each regression uses the outcome's denominator weight. The estimator projects both the outcome and treatment on the complete fixed-effect span before estimating `beta`. Redundant fixed-effect columns are handled by least squares; the effective model rank enters the finite-sample correction. Pairwise estimates retain the same fixed-effect structure within the selected two groups. See [estimation details](docs/methods.md).

## Data and interpretation

ACS extracts and their codebook, a verified state policy-date table, and the occupation crosswalk are required to connect the pipeline to research data. They are not bundled. The canonical input format makes sample definitions and denominators explicit; IPUMS special codes must be harmonized using the extract's own documentation before analysis. Optional occupational indicators are accepted as prepared inputs, rather than inferred from occupation numbers.

Manuscript estimates are recorded separately from the pipeline's output directory. Running the analysis requires the extract, policy definitions, occupation mapping, and preparation choices described in the data contract.

The coefficient is a comparative change under the stated specification. A causal interpretation requires the relevant parallel-trends assumptions. Staggered adoption and heterogeneous effects can affect the comparisons implicit in this regression; small estimates alone do not resolve that issue. These broad ACS outcomes do not directly measure hair-based screening in individual hiring decisions.

## Repository contents

| Path | Purpose |
| --- | --- |
| `crown/aggregate.py` | Sample restrictions and denominator-specific weighted aggregation |
| `crown/policy.py` | Documented policy inputs and annual/fractional exposure |
| `crown/estimate.py` | Saturated WLS and state-clustered inference |
| `crown/__main__.py` | Command-line pipeline |
| `docs/data.md` | Harmonized input and policy contracts |
| `docs/methods.md` | Estimator, inference, and implementation choices |
| `templates/` | Empty input schemas |
| `results/reported_estimates.csv` | Estimates transcribed from manuscript Tables 1–3 |

## Research sources

The paper cites IPUMS USA version 15.0 (Ruggles et al., 2024; DOI `10.18128/D010.V15.0`) and O*NET 30.3 Work Context and Work Activities measures. Record the actual release and extraction details used in any analysis. The paper's bibliography also discusses staggered-adoption methods by Callaway and Sant'Anna, Sun and Abraham, and Borusyak, Jaravel, and Spiess. Those alternative estimators are not implemented here.
