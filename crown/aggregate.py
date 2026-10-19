"""Construct denominator-specific ACS cells without loading all records at once."""

from pathlib import Path

import numpy as np
import pandas as pd


KEYS = ["state_fips", "year", "group"]
GROUPS = ("BW", "BM", "WW", "WM")
RATE_OUTCOMES = {
    "employment_rate": "employed",
    "labour_force_participation": "in_labour_force",
    "self_employment_rate": "self_employed",
}
OCCUPATION_OUTCOMES = (
    "managerial_professional",
    "customer_facing_top_quartile",
    "interpersonal_top_quartile",
    "managerial_onet_top_quartile",
    "subjective_evaluation_top_quartile",
)
OUTCOMES = (*RATE_OUTCOMES, "log_wage_income", *OCCUPATION_OUTCOMES)
REQUIRED_PEOPLE = (
    "state_fips", "year", "age", "race", "sex", "hispanic", "person_weight",
    "employed", "in_labour_force", "self_employed", "wage_income",
)
SUM_COLUMNS = (
    "weighted_sum", "denominator_weight", "weight_square_sum", "n_eligible",
    "population_weight", "n_sample",
)


def require_columns(frame: pd.DataFrame, columns: tuple | list) -> None:
    missing = sorted(set(columns).difference(frame.columns))
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(missing)}")


def validate_state_codes(series: pd.Series) -> None:
    """Enforce formatting without silently guessing the geographical universe."""
    valid = series.astype("string").str.fullmatch(r"\d{2}").fillna(False)
    if not valid.all():
        raise ValueError("state_fips must contain two-digit strings, such as 01.")


def numeric(series: pd.Series, name: str, *, missing_ok: bool = False) -> pd.Series:
    values = pd.to_numeric(series, errors="raise").astype(float)
    if np.isinf(values).any() or (not missing_ok and values.isna().any()):
        raise ValueError(f"{name} contains missing or nonfinite values.")
    return values


def binary(series: pd.Series, name: str) -> pd.Series:
    values = numeric(series, name)
    if not values.isin([0, 1]).all():
        raise ValueError(f"{name} must contain only 0 and 1 in its denominator.")
    return values


def prepare_sample(chunk: pd.DataFrame, start_year: int, end_year: int) -> pd.DataFrame:
    require_columns(chunk, REQUIRED_PEOPLE)
    year = numeric(chunk["year"], "year")
    age = numeric(chunk["age"], "age", missing_ok=True)
    if ((year % 1) != 0).any() or ((age.dropna() % 1) != 0).any():
        raise ValueError("year and nonmissing age must be integers.")
    hispanic = numeric(chunk["hispanic"], "hispanic", missing_ok=True)
    if not hispanic.dropna().isin([0, 1]).all():
        raise ValueError("hispanic must be 0, 1, or missing.")
    selected = (
        year.between(start_year, end_year)
        & age.between(25, 64)
        & hispanic.eq(0)
        & chunk["race"].isin(["black", "white"])
    )
    frame = chunk.loc[selected].copy()
    if frame.empty:
        return frame
    validate_state_codes(frame["state_fips"])
    if not frame["sex"].isin(["female", "male"]).all():
        raise ValueError("sex must be female or male in the retained analytical sample.")
    frame["year"] = year.loc[selected].astype(int)
    frame["group"] = (
        frame["race"].map({"black": "B", "white": "W"})
        + frame["sex"].map({"female": "W", "male": "M"})
    )
    frame["person_weight"] = numeric(frame["person_weight"], "person_weight")
    if (frame["person_weight"] <= 0).any():
        raise ValueError("person_weight must be strictly positive in the retained sample.")
    for column in RATE_OUTCOMES.values():
        frame[column] = binary(frame[column], column)
    if (frame["employed"] > frame["in_labour_force"]).any():
        raise ValueError("Employment must imply labour-force participation.")
    if (frame["self_employed"] > frame["employed"]).any():
        raise ValueError("self_employed cannot equal 1 for a non-employed person.")
    frame["wage_income"] = numeric(frame["wage_income"], "wage_income", missing_ok=True)
    return frame


