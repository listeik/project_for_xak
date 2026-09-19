"""Exact daily LP for annual orders with fixed investment decisions.

Each admissible Emergency-year pattern is a separate continuous LP. The union
of maximal patterns covers all permitted plans, so the best solution is globally
optimal within the fixed-investment, uniform-delivery model, to solver tolerance.
"""

from __future__ import annotations

from copy import deepcopy
from itertools import product
from time import perf_counter

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import csr_matrix

from app.core.balance_engine import (
    calculate_plan,
    capex_by_year,
    commissioning_day,
    effective_year_data,
    reserve_requirement,
    source_contract,
    startup_stock,
)
from app.core.constants import (
    CONSTRAINTS,
    DAYS_PER_YEAR,
    DEFAULT_DISCOUNT_RATE,
    EPSILON,
    FIRST_YEAR,
    INVESTMENTS,
    SOURCE_IDS,
    SOURCES,
    YEARS,
)


class OptimizationError(ValueError):
    """No verified optimum can be returned for the supplied fixed decisions."""

    def __init__(self, message: str, details: list[dict] | None = None):
        super().__init__(message)
        self.details = details or []


def _emergency_masks() -> list[tuple[int, ...]]:
    """Enumerate maximal admissible supports; enabled years may still order zero."""
    streak_limit = int(CONSTRAINTS["EMERGENCY_BASE_STREAK"]["value"])
    valid = []
    for mask in product((0, 1), repeat=len(YEARS)):
        if any(
            all(mask[start : start + streak_limit + 1])
            for start in range(len(YEARS) - streak_limit)
        ):
            continue
        valid.append(mask)
    return [
        mask
        for mask in valid
        if not any(
            mask != other and all(left <= right for left, right in zip(mask, other))
            for other in valid
        )
    ]


def _fixed_violations(before: dict, contracts: dict) -> list[dict]:
    """Reject only constraints which changing annual orders cannot repair."""
    fixed_codes = {
        "INVESTMENT_OUTSIDE_HORIZON",
        "ZBO_TOO_EARLY",
        "C_OPTION_REQUIRED",
        "ISRU_FUNDING_TOO_LATE",
        "LOSS_CEILING_EXCEEDED",
        f"INITIAL_STORAGE_OVERFLOW_{FIRST_YEAR}",
        f"RESERVE_VIOLATED_{FIRST_YEAR}",
    }
    errors = [
        item
        for item in before["violation_details"]
        if item["code"] in fixed_codes or item["code"].startswith("CAPEX_LIMIT_EXCEEDED_")
    ]
    for (year, source_id), contract in contracts.items():
        if not contract["reservation_explicit"]:
            continue
        reserved = contract["reserved_capacity_t_per_year"]
        if reserved > SOURCES[source_id]["capacity_t_per_year"] + EPSILON:
            errors.append(
                {
                    "code": "FIXED_RESERVATION_EXCEEDS_CAPACITY",
                    "year": year,
                    "source": source_id,
                    "actual": reserved,
                    "limit": SOURCES[source_id]["capacity_t_per_year"],
                    "message": "Фиксированная бронь превышает мощность; измените контракт перед оптимизацией.",
                }
            )
        if not contract["active_days"] and reserved > EPSILON:
            errors.append(
                {
                    "code": "FIXED_RESERVATION_UNAVAILABLE",
                    "year": year,
                    "source": source_id,
                    "actual": reserved,
                    "limit": 0.0,
                    "message": "Фиксированная бронь относится к периоду до доступности источника.",
                }
            )
    return errors


