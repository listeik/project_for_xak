"""Request-scoped configuration; no mutable process-wide model state."""
from copy import deepcopy
import hashlib
import json

from app.core.constants import DEMAND, SOURCES, INPUT_VERSION


def model_data(plan: dict) -> tuple[dict, dict, tuple[int, ...]]:
    config = plan.get("research_config")
    if not config:
        return SOURCES, DEMAND, tuple(sorted(DEMAND))
    sources = {**SOURCES, **{row["source_id"]: {**row, "status": "TEAM_ASSUMPTION"} for row in config["extra_sources"]}}
    demand = {**DEMAND, **{row["year"]: row for row in config["future_demand"]}}
    return sources, demand, tuple(sorted(demand))


def config_version(plan: dict) -> str:
    config = plan.get("research_config")
    return INPUT_VERSION if not config else hashlib.sha256((INPUT_VERSION + json.dumps(config, sort_keys=True)).encode()).hexdigest()[:16]


def source_shock(plan: dict, source: str, year: int) -> dict:
    shock = plan.get("research_shock")
    return shock.get("sources", {}).get(source, {}) if shock and shock["start_year"] <= year <= shock["end_year"] else {}


def extended_plan(plan: dict, last_year: int = 2042) -> dict:
    """Synthetic demonstration, not a forecast or replacement of CASE_INPUT."""
    result = deepcopy(plan)
    result.update(scenario="BASE", demand_profile="BASE", research_shock=None, contract_lock=None, additional_orders={})
    result["research_config"] = {
        "config_id": f"TEAM_EXTENSION_{last_year}",
        "assumptions": "Synthetic engineering demonstration. Future demand grows 5% per year from 2040; critical share stays 250/390; LOW/HIGH are 0.8/1.25. Nominal 2035 prices and capacities persist. F is a hypothetical purchased delivery service without separate CAPEX; no Mars feasibility claim. No probability model. Original CAPEX limits remain; cumulative future cap is explicitly 2800 million 2035 units. No mandatory shocks after 2040.",
        "extra_sources": [{"source_id":"F", "name":"Mars-Cargo (synthetic)", "capacity_t_per_year":60.0, "variable_cost_mln_per_t":10.0, "reservation_rate_mln_per_t_year_capacity":0.2, "take_or_pay_share":0.0, "lead_time_min_value":6.0, "lead_time_max_value":6.0, "lead_time_unit":"month", "available_from_year":2041, "reliability_profile":"scenario only", "notes":"TEAM_ASSUMPTION: purchased annual capacity, no separate investment; hypothetical channel for extensibility only"}],
        "future_demand": [{"year":y,"base_total_t":390 * 1.05**(y-2040),"base_critical_t":250 * 1.05**(y-2040),"low_total_t":312 * 1.05**(y-2040),"high_total_t":487.5 * 1.05**(y-2040)} for y in range(2041,last_year+1)],
        "future_capex_limit_mln":2800.0,
        "future_policy":"retain_service_reserve_storage_emergency_and_prices_no_additional_stress",
    }
    sources, _, years = model_data(result)
    result["yearly_orders"] = {y: {s: float(result["yearly_orders"].get(y, result["yearly_orders"].get(str(y), {})).get(s,0)) for s in sources} for y in years}
    for y in years:
        if y > 2040:
            result["yearly_orders"][y].update(A=190.0,B=70.0,C=100.0,D=120.0,F=10.0)
    result["plan_id"] = f"extension-{last_year}"
    return result