def summarize_outcome(
    frame: pd.DataFrame, outcome: str, values: pd.Series, eligible: pd.Series
) -> pd.DataFrame:
    weight = frame["person_weight"]
    eligible_weight = weight.where(eligible, 0.0)
    summary = frame[KEYS].copy()
    summary["weighted_sum"] = values.where(eligible, 0.0) * eligible_weight
    summary["denominator_weight"] = eligible_weight
    summary["weight_square_sum"] = eligible_weight**2
    summary["n_eligible"] = eligible.astype(int)
    summary["population_weight"] = weight
    summary["n_sample"] = 1
    summary = summary.groupby(KEYS, observed=True, sort=False).sum()
    summary["outcome"] = outcome
    return summary.reset_index().set_index([*KEYS, "outcome"])


def aggregate_people(
    path: Path, *, start_year: int = 2015, end_year: int = 2024,
    chunksize: int = 250_000,
) -> tuple[pd.DataFrame, dict]:
    if start_year > end_year or chunksize <= 0:
        raise ValueError("Specify an ordered year range and a positive chunk size.")
    total = None
    rows_read = 0
    rows_retained = 0
    occupation_columns = None
    reader = pd.read_csv(
        path, chunksize=chunksize,
        dtype={"state_fips": "string", "race": "string", "sex": "string"},
    )
    for chunk in reader:
        rows_read += len(chunk)
        if occupation_columns is None:
            occupation_columns = [name for name in OCCUPATION_OUTCOMES if name in chunk]
            if occupation_columns:
                require_columns(chunk, ["has_occupation"])
        frame = prepare_sample(chunk, start_year, end_year)
        rows_retained += len(frame)
        if frame.empty:
            continue
        pieces = []
        all_people = pd.Series(True, index=frame.index)
        for outcome, column in RATE_OUTCOMES.items():
            pieces.append(summarize_outcome(frame, outcome, frame[column], all_people))
        positive_income = frame["wage_income"].gt(0)
        log_income = np.log(frame["wage_income"].where(positive_income))
        pieces.append(summarize_outcome(frame, "log_wage_income", log_income, positive_income))
        if occupation_columns:
            has_occupation = binary(frame["has_occupation"], "has_occupation")
            occupation_sample = frame["employed"].eq(1) & has_occupation.eq(1)
            for outcome in occupation_columns:
                values = pd.Series(np.nan, index=frame.index)
                values.loc[occupation_sample] = binary(
                    frame.loc[occupation_sample, outcome], outcome
                )
                pieces.append(summarize_outcome(frame, outcome, values, occupation_sample))
        chunk_summary = pd.concat(pieces)
        total = chunk_summary if total is None else total.add(chunk_summary, fill_value=0)
    if total is None or total.empty:
        raise ValueError("No records remain after the sample restrictions.")
    cells = total.reset_index()
    if not np.isfinite(cells[list(SUM_COLUMNS)].to_numpy()).all():
        raise ValueError("Aggregation overflowed; inspect the input weights and outcomes.")
    positive = cells["denominator_weight"].gt(0)
    cells["mean"] = cells["weighted_sum"].div(cells["denominator_weight"].where(positive))
    cells["effective_n"] = cells["denominator_weight"].pow(2).div(
        cells["weight_square_sum"].where(positive)
    )
    cells[["n_eligible", "n_sample"]] = cells[["n_eligible", "n_sample"]].astype(int)
    cells = cells.sort_values(["outcome", *KEYS]).reset_index(drop=True)
    metadata = {
        "rows_read": rows_read,
        "rows_retained": rows_retained,
        "year_window": [start_year, end_year],
        "age_window": [25, 64],
        "sample": "non-Hispanic Black and White adults; female/male analytical groups",
        "outcomes": sorted(cells["outcome"].unique().tolist()),
        "cell_rows": len(cells),
        "zero_denominator_cells": int((~positive).sum()),
        "weight": "person_weight",
        "occupation_inputs": occupation_columns or [],
    }
    return cells, metadata