def optimize_supply_plan(plan: dict) -> dict:
    """Minimize discounted cost and return a plan independently checked by core.

    Inputs are finite, schema-validated plans (the same contract as calculate_plan).
    Orders are replaced; investments, explicit reservations, initial inventory,
    scenario, discount rate and sensitivity/lead-time assumptions stay fixed.
    """
    started = perf_counter()
    before = calculate_plan(plan)
    keys = [(year, source) for year in YEARS for source in SOURCE_IDS]
    contracts = {key: source_contract(plan, key[1], key[0]) for key in keys}
    errors = _fixed_violations(before, contracts)
    if errors:
        raise OptimizationError(
            "Фиксированные решения нарушают ограничения. Изменение закупок не устранит эти нарушения.",
            errors,
        )

    # Only explicit take-or-pay contracts need an auxiliary payable-volume variable.
    payable_keys = [
        key for key in keys
        if contracts[key]["reservation_explicit"] and SOURCES[key[1]]["take_or_pay_share"] > 0
    ]
    payable_indices = {key: len(keys) + index for index, key in enumerate(payable_keys)}
    variable_count = len(keys) + len(payable_keys)
    day_count = len(YEARS) * DAYS_PER_YEAR
    net_daily = np.zeros((day_count, variable_count))
    daily_demand = np.empty(day_count)
    daily_capacity = np.empty(day_count)
    holding_weights = np.empty(day_count)
    objective = np.zeros(variable_count)
    constant_cost = 0.0
    bounds: list[tuple[float, float | None]] = []
    extra_rows, extra_limits = [], []
    discount_rate = float(plan.get("discount_rate", DEFAULT_DISCOUNT_RATE))
    capex = capex_by_year(plan)
    year_data = {year: effective_year_data(plan, year) for year in YEARS}
    initial_inventory = startup_stock(plan)["net_inventory_t"]
    isru_commission = commissioning_day(plan, "D")

    for year_index, year in enumerate(YEARS):
        data = year_data[year]
        start, end = year_index * DAYS_PER_YEAR, (year_index + 1) * DAYS_PER_YEAR
        discount = 1 / (1 + discount_rate) ** (year - FIRST_YEAR)
        daily_demand[start:end] = data["demand_total"] / DAYS_PER_YEAR
        daily_capacity[start:end] = data["storage_capacity"]
        holding_weights[start:end] = data["holding_rate"] / DAYS_PER_YEAR * discount
        fixed_opex = data["storage_fixed_opex"]
        if isru_commission is not None and isru_commission < end:
            fixed_opex += INVESTMENTS["LUNAR_ISRU"]["fixed_opex_mln_per_year"]
        constant_cost += (capex[year] + fixed_opex) * discount

    for index, (year, source_id) in enumerate(keys):
        contract = contracts[year, source_id]
        source = SOURCES[source_id]
        data = year_data[year]
        discount = 1 / (1 + discount_rate) ** (year - FIRST_YEAR)
        startup = contract["startup_ordered_t"]
        upper = contract["available_capacity_t"] - startup
        if contract["reservation_explicit"]:
            upper = min(upper, contract["reserved_period_t"] - startup)
        if upper < 0:
            raise OptimizationError(
                "Фиксированный начальный запас не помещается в мощность или бронь канала A в 2035 году.",
                [{"code": "STARTUP_CONTRACT_INSUFFICIENT", "year": year,
                  "source": source_id, "startup_gross_t": startup,
                  "available_capacity_t": contract["available_capacity_t"],
                  "reserved_period_t": contract["reserved_period_t"]
                  if contract["reservation_explicit"] else None}],
            )
        bounds.append((0.0, upper))
        if contract["active_days"]:
            net_daily[contract["day_start"] : contract["day_end"], index] = (
                contract["delivery_share"] * (1 - data["loss_rate"]) / contract["active_days"]
            )

        if (year, source_id) in payable_indices:
            payable_index = payable_indices[year, source_id]
            objective[payable_index] = contract["price_per_t"] * discount
            row = np.zeros(variable_count)
            row[index], row[payable_index] = 1.0, -1.0
            extra_rows.append(row)
            extra_limits.append(-startup)
            row = np.zeros(variable_count)
            row[payable_index] = -1.0
            extra_rows.append(row)
            extra_limits.append(-source["take_or_pay_share"] * contract["reserved_period_t"])
        else:
            objective[index] += contract["price_per_t"] * discount
            constant_cost += startup * contract["price_per_t"] * discount

        if contract["reservation_explicit"]:
            constant_cost += contract["reservation"] * discount
        else:
            # annual_reserved = (order + startup) / fraction; the fraction cancels.
            reservation_rate = source["reservation_rate_mln_per_t_year_capacity"]
            objective[index] += reservation_rate * discount
            constant_cost += startup * reservation_rate * discount

    bounds.extend((0.0, None) for _ in payable_keys)
    cumulative_net = net_daily.cumsum(axis=0)
    cumulative_demand = daily_demand.cumsum()
    closing_constant = initial_inventory - cumulative_demand
    # At 100% service: pre-service = closing + daily demand; the two share coefficients.
    pre_service_constant = closing_constant + daily_demand
    objective += holding_weights @ cumulative_net
    constant_cost += float(holding_weights @ (closing_constant + daily_demand / 2))

    rows = [-cumulative_net, cumulative_net]
    limits = [closing_constant, daily_capacity - pre_service_constant]
    for year_index, year in enumerate(YEARS[1:], start=1):
        previous_day = year_index * DAYS_PER_YEAR - 1
        rows.append(-cumulative_net[previous_day : previous_day + 1])
        limits.append(
            np.array([closing_constant[previous_day] - reserve_requirement(year_data[year]["demand_total"])])
        )
    if extra_rows:
        rows.append(np.asarray(extra_rows))
        limits.append(np.asarray(extra_limits))
    inequalities = csr_matrix(np.vstack(rows))
    inequality_limits = np.concatenate(limits)

    masks = _emergency_masks()
    candidates, solver_details = [], []
    emergency_indices = [index for index, (_, source) in enumerate(keys) if source == "E"]
    for mask in masks:
        mask_bounds = list(bounds)
        for index, enabled in zip(emergency_indices, mask):
            if not enabled:
                mask_bounds[index] = (0.0, 0.0)
        solution = linprog(
            objective,
            A_ub=inequalities,
            b_ub=inequality_limits,
            bounds=mask_bounds,
            method="highs",
            options={"primal_feasibility_tolerance": 1e-9, "dual_feasibility_tolerance": 1e-9},
        )
        solver_details.append(
            {"emergency_enabled_years": [year for year, enabled in zip(YEARS, mask) if enabled],
             "status": int(solution.status), "message": solution.message}
        )
        if solution.status == 2:  # A proven infeasible support contributes no candidate.
            continue
        if not solution.success:
            raise OptimizationError(
                "Решатель не подтвердил оптимум для всех вариантов Emergency. Проверенный оптимум не получен.",
                solver_details,
            )

        optimized = deepcopy(plan)
        optimized["yearly_orders"] = {year: {} for year in YEARS}
        for index, (year, source) in enumerate(keys):
            # Preserve full solver precision. Do not round/clip a physical plan after solving.
            value = float(solution.x[index])
            if value < 0:
                raise OptimizationError("Решатель вернул отрицательный заказ из-за численной ошибки.", solver_details)
            optimized["yearly_orders"][year][source] = value
        result = calculate_plan(optimized)
        lp_cost = float(solution.fun + constant_cost)
        engine_cost = result["kpi_summary"]["npv"]
        cost_tolerance = max(1e-6, abs(engine_cost) * 1e-9)
        if (
            result["violations"]
            or result["kpi_summary"]["total_shortage"] >= 1e-6
            or abs(lp_cost - engine_cost) > cost_tolerance
        ):
            raise OptimizationError(
                "Найденный план не прошёл независимую проверку ежедневного баланса и стоимости.",
                [{"code": "SOLUTION_REVALIDATION_FAILED", "lp_npv": lp_cost,
                  "engine_npv": engine_cost, "npv_tolerance": cost_tolerance,
                  "total_shortage_t": result["kpi_summary"]["total_shortage"],
                  "violations": result["violation_details"]}],
            )
        candidates.append((engine_cost, optimized, result, lp_cost, mask))

    if not candidates:
        capacities = []
        for year in YEARS:
            maximum_net = sum(
                bounds[index][1] * contracts[year, source]["delivery_share"] * (1 - year_data[year]["loss_rate"])
                for index, (order_year, source) in enumerate(keys) if order_year == year
            )
            capacities.append(
                {"year": year, "demand_t": year_data[year]["demand_total"],
                 "opening_reserve_t": reserve_requirement(year_data[year]["demand_total"]),
                 "maximum_regular_net_inflow_t": maximum_net,
                 "note": "Верхняя оценка учитывает мощности, бронь и сроки ввода; запрет цепочек E может её уменьшить."}
            )
        raise OptimizationError(
            "Нулевой дефицит недостижим при фиксированных инвестициях, запасе и контрактах: "
            "совместно не выполняются доступность поставок, суточная вместимость, резерв или правило Emergency. "
            "Проверьте годы ввода C/D, модернизацию, бронь и спрос.",
            [{"code": "NO_FEASIBLE_ORDER_PLAN", "yearly_capacity_diagnostics": capacities,
              "solver_candidates": solver_details}],
        )

    engine_cost, optimized, result, lp_cost, best_mask = min(candidates, key=lambda item: item[0])
    before_npv = before["kpi_summary"]["npv"]
    return {
        "plan": optimized,
        "result": result,
        "optimization": {
            "solver": "scipy.optimize.linprog(method='highs')",
            "status": "optimal",
            "scope": "annual orders at fixed investments, initial inventory, explicit reservations and uniform daily delivery assumptions",
            "objective": "minimum discounted procurement + reservation + daily holding + fixed OPEX + CAPEX; 100% daily service",
            "objective_value": engine_cost,
            "lp_objective_value": lp_cost,
            "objective_residual": lp_cost - engine_cost,
            "npv_before": before_npv,
            "npv_after": engine_cost,
            "savings": before_npv - engine_cost,
            "baseline_feasible": before["feasible"],
            "baseline_shortage_t": before["kpi_summary"]["total_shortage"],
            "baseline_has_shortage": before["kpi_summary"]["has_shortage"],
            "elapsed_seconds": perf_counter() - started,
            "candidate_count": len(masks),
            "feasible_candidate_count": len(candidates),
            "emergency_enabled_years": [year for year, enabled in zip(YEARS, best_mask) if enabled],
            "order_variable_count": len(keys),
            "payable_variable_count": len(payable_keys),
            "daily_steps": day_count,
            "primal_feasibility_tolerance": 1e-9,
            "investment_search_performed": False,
            "explanation": (
                "Минимум NPV для фиксированных инвестиционных решений и допущения равномерных поставок "
                "найден перебором всех максимальных допустимых наборов лет Emergency и решением LP для каждого. "
                "Годы инвестиций, начальный запас и явная бронь сохранены. Каждый кандидат проверен "
                "суточным расчётным ядром: нарушений нет, дефицит менее 0,000001 т. "
                "Оптимальность по другим инвестициям и произвольным графикам поставок не утверждается. "
                "Экономия является разностью стоимостей; если исходный план имеет дефицит, она не означает "
                "сравнение двух равноценных по обслуживанию стратегий."
            ),
        },
    }
