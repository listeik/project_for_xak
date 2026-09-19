"""Explicit research inputs. Original CASE_INPUT files are never overwritten."""
from __future__ import annotations

from typing import Annotated, Literal
from pydantic import BaseModel, ConfigDict, Field, model_validator

Nonnegative = Annotated[float, Field(strict=True, ge=0, le=1e9, allow_inf_nan=False)]
Factor = Annotated[float, Field(strict=True, ge=0, le=10, allow_inf_nan=False)]


class ResearchInput(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class ExtraSource(ResearchInput):
    source_id: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,15}$")
    name: str = Field(min_length=1, max_length=100)
    capacity_t_per_year: Nonnegative
    variable_cost_mln_per_t: Nonnegative
    reservation_rate_mln_per_t_year_capacity: Nonnegative = 0.0
    take_or_pay_share: Annotated[float, Field(strict=True, ge=0, le=1)] = 0.0
    lead_time_min_value: Annotated[float, Field(strict=True, ge=0, le=36)] = 6.0
    lead_time_max_value: Annotated[float, Field(strict=True, ge=0, le=36)] = 6.0
    lead_time_unit: Literal["month", "week"] = "month"
    available_from_year: int = Field(strict=True, ge=2035, le=2045)
    reliability_profile: str = "scenario only; no probability assigned"
    notes: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def lead_range(self):
        if self.lead_time_min_value > self.lead_time_max_value:
            raise ValueError("Минимальный lead time не может превышать максимальный.")
        if self.source_id in {"A", "B", "C", "D", "E", "HUB", "DEMAND"}:
            raise ValueError("ID дополнительного источника конфликтует с исходным набором.")
        return self


class FutureDemand(ResearchInput):
    year: int = Field(strict=True, ge=2041, le=2045)
    base_total_t: Nonnegative
    base_critical_t: Nonnegative
    low_total_t: Nonnegative
    high_total_t: Nonnegative

    @model_validator(mode="after")
    def demand_order(self):
        if not self.low_total_t <= self.base_total_t <= self.high_total_t:
            raise ValueError("Требуется LOW ≤ BASE ≤ HIGH.")
        if self.base_critical_t > self.base_total_t:
            raise ValueError("Критический спрос является частью общего.")
        return self


class ResearchConfig(ResearchInput):
    config_id: str = Field(pattern=r"^TEAM_[A-Za-z0-9_-]+$", max_length=80)
    assumptions: str = Field(min_length=20, max_length=5000)
    extra_sources: list[ExtraSource] = Field(default_factory=list, max_length=7)
    future_demand: list[FutureDemand] = Field(default_factory=list, max_length=5)
    future_capex_limit_mln: Nonnegative
    future_policy: Literal["retain_service_reserve_storage_emergency_and_prices_no_additional_stress"]

    @model_validator(mode="after")
    def unique_extension(self):
        ids = [source.source_id for source in self.extra_sources]
        years = sorted(row.year for row in self.future_demand)
        if len(ids) != len(set(ids)) or years != list(range(2041, 2041 + len(years))):
            raise ValueError("Источники должны быть уникальны, будущие годы — непрерывны начиная с 2041.")
        return self


class SourceShock(ResearchInput):
    delivery_factor: Annotated[float, Field(strict=True, ge=0, le=1)] = 1.0
    price_factor: Factor = 1.0
    capacity_factor: Annotated[float, Field(strict=True, ge=0, le=1)] = 1.0
    delay_months: Annotated[float, Field(strict=True, ge=0, le=12)] = 0.0


class ResearchShock(ResearchInput):
    scenario_id: str = Field(pattern=r"^TEAM_[A-Za-z0-9_-]+$", max_length=80)
    description: str = Field(min_length=10, max_length=2000)
    start_year: int = Field(strict=True, ge=2035, le=2045)
    end_year: int = Field(strict=True, ge=2035, le=2045)
    demand_factor: Factor = 1.0
    sources: dict[str, SourceShock] = Field(default_factory=dict, max_length=12)
    combination_rule: Literal["standalone", "multiply_independent_effects"] = "standalone"

    @model_validator(mode="after")
    def period(self):
        if self.start_year > self.end_year:
            raise ValueError("Начало шока должно предшествовать окончанию.")
        return self


class ContractLock(ResearchInput):
    shock_year: int = Field(strict=True, ge=2036, le=2045)
    baseline_orders: dict[int, dict[str, Nonnegative]]
    baseline_reservations: dict[int, dict[str, Nonnegative]] | None = None
    baseline_investments: dict[str, int | None]
    baseline_initial_inventory_t: Nonnegative
    baseline_c_lead_months: Nonnegative
    baseline_d_lead_months: Nonnegative
    policy: Literal["freeze_annual_contract_if_first_order_precedes_shock"] = "freeze_annual_contract_if_first_order_precedes_shock"
