"""Saturated cell-level WLS, using explicit fixed-effect projection and CR1 inference."""

from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import t as student_t

from .aggregate import (
    GROUPS, KEYS, OUTCOMES, numeric, require_columns, validate_state_codes,
)


COMPARISONS = {
    "four_group": GROUPS,
    "BW_vs_BM": ("BW", "BM"),
    "BW_vs_WW": ("BW", "WW"),
}


def load_cells(path: Path) -> pd.DataFrame:
    cells = pd.read_csv(path, dtype={"state_fips": "string", "group": "string", "outcome": "string"})
    require_columns(cells, [*KEYS, "outcome", "mean", "denominator_weight"])
    if cells.empty:
        raise ValueError("The cell table is empty.")
    validate_state_codes(cells["state_fips"])
    year = numeric(cells["year"], "year")
    if ((year % 1) != 0).any() or not year.between(1900, 2200).all():
        raise ValueError("year must be an integer between 1900 and 2200.")
    cells["year"] = year.astype(int)
    if not cells["group"].isin(GROUPS).all():
        raise ValueError(f"Cell group must be one of {GROUPS}.")
    if not cells["outcome"].isin(OUTCOMES).all():
        raise ValueError(f"Unsupported outcome; supported outcomes are {OUTCOMES}.")
    if cells.duplicated([*KEYS, "outcome"]).any():
        raise ValueError("Duplicate state-year-group-outcome rows in the cell table.")
    cells["denominator_weight"] = numeric(cells["denominator_weight"], "denominator_weight")
    cells["mean"] = numeric(cells["mean"], "mean", missing_ok=True)
    if (cells["denominator_weight"] < 0).any():
        raise ValueError("Cell denominator weights cannot be negative.")
    eligible = cells["denominator_weight"].gt(0)
    if cells.loc[eligible, "mean"].isna().any():
        raise ValueError("Positive-weight cells must have finite outcome means.")
    rates = eligible & cells["outcome"].ne("log_wage_income")
    if not cells.loc[rates, "mean"].between(0, 1).all():
        raise ValueError("Rate/share cell means must be in [0, 1], before percentage-point scaling.")
    return cells


def fixed_effect_matrix(sample: pd.DataFrame) -> np.ndarray:
    """All three FE blocks; their joint span includes the intercept."""
    blocks = []
    for left, right in [("state_fips", "year"), ("state_fips", "group"), ("year", "group")]:
        labels = sample[left].astype(str) + "|" + sample[right].astype(str)
        blocks.append(pd.get_dummies(labels, dtype=float).to_numpy())
    return np.column_stack(blocks)


