"""Create annual exposure from explicitly documented, absorbing adoption dates."""

from pathlib import Path

import pandas as pd

from .aggregate import require_columns, validate_state_codes


TREATMENTS = ("any_exposure", "full_year", "fractional_year")
POLICY_COLUMNS = (
    "state_fips", "status", "effective_date", "verified_through", "source_url", "scope_note",
)


def load_policy(path: Path, *, last_year: int) -> pd.DataFrame:
    table = pd.read_csv(path, dtype="string")
    require_columns(table, POLICY_COLUMNS)
    validate_state_codes(table["state_fips"])
    if table["state_fips"].duplicated().any():
        raise ValueError("Policy table must have exactly one row per state.")
    if not table["status"].isin(["adopted", "not_adopted"]).all():
        raise ValueError("Policy status must be adopted or not_adopted.")
    for column in ["source_url", "scope_note", "verified_through"]:
        if table[column].fillna("").str.strip().eq("").any():
            raise ValueError(f"Policy table requires a nonempty {column} for every state.")
    if not table["source_url"].str.match(r"https?://\S+").fillna(False).all():
        raise ValueError("Policy source_url must be an HTTP(S) reference.")
    adopted = table["status"].eq("adopted")
    date_present = table["effective_date"].fillna("").str.strip().ne("")
    if not adopted.equals(date_present):
        raise ValueError("Only adopted rows must have an effective_date; other rows must leave it blank.")
    for column in ["effective_date", "verified_through"]:
        present = table[column].notna() & table[column].str.strip().ne("")
        if not table.loc[present, column].str.fullmatch(r"\d{4}-\d{2}-\d{2}").all():
            raise ValueError(f"{column} must use YYYY-MM-DD dates.")
        table[column] = pd.to_datetime(table[column].where(present), format="%Y-%m-%d", errors="raise")
    coverage_end = pd.Timestamp(year=last_year, month=12, day=31)
    if (table["verified_through"] < coverage_end).any():
        raise ValueError(f"Every policy row must be verified through {coverage_end.date()} or later.")
    if (table.loc[adopted, "effective_date"] > table.loc[adopted, "verified_through"]).any():
        raise ValueError("An adopted effective_date cannot follow verified_through.")
    return table


def attach_exposure(cells: pd.DataFrame, policy: pd.DataFrame, treatment: str) -> pd.DataFrame:
    if treatment not in TREATMENTS:
        raise ValueError(f"Unknown treatment convention: {treatment}")
    unknown = sorted(set(cells["state_fips"]).difference(policy["state_fips"]))
    if unknown:
        raise ValueError(f"Missing policy coverage for states: {', '.join(unknown)}")
    panel = cells.merge(
        policy[["state_fips", "status", "effective_date"]],
        on="state_fips", how="left", validate="many_to_one",
    )
    january = pd.to_datetime(panel["year"].astype(str) + "-01-01")
    next_january = pd.to_datetime((panel["year"] + 1).astype(str) + "-01-01")
    effective = panel["effective_date"]
    if treatment == "any_exposure":
        exposure = effective.lt(next_january).astype(float)
    elif treatment == "full_year":
        exposure = effective.le(january).astype(float)
    else:
        year_days = (next_january - january).dt.days
        days_covered = (next_january - effective).dt.days.clip(lower=0)
        exposure = (days_covered / year_days).clip(upper=1).fillna(0.0)
    panel["exposure"] = exposure
    panel["bw_post"] = panel["group"].eq("BW").astype(float) * exposure
    return panel
