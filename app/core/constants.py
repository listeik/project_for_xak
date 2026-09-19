"""Load authoritative organiser inputs without duplicating case numbers in code.

All money is million constant-price 2035 monetary units, never plain dollars.
The YAML scenario and CSV files are distributed with the application.
"""

from __future__ import annotations

import csv
import hashlib
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
SCENARIO_DIR = PROJECT_ROOT / "scenarios"


def _rows(filename: str) -> list[dict]:
    with (DATA_DIR / filename).open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def _numeric(rows: list[dict], fields: tuple[str, ...]) -> list[dict]:
    for row in rows:
        for field in fields:
            row[field] = float(row[field]) if row[field] else None
    return rows


SOURCES = {
    row["source_id"]: row
    for row in _numeric(
        _rows("supply_sources.csv"),
        (
            "capacity_t_per_year",
            "variable_cost_mln_per_t",
            "reservation_rate_mln_per_t_year_capacity",
            "take_or_pay_share",
            "lead_time_min_value",
            "lead_time_max_value",
            "available_from_year",
        ),
    )
}
SOURCE_IDS = tuple(SOURCES)
DEMAND = {
    int(row["year"]): row
    for row in _numeric(
        _rows("demand.csv"),
        ("base_total_t", "base_critical_t", "low_total_t", "high_total_t"),
    )
}
YEARS = tuple(sorted(DEMAND))
FIRST_YEAR, LAST_YEAR = YEARS[0], YEARS[-1]
STORAGE = {
    row["storage_id"]: row
    for row in _numeric(
        _rows("storage_options.csv"),
        (
            "capacity_t",
            "loss_rate_on_throughput",
            "holding_cost_mln_per_t_year",
            "capex_mln",
            "fixed_opex_mln_per_year",
            "available_from_year",
        ),
    )
}
INVESTMENTS = {
    row["investment_id"]: row
    for row in _numeric(
        _rows("investment_options.csv"),
        (
            "option_fee_mln",
            "exercise_cost_mln",
            "total_capex_mln",
            "fixed_opex_mln_per_year",
        ),
    )
}
CONSTRAINTS = {
    row["constraint_id"]: row
    for row in _numeric(_rows("constraints.csv"), ("value",))
}
with (SCENARIO_DIR / "mandatory_stress.yaml").open(encoding="utf-8") as _file:
    MANDATORY_STRESS = yaml.safe_load(_file)

# Explicit model assumptions, distinct from the authoritative dictionaries above.
DAYS_PER_YEAR = 365
DAYS_PER_MONTH = DAYS_PER_YEAR / 12
DAYS_PER_WEEK = 7
DEFAULT_DISCOUNT_RATE = 0.08
DEFAULT_INITIAL_INVENTORY = 15.0
RESERVE_DAYS = CONSTRAINTS["RESERVE_45D"]["value"]
EPSILON = 1e-7
MODEL_VERSION = "2.0-analytics"

INPUT_FILES = tuple(sorted(DATA_DIR.glob("*.csv"))) + (
    SCENARIO_DIR / "mandatory_stress.yaml",
)
INPUT_VERSION = hashlib.sha256(
    b"".join(path.name.encode() + path.read_bytes() for path in INPUT_FILES)
).hexdigest()[:16]


def case_metadata() -> dict:
    """JSON-compatible input metadata for an API/UI without hidden constants."""
    return {
        "years": list(YEARS),
        "sources": list(SOURCES.values()),
        "demand": [{**row, "year": year} for year, row in DEMAND.items()],
        "storage": list(STORAGE.values()),
        "investments": list(INVESTMENTS.values()),
        "constraints": list(CONSTRAINTS.values()),
        "mandatory_stress": MANDATORY_STRESS,
        "input_version": INPUT_VERSION,
        "units": {"fuel": "t", "capacity": "t/year", "money": "million 2035 units"},
    }