def fit_comparison(
    panel: pd.DataFrame, outcome: str, comparison: str, *, alpha: float,
    require_balanced: bool,
) -> dict:
    groups = COMPARISONS[comparison]
    expected_states = sorted(panel["state_fips"].unique())
    expected_years = sorted(panel["year"].unique())
    expected_n = len(expected_states) * len(expected_years) * len(groups)
    selected = panel.loc[panel["outcome"].eq(outcome) & panel["group"].isin(groups)].copy()
    zero_weight_cells = int(selected["denominator_weight"].eq(0).sum())
    sample = selected.loc[selected["denominator_weight"].gt(0)].copy()
    if set(sample["group"]) != set(groups):
        raise ValueError(f"{outcome}/{comparison}: at least one comparison group has no eligible cells.")
    n = len(sample)
    if require_balanced and n != expected_n:
        raise ValueError(
            f"{outcome}/{comparison}: balanced panel requires {expected_n} cells; found {n}. "
            "Resolve missing cells or explicitly omit --require-balanced."
        )
    states, state_names = pd.factorize(sample["state_fips"], sort=True)
    n_clusters = len(state_names)
    if n_clusters < 2:
        raise ValueError(f"{outcome}/{comparison}: state clustering requires at least two states.")
    if sample["year"].nunique() < 2:
        raise ValueError(f"{outcome}/{comparison}: at least two years are required.")
    weight = sample["denominator_weight"].to_numpy(dtype=float)
    weight = weight / weight.mean()
    root_weight = np.sqrt(weight)
    # All rates become percentage points; log income becomes 100 x log units.
    weighted_y = sample["mean"].to_numpy(dtype=float) * 100 * root_weight
    weighted_d = sample["bw_post"].to_numpy(dtype=float) * root_weight
    weighted_fe = fixed_effect_matrix(sample) * root_weight[:, None]
    targets = np.column_stack([weighted_y, weighted_d])
    coefficients, _, fe_rank, _ = np.linalg.lstsq(weighted_fe, targets, rcond=None)
    projected = targets - weighted_fe @ coefficients
    y_residual, d_residual = projected[:, 0], projected[:, 1]
    residual_treatment_ss = float(d_residual @ d_residual)
    raw_treatment_ss = float(weighted_d @ weighted_d)
    tolerance = np.finfo(float).eps * max(weighted_fe.shape) * max(1.0, raw_treatment_ss)
    if residual_treatment_ss <= tolerance:
        raise ValueError(
            f"{outcome}/{comparison}: treatment is absorbed by the fixed effects, "
            "or has effectively zero residual variation."
        )
    model_rank = int(fe_rank) + 1
    residual_df = n - model_rank
    if residual_df <= 0:
        raise ValueError(f"{outcome}/{comparison}: no residual degrees of freedom remain.")
    estimate = float(d_residual @ y_residual / residual_treatment_ss)
    residual = y_residual - estimate * d_residual
    state_scores = np.bincount(states, weights=d_residual * residual, minlength=n_clusters)
    correction = (n_clusters / (n_clusters - 1)) * ((n - 1) / residual_df)
    variance = float(correction * (state_scores @ state_scores) / residual_treatment_ss**2)
    if not np.isfinite(variance) or variance <= 0:
        raise ValueError(f"{outcome}/{comparison}: state-clustered variance is not strictly positive.")
    standard_error = float(np.sqrt(variance))
    inference_df = n_clusters - 1
    critical = float(student_t.ppf(1 - alpha / 2, df=inference_df))
    statistic = estimate / standard_error
    result = {
        "outcome": outcome,
        "comparison": comparison,
        "estimate": estimate,
        "std_error": standard_error,
        "ci_lower": estimate - critical * standard_error,
        "ci_upper": estimate + critical * standard_error,
        "p_value": float(2 * student_t.sf(abs(statistic), df=inference_df)),
        "t_statistic": statistic,
        "confidence_level": 1 - alpha,
        "units": "100 x log units" if outcome == "log_wage_income" else "percentage points",
        "n_cells": n,
        "n_states": n_clusters,
        "n_years": int(sample["year"].nunique()),
        "first_year": int(sample["year"].min()),
        "last_year": int(sample["year"].max()),
        "expected_cells": expected_n,
        "missing_cells": expected_n - n,
        "zero_weight_cells": zero_weight_cells,
        "cell_coverage": n / expected_n,
        "fixed_effect_rank": int(fe_rank),
        "model_rank": model_rank,
        "residual_df": residual_df,
        "inference_df": inference_df,
        "cr1_correction": correction,
        "residual_treatment_ss": residual_treatment_ss,
        "residual_treatment_fraction": residual_treatment_ss / raw_treatment_ss,
    }
    return result


def estimate_models(
    panel: pd.DataFrame, *, treatment: str, pairwise: bool = False,
    outcomes: list[str] | None = None, alpha: float = 0.05, require_balanced: bool = False,
) -> tuple[pd.DataFrame, dict]:
    if not 0 < alpha < 1:
        raise ValueError("alpha must be strictly between 0 and 1.")
    available = set(panel["outcome"])
    chosen = outcomes or [name for name in OUTCOMES if name in available]
    if len(set(chosen)) != len(chosen):
        raise ValueError("Do not repeat outcome names.")
    if set(chosen).difference(available):
        raise ValueError(f"Requested outcomes absent from cells: {sorted(set(chosen) - available)}")
    comparisons = list(COMPARISONS) if pairwise else ["four_group"]
    rows = []
    for outcome in chosen:
        for comparison in comparisons:
            result = fit_comparison(
                panel, outcome, comparison, alpha=alpha, require_balanced=require_balanced,
            )
            result["treatment"] = treatment
            rows.append(result)
    metadata = {
        "formula": "mean ~ BW * exposure + state_year_FE + state_group_FE + year_group_FE",
        "regressor_of_interest": "BlackWoman_group_indicator x state_year_exposure",
        "weight": "outcome-specific denominator_weight, normalized to mean 1",
        "outcome_scale": 100,
        "fixed_effects": ["state-year", "state-group", "year-group"],
        "covariance": "state-clustered CR1; effective model rank counts absorbed fixed effects",
        "inference": "Student t with number_of_states - 1 degrees of freedom",
        "confidence_level": 1 - alpha,
        "treatment": treatment,
        "require_balanced": require_balanced,
        "outcomes": chosen,
        "comparisons": comparisons,
        "models": rows,
    }
    return pd.DataFrame(rows), metadata
