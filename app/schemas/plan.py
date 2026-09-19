"""Validated REST inputs; physical feasibility remains the engine's responsibility."""

from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.constants import (
    DEFAULT_DISCOUNT_RATE,
    DEFAULT_INITIAL_INVENTORY,
    FIRST_YEAR,
    LAST_YEAR,
    SOURCES,
    YEARS,
)

# These generous numerical safety limits are not source/storage capacities.
# The engine still calculates, and reports, orders above real physical limits.
Quantity = Annotated[float, Field(strict=True, ge=0, le=1e9, allow_inf_nan=False)]
Year = Annotated[int, Field(strict=True, ge=FIRST_YEAR, le=LAST_YEAR)]
SourceId = Literal["A", "B", "C", "D", "E"]
Scenario = Literal["BASE", "MANDATORY_STRESS"]


class StrictInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class SourceOrders(StrictInput):
    A: Quantity
    B: Quantity
    C: Quantity
    D: Quantity
    E: Quantity


class InvestmentDecisions(StrictInput):
    zbo_year: Year | None = None
    option_c_year: Year | None = None
    exercise_c_year: Year | None = None
    isru_funding_year: Year | None = None


class PlanRequest(StrictInput):
    plan_id: Annotated[str, Field(strict=True, min_length=1, max_length=128)] = "untitled-plan"
    yearly_orders: dict[int, SourceOrders]
    yearly_reservations: dict[int, dict[SourceId, Quantity]] | None = None
    investments: InvestmentDecisions = Field(default_factory=InvestmentDecisions)
    scenario: Scenario = "BASE"
    demand_profile: Literal["BASE", "LOW", "HIGH"] = "BASE"
    initial_inventory_t: Quantity = DEFAULT_INITIAL_INVENTORY
    discount_rate: Annotated[
        float, Field(strict=True, ge=0, le=1, allow_inf_nan=False)
    ] = DEFAULT_DISCOUNT_RATE
    c_lead_months: Annotated[
        float,
        Field(
            strict=True,
            ge=SOURCES["C"]["lead_time_min_value"],
            le=SOURCES["C"]["lead_time_max_value"],
            allow_inf_nan=False,
        ),
    ] = SOURCES["C"]["lead_time_max_value"]
    d_lead_months: Annotated[
        float,
        Field(
            strict=True,
            ge=SOURCES["D"]["lead_time_min_value"],
            le=SOURCES["D"]["lead_time_max_value"],
            allow_inf_nan=False,
        ),
    ] = SOURCES["D"]["lead_time_max_value"]
    demand_factor: Annotated[
        float, Field(strict=True, ge=0, le=1000, allow_inf_nan=False)
    ] = 1.0
    price_factor: Annotated[
        float, Field(strict=True, ge=0, le=1000, allow_inf_nan=False)
    ] = 1.0

    @model_validator(mode="after")
    def separate_demand_research(self):
        if self.scenario == "MANDATORY_STRESS" and self.demand_profile != "BASE":
            raise ValueError("LOW/HIGH — отдельное исследование спроса; выберите режим BASE вместо MANDATORY_STRESS.")
        return self

    @field_validator("plan_id")
    @classmethod
    def nonempty_plan_id(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("Название плана не должно быть пустым.")
        return value

    @field_validator("yearly_orders", "yearly_reservations", mode="before")
    @classmethod
    def normalize_year_keys(cls, value):
        if value is None or not isinstance(value, dict):
            return value
        normalized = {}
        for key, item in value.items():
            if isinstance(key, bool) or not (
                isinstance(key, int) or (isinstance(key, str) and key.isascii() and key.isdigit())
            ):
                raise ValueError("Ключ года должен быть целым числом 2035–2040.")
            year = int(key)
            if year not in YEARS:
                raise ValueError(f"Год {year} вне горизонта 2035–2040.")
            if year in normalized:
                raise ValueError(f"Год {year} указан повторно.")
            normalized[year] = item
        return normalized

    @field_validator("yearly_orders")
    @classmethod
    def require_complete_horizon(cls, value):
        missing = sorted(set(YEARS) - set(value))
        if missing:
            raise ValueError("Отсутствуют годы плана: " + ", ".join(map(str, missing)))
        return value


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    input_version: str
    model_version: str
