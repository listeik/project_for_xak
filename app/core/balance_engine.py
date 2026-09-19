"""Daily, deterministic fuel and financial accounting independent of FastAPI.

The annual UI chooses delivery-year contract quantities. Timely rolling orders
produce uniform deliveries during each channel's available part of that year.
See docs/MODEL.md for preparation, startup-stock and partial-year conventions.
"""

from __future__ import annotations

import calendar
import math
from app.core.configuration import model_data, config_version, source_shock
from datetime import date, timedelta

from app.core.constants import (
    CONSTRAINTS,
    DAYS_PER_MONTH,
    DAYS_PER_WEEK,
    DAYS_PER_YEAR,
    DEFAULT_DISCOUNT_RATE,
    DEFAULT_INITIAL_INVENTORY,
    DEMAND,
    EPSILON,
    FIRST_YEAR,
    INPUT_VERSION,
    INVESTMENTS,
    LAST_YEAR,
    MANDATORY_STRESS,
    MODEL_VERSION,
    RESERVE_DAYS,
    SOURCE_IDS,
    SOURCES,
    STORAGE,
    YEARS,
)


def material_balance(opening: float, delivered: float, losses: float, served: float) -> float:
    """The organiser identity; callers must separately enforce physical bounds."""
    return opening + delivered - losses - served


def allocate_demand(available: float, total: float, critical: float) -> dict:
    """Critical demand is nested in total and receives first priority."""
    served_critical = min(max(available, 0.0), critical)
    served_other = min(max(available - served_critical, 0.0), total - critical)
    served = served_critical + served_other
    return {
        "served": served,
        "served_critical": served_critical,
        "shortage": max(0.0, total - served),
        "closing_inventory": max(0.0, available - served),
    }


def throughput_losses(gross_inflow: float, loss_rate: float) -> float:
    return gross_inflow * loss_rate


def reserve_requirement(annual_demand: float, days: float = RESERVE_DAYS) -> float:
    return annual_demand * days / DAYS_PER_YEAR


def take_or_pay(order: float, reserved_period: float, share: float, price: float) -> dict:
    payable = max(order, reserved_period * share)
    return {"payable_volume": payable, "variable_payment": payable * price}


def reservation_payment(annual_capacity: float, rate: float, period_fraction: float) -> float:
    return annual_capacity * rate * period_fraction


def apply_delivery_share(planned: float, actual_share: float) -> float:
    """Reliability metadata is deliberately absent from this calculation."""
    return planned * actual_share


def capacity_check(reserved: float, capacity: float) -> dict:
    excess = max(0.0, reserved - capacity)
    return {"violation": "CAPACITY_EXCEEDED" if excess > EPSILON else None, "excess_t": excess}


def _year_value(mapping: dict, year: int, default=None):
    return mapping.get(year, mapping.get(str(year), default))


def _decision(plan: dict, name: str) -> int | None:
    value = plan.get("investments", {}).get(name)
    return int(value) if value is not None else None


def _year_start(year: int) -> int:
    return (year - FIRST_YEAR) * DAYS_PER_YEAR


def model_date(day_index: int) -> str:
    """Model calendar has 365 days/year; leap days are skipped in date labels."""
    relative_year, ordinal = divmod(day_index, DAYS_PER_YEAR)
    year = FIRST_YEAR + relative_year
    leap_offset = int(calendar.isleap(year) and ordinal >= 59)
    return (date(year, 1, 1) + timedelta(days=ordinal + leap_offset)).isoformat()


def lead_days(plan: dict, source_id: str) -> int:
    SOURCES, DEMAND, YEARS = model_data(plan)
    LAST_YEAR = YEARS[-1]
    source = SOURCES[source_id]
    value = source["lead_time_max_value"]
    if source_id == "C":
        value = plan.get("c_lead_months", value)
    elif source_id == "D":
        value = plan.get("d_lead_months", value)
    conversion = DAYS_PER_WEEK if source["lead_time_unit"] == "week" else DAYS_PER_MONTH
    return math.ceil(float(value) * conversion)


def commissioning_day(plan: dict, source_id: str) -> int | None:
    SOURCES, DEMAND, YEARS = model_data(plan)
    LAST_YEAR = YEARS[-1]
    source = SOURCES[source_id]
    if source_id == "C":
        option = _decision(plan, "option_c_year")
        exercise = _decision(plan, "exercise_c_year")
        if option is None or exercise is None or not FIRST_YEAR <= option <= exercise <= LAST_YEAR:
            return None
        return _year_start(exercise) + lead_days(plan, source_id)
    if source_id == "D":
        funding = _decision(plan, "isru_funding_year")
        earliest = int(source["available_from_year"])
        if funding is None or not FIRST_YEAR <= funding < earliest:
            return None
        return _year_start(earliest)
    return _year_start(int(source["available_from_year"] or FIRST_YEAR))


def source_availability(plan: dict, source_id: str, year: int) -> dict:
    """Reusable affine schedule for simulation and the LP optimizer.

    day_start/day_end are absolute model-day indices, end exclusive. C's
    preparation is its first delivery lead; D has an additional post-commission
    transport lead. A/B/E can be ordered during the preparatory period.
    """
    SOURCES, _, _ = model_data(plan)
    commission = commissioning_day(plan, source_id)
    year_start, year_end = _year_start(year), _year_start(year + 1)
    if commission is None:
        start = year_end
        first_delivery = None
    else:
        first_delivery = commission + (lead_days(plan, source_id) if source_id == "D" else 0)
        start = min(year_end, max(year_start, first_delivery))
    scheduled_days = max(0, year_end - start)
    first_order_day = start - lead_days(plan, source_id)
    effect = source_shock(plan, source_id, year)
    start = min(year_end, start + math.ceil(effect.get("delay_months", 0) * DAYS_PER_MONTH))
    active_days = max(0, year_end - start)
    fraction = scheduled_days / DAYS_PER_YEAR
    return {
        "source_id": source_id,
        "year": year,
        "commission_day": commission,
        "first_possible_delivery_day": first_delivery,
        "day_start": start,
        "day_end": year_end,
        "active_days": active_days,
        "scheduled_days": scheduled_days,
        "first_order_day": first_order_day,
        "timely_share": active_days / scheduled_days if scheduled_days else 0.0,
        "period_fraction": fraction,
        "available_capacity_t": SOURCES[source_id]["capacity_t_per_year"] * fraction * effect.get("capacity_factor", 1.0),
        "lead_days": lead_days(plan, source_id),
    }


def effective_year_data(plan: dict, year: int) -> dict:
    SOURCES, DEMAND, YEARS = model_data(plan)
    LAST_YEAR = YEARS[-1]
    scenario = plan.get("scenario", "BASE")
    is_stress = scenario == "MANDATORY_STRESS"
    demand_profile = plan.get("demand_profile", "BASE")
    if is_stress and demand_profile != "BASE":
        raise ValueError("LOW/HIGH demand research cannot be combined with MANDATORY_STRESS.")
    demand_row = DEMAND[year]
    profile_total = demand_row[f"{demand_profile.lower()}_total_t"]
    # LOW/HIGH preserve the critical share of the corresponding BASE year.
    profile_critical = demand_row["base_critical_t"] * profile_total / demand_row["base_total_t"] if demand_row["base_total_t"] else 0.0
    demand_multiplier = (
        _year_value(MANDATORY_STRESS["demand_multiplier"], year, 1.0) if is_stress else 1.0
    )
    critical_multiplier = (
        _year_value(MANDATORY_STRESS["critical_demand_multiplier"], year, 1.0)
        if is_stress
        else 1.0
    )
    research_demand = float(plan.get("demand_factor", 1.0))
    research_price = float(plan.get("price_factor", 1.0))
    shock = plan.get("research_shock")
    if shock and shock["start_year"] <= year <= shock["end_year"]:
        research_demand *= shock.get("demand_factor", 1.0)
    zbo_year = _decision(plan, "zbo_year")
    zbo_valid = zbo_year is not None and STORAGE["ZBO"]["available_from_year"] <= zbo_year <= year
    storage = STORAGE["ZBO" if zbo_valid else "BASE"]
    prices, delivery_shares = {}, {}
    for source_id, source in SOURCES.items():
        price_multiplier = (
            _year_value(
                MANDATORY_STRESS["variable_price_multiplier"].get(source["name"], {}), year, 1.0
            )
            if is_stress
            else 1.0
        )
        prices[source_id] = source["variable_cost_mln_per_t"] * price_multiplier * research_price * source_shock(plan, source_id, year).get("price_factor", 1.0)
        delivery_shares[source_id] = (
            _year_value(
                MANDATORY_STRESS["actual_delivery_share"].get(source["name"], {}), year, 1.0
            )
            if is_stress
            else 1.0
        )
        delivery_shares[source_id] *= source_shock(plan, source_id, year).get("delivery_factor", 1.0)
    return {
        "year": year,
        "demand_total": profile_total * demand_multiplier * research_demand,
        "demand_critical": profile_critical * critical_multiplier * research_demand,
        "storage_capacity": storage["capacity_t"],
        "loss_rate": storage["loss_rate_on_throughput"],
        "holding_rate": storage["holding_cost_mln_per_t_year"],
        "storage_fixed_opex": storage["fixed_opex_mln_per_year"],
        "zbo_active": bool(zbo_valid),
        "prices": prices,
        "delivery_shares": delivery_shares,
    }


def startup_stock(plan: dict) -> dict:
    """Explicit acquisition ledger: prepare net opening inventory using source A."""
    net = float(plan.get("initial_inventory_t", DEFAULT_INITIAL_INVENTORY))
    year_data = effective_year_data(plan, FIRST_YEAR)
    gross = net / (1 - year_data["loss_rate"])
    return {
        "source_id": "A",
        "accounting_year": FIRST_YEAR,
        "net_inventory_t": net,
        "gross_delivery_t": gross,
        "losses_t": gross - net,
        "variable_cost": gross * year_data["prices"]["A"],
        "order_date": model_date(-lead_days(plan, "A")),
        "arrival_date": model_date(0),
        "lead_days": lead_days(plan, "A"),
        "balance_treatment": "arrival immediately before horizon opening balance; counted once",
    }


def source_contract(plan: dict, source_id: str, year: int) -> dict:
    SOURCES, DEMAND, YEARS = model_data(plan)
    LAST_YEAR = YEARS[-1]
    availability = source_availability(plan, source_id, year)
    fraction = availability["period_fraction"]
    order = float(_year_value(plan.get("yearly_orders", {}), year, {}).get(source_id, 0.0))
    startup = startup_stock(plan)["gross_delivery_t"] if year == FIRST_YEAR and source_id == "A" else 0.0
    total_order = order + startup
    reservations = _year_value(plan.get("yearly_reservations") or {}, year, {})
    explicit_reservation = source_id in reservations
    reserved_rate = (
        float(reservations[source_id])
        if explicit_reservation
        else total_order / fraction if fraction > 0 else 0.0
    )
    reserved_period = reserved_rate * fraction
    source = SOURCES[source_id]
    year_data = effective_year_data(plan, year)
    payment = take_or_pay(
        total_order, reserved_period, source["take_or_pay_share"], year_data["prices"][source_id]
    )
    delivered = apply_delivery_share(order, year_data["delivery_shares"][source_id] * availability["timely_share"]) if fraction else 0.0
    return {
        **availability,
        "ordered_t": order,
        "startup_ordered_t": startup,
        "total_ordered_t": total_order,
        "reserved_capacity_t_per_year": reserved_rate,
        "reserved_period_t": reserved_period,
        "reservation_explicit": explicit_reservation,
        "delivered_t": delivered,
        "delivery_share": year_data["delivery_shares"][source_id] * availability["timely_share"],
        "price_per_t": year_data["prices"][source_id],
        "payable_volume_t": payment["payable_volume"],
        "procurement": payment["variable_payment"],
        "reservation": reservation_payment(
            reserved_rate, source["reservation_rate_mln_per_t_year_capacity"], fraction
        ),
    }


def capex_by_year(plan: dict) -> dict[int, float]:
    _, _, YEARS = model_data(plan)
    cash = dict.fromkeys(YEARS, 0.0)
    decisions = (
        ("zbo_year", INVESTMENTS["ZBO"]["exercise_cost_mln"]),
        ("option_c_year", INVESTMENTS["EARTH_NEW"]["option_fee_mln"]),
        ("exercise_c_year", INVESTMENTS["EARTH_NEW"]["exercise_cost_mln"]),
        ("isru_funding_year", INVESTMENTS["LUNAR_ISRU"]["exercise_cost_mln"]),
    )
    for name, amount in decisions:
        year = _decision(plan, name)
        if year in cash:
            cash[year] += amount
    return cash


def check_capex_limits(cash_by_year: dict) -> list[dict]:
    """Also accepts synthetic CAPEX cash flows for independent boundary testing."""
    details = []
    for constraint_id in ("CAPEX_2037", "CAPEX_2040"):
        year = int(constraint_id.rsplit("_", 1)[1])
        actual = sum(float(value) for key, value in cash_by_year.items() if int(key) <= year)
        limit = CONSTRAINTS[constraint_id]["value"]
        if actual > limit + EPSILON:
            details.append(
                {
                    "code": f"CAPEX_LIMIT_EXCEEDED_{year}",
                    "year": year,
                    "source": None,
                    "actual": actual,
                    "limit": limit,
                    "excess": actual - limit,
                    "unit": "million 2035 units",
                    "message": f"Накопленный CAPEX до {year}: {actual:.3f} > {limit:.3f} млн.",
                }
            )
    return details


def _investment_violations(plan: dict) -> list[dict]:
    SOURCES, _, YEARS = model_data(plan)
    LAST_YEAR = YEARS[-1]
    errors = []

    def issue(code: str, year: int | None, message: str, limit=None):
        errors.append(
            {"code": code, "year": year, "source": None, "actual": year, "limit": limit, "message": message}
        )

    for key in ("zbo_year", "option_c_year", "exercise_c_year", "isru_funding_year"):
        value = _decision(plan, key)
        if value is not None and not FIRST_YEAR <= value <= LAST_YEAR:
            issue("INVESTMENT_OUTSIDE_HORIZON", value, f"{key}: инвестиция за пределами горизонта.")
    zbo = _decision(plan, "zbo_year")
    if zbo is not None and zbo < STORAGE["ZBO"]["available_from_year"]:
        issue("ZBO_TOO_EARLY", zbo, "ZBO доступна только с 2036 года.", 2036)
    option, exercise = _decision(plan, "option_c_year"), _decision(plan, "exercise_c_year")
    if exercise is not None and (option is None or option > exercise):
        issue("C_OPTION_REQUIRED", exercise, "Реализация C требует покупки опциона до или в год реализации.", option)
    funding = _decision(plan, "isru_funding_year")
    if funding is not None and funding >= SOURCES["D"]["available_from_year"]:
        issue("ISRU_FUNDING_TOO_LATE", funding, "ISRU должна быть профинансирована до начала 2038 года.", 2037)
    return errors


def locked_contracts(plan: dict) -> dict[tuple[int, str], float]:
    """Conservative annual commitments: freeze a contract once its first order was placed."""
    lock = plan.get("contract_lock")
    if not lock:
        return {}
    sources, _, years = model_data(plan)
    baseline = {**plan, "research_shock": None, "contract_lock": None}
    result = {}
    for year in years:
        for source in sources:
            availability = source_availability(baseline, source, year)
            if year < lock["shock_year"] or (availability["active_days"] and availability["day_start"] - availability["lead_days"] < _year_start(lock["shock_year"])):
                result[year, source] = float(_year_value(lock["baseline_orders"], year, {}).get(source, 0))
    return result


def contract_lock_violations(plan: dict) -> list[dict]:
    errors = []
    lock = plan.get("contract_lock")
    if not lock:
        return errors
    for (year, source), expected in locked_contracts(plan).items():
        actual = float(_year_value(plan["yearly_orders"], year, {}).get(source, 0))
        if abs(actual - expected) > EPSILON:
            errors.append({"code":f"SUNK_CONTRACT_CHANGED_{source}_{year}","year":year,"source":source,"actual":actual,"limit":expected,"unit":"t","message":"Заказ размещён до шока: годовой контракт нельзя отменить или заменить задним числом."})
    if (plan.get("yearly_reservations") or {}) != (lock.get("baseline_reservations") or {}):
        errors.append({"code":"SUNK_RESERVATION_CHANGED","year":lock["shock_year"],"source":None,"actual":None,"limit":None,"message":"В режиме реакции явная бронь сохраняется."})
    return errors


def calculate_plan(plan: dict) -> dict:
    """Calculate one validated finite plan. Business failures remain inspectable.

    Insufficient supply never makes physical stock negative. Over-capacity
    orders are NOT silently reduced: the provisional path is calculated and
    marked infeasible. Uncommissioned sources deliver nothing, with violations.
    """
    SOURCES, _, YEARS = model_data(plan)
    SOURCE_IDS = tuple(SOURCES)
    annual, trace, schedules, warnings = [], [], [], []
    details = _investment_violations(plan)
    capex = capex_by_year(plan)
    details.extend(check_capex_limits(capex))
    details.extend(contract_lock_violations(plan))
    config = plan.get("research_config")
    if config and YEARS[-1] > 2040 and sum(capex.values()) > config["future_capex_limit_mln"] + EPSILON:
        details.append({"code":"FUTURE_CAPEX_LIMIT", "year":YEARS[-1],"source":None,"actual":sum(capex.values()),"limit":config["future_capex_limit_mln"],"unit":"million 2035 units","message":"Превышен явно заданный CAPEX исследовательского горизонта."})
    startup = startup_stock(plan)
    schedules.append(
        {
            "kind": "startup",
            "source_id": "A",
            "source_name": SOURCES["A"]["name"],
            "year": FIRST_YEAR,
            "ordered_t": startup["gross_delivery_t"],
            "delivered_t": startup["gross_delivery_t"],
            "net_inventory_t": startup["net_inventory_t"],
            "losses_t": startup["losses_t"],
            "first_order_date": startup["order_date"],
            "last_order_date": startup["order_date"],
            "first_arrival_date": startup["arrival_date"],
            "last_arrival_date": startup["arrival_date"],
            "commission_date": model_date(0),
            "lead_days": startup["lead_days"],
            "cost_included_in": "2035 A procurement; not an additional payment",
        }
    )
    inventory = startup["net_inventory_t"]
    discount_rate = float(plan.get("discount_rate", DEFAULT_DISCOUNT_RATE))
    emergency_streak = 0
    source_totals = {
        source: {"ordered_t": 0.0, "delivered_t": 0.0, "procurement": 0.0, "reservation": 0.0}
        for source in SOURCE_IDS
    }

    def violation(code, year, message, actual=None, limit=None, source=None, unit=None, **extra):
        item = {
            "code": code,
            "year": year,
            "source": source,
            "actual": actual,
            "limit": limit,
            "message": message,
            **extra,
        }
        if actual is not None and limit is not None and isinstance(actual, (int, float)):
            item["excess"] = abs(actual - limit)
        if unit:
            item["unit"] = unit
        details.append(item)

    if inventory > STORAGE["BASE"]["capacity_t"] + EPSILON:
        violation(
            f"INITIAL_STORAGE_OVERFLOW_{FIRST_YEAR}", FIRST_YEAR,
            "Начальный запас превышает объём базового склада.", inventory, STORAGE["BASE"]["capacity_t"], unit="t",
        )

    for year in YEARS:
        data = effective_year_data(plan, year)
        contracts = {source: source_contract(plan, source, year) for source in SOURCE_IDS}
        reserve = reserve_requirement(data["demand_total"], plan.get("reserve_target_days", RESERVE_DAYS))
        start_inventory = inventory
        if start_inventory + EPSILON < reserve:
            violation(
                f"RESERVE_VIOLATED_{year}", year,
                f"Резерв на начало {year}: {start_inventory:.3f} т при требовании {reserve:.3f} т.",
                start_inventory, reserve, unit="t",
            )
        if (
            plan.get("scenario", "BASE") == "MANDATORY_STRESS"
            and MANDATORY_STRESS["loss_ceiling"]["from_year"] <= year <= 2040
            and data["loss_rate"] > MANDATORY_STRESS["loss_ceiling"]["max_losses_divided_by_throughput"] + EPSILON
        ):
            violation(
                "LOSS_CEILING_EXCEEDED", year,
                f"В {year} коэффициент потерь {data['loss_rate']:.1%} превышает стресс-лимит 2%.",
                data["loss_rate"], MANDATORY_STRESS["loss_ceiling"]["max_losses_divided_by_throughput"], unit="share",
            )
        for source_id, contract in contracts.items():
            source = SOURCES[source_id]
            capacity = source["capacity_t_per_year"]
            if contract["reserved_capacity_t_per_year"] > capacity + EPSILON:
                violation(
                    f"RESERVATION_CAPACITY_EXCEEDED_{source_id}_{year}", year,
                    f"{source_id}: бронь превышает годовую мощность канала.",
                    contract["reserved_capacity_t_per_year"], capacity, source_id, "t/year",
                )
            if contract["total_ordered_t"] > contract["available_capacity_t"] + EPSILON:
                violation(
                    f"CAPACITY_EXCEEDED_{source_id}_{year}", year,
                    f"{source_id}: заказ с начальным запасом превышает доступную мощность за период.",
                    contract["total_ordered_t"], contract["available_capacity_t"], source_id, "t",
                )
            if contract["total_ordered_t"] > contract["reserved_period_t"] + EPSILON:
                violation(
                    f"ORDER_EXCEEDS_RESERVATION_{source_id}_{year}", year,
                    f"{source_id}: заказ превышает объём, обеспеченный резервированием мощности.",
                    contract["total_ordered_t"], contract["reserved_period_t"], source_id, "t",
                )
            if not contract["active_days"] and contract["ordered_t"] > EPSILON:
                violation(
                    f"SOURCE_UNAVAILABLE_{source_id}_{year}", year,
                    f"{source_id}: источник не может доставить заказ в этом году с учётом ввода и lead time.",
                    contract["ordered_t"], 0.0, source_id, "t",
                )
            if not contract["active_days"] and contract["reserved_capacity_t_per_year"] > EPSILON:
                violation(
                    f"RESERVATION_UNAVAILABLE_{source_id}_{year}", year,
                    f"{source_id}: мощность зарезервирована до появления доступного периода поставки.",
                    contract["reserved_capacity_t_per_year"], 0.0, source_id, "t/year",
                )
            source_totals[source_id]["ordered_t"] += contract["total_ordered_t"]
            source_totals[source_id]["delivered_t"] += contract["delivered_t"] + contract["startup_ordered_t"]
            source_totals[source_id]["procurement"] += contract["procurement"]
            source_totals[source_id]["reservation"] += contract["reservation"]
            active = bool(contract["active_days"])
            schedules.append(
                {
                    **contract,
                    "kind": "regular",
                    "source_name": source["name"],
                    "commission_date": model_date(contract["commission_day"]) if contract["commission_day"] is not None else None,
                    "first_order_date": model_date(contract["first_order_day"]) if contract["scheduled_days"] else None,
                    "last_order_date": model_date(contract["day_end"] - 1 - contract["lead_days"]) if active else None,
                    "first_arrival_date": model_date(contract["day_start"]) if active else None,
                    "last_arrival_date": model_date(contract["day_end"] - 1) if active else None,
                    "gross_daily_delivery_t": contract["delivered_t"] / contract["active_days"] if active else 0.0,
                }
            )

        emergency_streak = emergency_streak + 1 if contracts["E"]["ordered_t"] > EPSILON else 0
        streak_limit = CONSTRAINTS["EMERGENCY_BASE_STREAK"]["value"]
        if emergency_streak > streak_limit:
            violation(
                f"EMERGENCY_STREAK_EXCEEDED_{year}", year,
                "Плановая закупка Emergency используется более двух последовательных лет.",
                emergency_streak, streak_limit, "E", "years",
            )

        delivered = losses = served = served_critical = holding = 0.0
        min_inventory = inventory
        max_pre_service = inventory
        overflow_days = shortage_days = 0
        first_overflow = first_shortage = None
        first_day = _year_start(year)
        trace.append(
            {"year": year, "day": 0, "date": model_date(first_day), "inventory": inventory,
             "reserve": reserve, "capacity": data["storage_capacity"], "inflow": 0.0, "shortage": 0.0}
        )
        for day in range(DAYS_PER_YEAR):
            absolute_day = first_day + day
            gross = sum(
                contract["delivered_t"] / contract["active_days"]
                for contract in contracts.values()
                if contract["active_days"] and absolute_day >= contract["day_start"]
            )
            daily_losses = throughput_losses(gross, data["loss_rate"])
            pre_service = inventory + gross - daily_losses
            max_pre_service = max(max_pre_service, pre_service)
            if pre_service > data["storage_capacity"] + EPSILON:
                overflow_days += 1
                if first_overflow is None:
                    first_overflow = model_date(absolute_day)
            allocation = allocate_demand(
                pre_service, data["demand_total"] / DAYS_PER_YEAR, data["demand_critical"] / DAYS_PER_YEAR
            )
            inventory = allocation["closing_inventory"]
            if allocation["shortage"] > EPSILON:
                shortage_days += 1
                if first_shortage is None:
                    first_shortage = model_date(absolute_day)
            min_inventory = min(min_inventory, inventory)
            holding += (pre_service + inventory) / 2 * data["holding_rate"] / DAYS_PER_YEAR
            delivered += gross
            losses += daily_losses
            served += allocation["served"]
            served_critical += allocation["served_critical"]
            trace.append(
                {"year": year, "day": day + 1, "date": model_date(absolute_day),
                 "inventory": inventory, "reserve": reserve, "capacity": data["storage_capacity"],
                 "inflow": gross, "shortage": allocation["shortage"], "pre_service_inventory": pre_service}
            )
        if overflow_days:
            violation(
                f"STORAGE_OVERFLOW_{year}", year,
                f"Переполнение склада перед выдачей: максимум {max_pre_service:.3f} т; {overflow_days} дней.",
                max_pre_service, data["storage_capacity"], unit="t", first_date=first_overflow, days=overflow_days,
            )
        service = min(1.0, served / data["demand_total"]) if data["demand_total"] > 0 else 1.0
        critical_service = min(1.0, served_critical / data["demand_critical"]) if data["demand_critical"] > 0 else 1.0
        shortage = max(0.0, data["demand_total"] - served)
        service_below_target = service + EPSILON < CONSTRAINTS["BASE_TOTAL_SERVICE"]["value"]
        critical_service_below_target = critical_service + EPSILON < CONSTRAINTS["BASE_CRITICAL_SERVICE"]["value"]
        if plan.get("scenario", "BASE") == "BASE":
            if service_below_target:
                violation(
                    f"SERVICE_LEVEL_VIOLATED_{year}", year, "Общий уровень обслуживания ниже минимума BASE.",
                    service, CONSTRAINTS["BASE_TOTAL_SERVICE"]["value"], unit="share",
                )
            if critical_service_below_target:
                violation(
                    f"CRITICAL_SERVICE_LEVEL_VIOLATED_{year}", year, "Критический уровень обслуживания ниже минимума BASE.",
                    critical_service, CONSTRAINTS["BASE_CRITICAL_SERVICE"]["value"], unit="share",
                )
        else:
            if shortage > EPSILON:
                warnings.append({
                    "code": f"STRESS_SHORTAGE_{year}", "year": year, "source": None,
                    "actual": shortage, "limit": 0.0, "unit": "t",
                    "message": f"В {year} дефицит {shortage:.3f} т; дней с дефицитом: {shortage_days}. "
                    "Запаса и поставок недостаточно для полного обслуживания. "
                    "Пересмотрите будущие заказы и резерв с учётом сроков доставки.",
                    "first_date": first_shortage, "days": shortage_days,
                })
            for below, code, title, actual, target in (
                (service_below_target, "SERVICE", "Общий сервис", service, CONSTRAINTS["BASE_TOTAL_SERVICE"]["value"]),
                (critical_service_below_target, "CRITICAL_SERVICE", "Критический сервис", critical_service, CONSTRAINTS["BASE_CRITICAL_SERVICE"]["value"]),
            ):
                if below:
                    warnings.append({
                        "code": f"STRESS_{code}_BELOW_TARGET_{year}", "year": year, "source": None,
                        "actual": actual, "limit": target, "unit": "share",
                        "message": f"{title} {actual:.2%} ниже ориентира устойчивости {target:.0%}. "
                        "В STRESS это предупреждение, а не жёсткое ограничение.",
                    })
        procurement = sum(contract["procurement"] for contract in contracts.values())
        reservation = sum(contract["reservation"] for contract in contracts.values())
        isru_commission = commissioning_day(plan, "D")
        isru_active = isru_commission is not None and isru_commission < _year_start(year + 1)
        fixed_opex = data["storage_fixed_opex"] + (
            INVESTMENTS["LUNAR_ISRU"]["fixed_opex_mln_per_year"] if isru_active else 0.0
        )
        total_opex = procurement + reservation + holding + fixed_opex
        total_cost = total_opex + capex[year]
        discount_factor = 1 / (1 + discount_rate) ** (year - FIRST_YEAR)
        annual.append(
            {
                "year": year,
                "start_inventory": start_inventory,
                "inflow": delivered,
                "losses": losses,
                "served_total": served,
                "served_critical": served_critical,
                "end_inventory": inventory,
                "shortage": shortage,
                "has_shortage": shortage > EPSILON,
                "critical_shortage": max(0.0, data["demand_critical"] - served_critical),
                "demand_total": data["demand_total"],
                "demand_critical": data["demand_critical"],
                "reserve_required": reserve,
                "service_level": service,
                "critical_service_level": critical_service,
                "service_below_target": service_below_target,
                "critical_service_below_target": critical_service_below_target,
                "storage_capacity": data["storage_capacity"],
                "loss_rate": data["loss_rate"],
                "zbo_active": data["zbo_active"],
                "min_inventory": min_inventory,
                "max_pre_service_inventory": max_pre_service,
                "shortage_days": shortage_days,
                "first_shortage_date": first_shortage,
                "startup_inflow": startup["gross_delivery_t"] if year == FIRST_YEAR else 0.0,
                "startup_losses": startup["losses_t"] if year == FIRST_YEAR else 0.0,
                "procurement": procurement,
                "reservation": reservation,
                "holding": holding,
                "fixed_opex": fixed_opex,
                "capex": capex[year],
                "opex": total_opex,
                "total_cost": total_cost,
                "discount_factor": discount_factor,
                "npv": total_cost * discount_factor,
                "source_breakdown": contracts,
                "balance_residual": material_balance(start_inventory, delivered, losses, served) - inventory,
            }
        )

    cost_fields = ("procurement", "reservation", "holding", "fixed_opex", "capex", "opex", "total_cost", "npv")
    totals = {key: sum(row[key] for row in annual) for key in cost_fields}
    discounted_totals = {
        key: sum(row[key] * row["discount_factor"] for row in annual)
        for key in cost_fields if key != "npv"
    }
    nodes = [
        {"id": source, "name": SOURCES[source]["name"], "category": "source", **source_totals[source]}
        for source in SOURCE_IDS
    ] + [
        {"id": "HUB", "name": "Орбитальный топливный узел", "category": "hub", "inventory": inventory,
         "capacity": annual[-1]["storage_capacity"]},
        {"id": "DEMAND", "name": "Цислунарные миссии", "category": "demand", "served_t": sum(row["served_total"] for row in annual)},
    ]
    links = [
        {"source": source, "target": "HUB", "value": source_totals[source]["delivered_t"]}
        for source in SOURCE_IDS
    ] + [{"source": "HUB", "target": "DEMAND", "value": sum(row["served_total"] for row in annual)}]
    unique_codes = list(dict.fromkeys(item["code"] for item in details))
    scenario = plan.get("scenario", "BASE")
    demand_profile = plan.get("demand_profile", "BASE")
    research_active = bool(plan.get("research_config") or plan.get("research_shock")) or demand_profile != "BASE" or plan.get("demand_factor", 1.0) != 1.0 or plan.get("price_factor", 1.0) != 1.0
    scenario_id = f"TEAM_{scenario}_{demand_profile}_SENSITIVITY" if research_active else scenario
    if plan.get("research_shock"):
        scenario_id = plan["research_shock"]["scenario_id"]
    elif config:
        scenario_id = config["config_id"] + "_" + scenario_id
    total_served = sum(row["served_total"] for row in annual)
    return {
        "plan_id": plan.get("plan_id", "untitled-plan"),
        "scenario": scenario,
        "scenario_id": scenario_id,
        "demand_profile": demand_profile,
        "input_version": config_version(plan),
        "case_input_version": INPUT_VERSION,
        "model_version": MODEL_VERSION,
        "feasible": not unique_codes,
        "annual_balances": annual,
        "kpi_summary": {
            "total_cost": totals["total_cost"],
            "total_served_t": total_served,
            "cost_per_served_ton": totals["total_cost"] / total_served if total_served > EPSILON else None,
            "discounted_cost_per_served_ton": totals["npv"] / total_served if total_served > EPSILON else None,
            "max_annual_shortage": max(row["shortage"] for row in annual),
            "npv": totals["npv"],
            "min_service_level": min(row["service_level"] for row in annual),
            "min_critical_service_level": min(row["critical_service_level"] for row in annual),
            "total_capex": totals["capex"],
            "total_opex": totals["opex"],
            "capex_through_2037": sum(value for year, value in capex.items() if year <= 2037),
            "capex_limit_2037": CONSTRAINTS["CAPEX_2037"]["value"],
            "capex_limit_2040": CONSTRAINTS["CAPEX_2040"]["value"],
            "horizon_capex_limit": config["future_capex_limit_mln"] if config and YEARS[-1] > 2040 else CONSTRAINTS["CAPEX_2040"]["value"],
            "total_shortage": sum(row["shortage"] for row in annual),
            "end_inventory": inventory,
            "violation_count": len(details),
            "warning_count": len(warnings),
            "has_shortage": any(row["has_shortage"] for row in annual),
        },
        "service_targets": {
            "total": CONSTRAINTS["BASE_TOTAL_SERVICE"]["value"],
            "critical": CONSTRAINTS["BASE_CRITICAL_SERVICE"]["value"],
        },
        "graph_data": {"nodes": nodes, "links": links},
        "violations": unique_codes,
        "violation_details": details,
        "warning_details": warnings,
        "inventory_trace": trace,
        "source_schedule": schedules,
        "startup_stock": startup,
        "financial_breakdown": {
            "annual": [{"year": row["year"], **{key: row[key] for key in cost_fields}} for row in annual],
            "totals": totals,
            "discounted_totals": discounted_totals,
            "by_source": source_totals,
            "startup_stock": startup,
        },
        "assumptions": {
            "classification": "TEAM_ASSUMPTION",
            "days_per_year": DAYS_PER_YEAR,
            "days_per_month": DAYS_PER_MONTH,
            "days_per_week": DAYS_PER_WEEK,
            "lead_rounding": "ceil to whole model day; date labels skip leap days",
            "discount_rate": discount_rate,
            "discount_base_year": FIRST_YEAR,
            "discount_timing": "annual costs placed at year opening; preparatory stock attributed to 2035",
            "demand_profile": "uniform daily; critical demand served first",
            "delivery_profile": "uniform daily over the available part of the delivery year",
            "loss_timing": "once on gross arrivals at inlet, before stock capacity check and demand issue",
            "holding_basis": "daily average of post-arrival/pre-issue and closing physical inventory",
            "reserve_policy": "physical opening-year stock only; unused emergency capacity gives no reserve credit",
            "emergency_base_definition": "any strictly positive annual E order; at most two consecutive years",
            "preparation": "rolling timely A/B/E orders may precede 2035; startup A stock is prepaid and charged in 2035",
            "startup_stock": "net opening stock has a separate gross/loss ledger; regular annual inflow excludes it",
            "partial_year_reservations": "annual reserved rate × available delivery days / 365; implicit rate=order/fraction",
            "invalid_capacity_policy": "no silent order clipping; projected path is infeasible when a capacity rule fails",
            "c_lead_months": plan.get("c_lead_months", SOURCES["C"]["lead_time_max_value"]),
            "d_lead_months": plan.get("d_lead_months", SOURCES["D"]["lead_time_max_value"]),
            "research_config": config,
            "research_shock": plan.get("research_shock"),
            "contract_lock_policy": (plan.get("contract_lock") or {}).get("policy"),
            "reserve_target_days": plan.get("reserve_target_days", RESERVE_DAYS),
            "cost_per_served_ton_formula": "(procurement + reservation + holding + fixed_opex + capex) / actual_served_t; no double counting; all undiscounted",
            "discounted_cost_per_served_ton_formula": "NPV(all_costs) / actual_served_t; discounted cost per physical ton, not LCOF",
            "delay_policy": "research delay closes the arrival window; missed deliveries are not caught up in this horizon; contracted amount remains payable",
            "demand_factor": plan.get("demand_factor", 1.0),
            "demand_input_profile": demand_profile,
            "critical_demand_profile": "LOW/HIGH preserve the critical share of each BASE year",
            "price_factor": plan.get("price_factor", 1.0),
            "research_factors_active": research_active,
            "stress_service": "BASE service targets are resilience benchmarks; stress shortages and missed targets generate warnings, not hard violations",
        },
        "units": {"fuel": "t", "money": "million constant-price 2035 monetary units", "service": "share 0..1", "time_step": "model day"},
    }


calculate_balance = calculate_plan


def default_plan() -> dict:
    """A transparent hybrid proposal, not a claim of economic optimality."""
    orders = {
        2035: {"A": 110, "B": 0, "C": 0, "D": 0, "E": 0},
        2036: {"A": 150, "B": 0, "C": 0, "D": 0, "E": 0},
        2037: {"A": 190, "B": 0, "C": 10, "D": 0, "E": 0},
        2038: {"A": 190, "B": 0, "C": 0, "D": 80, "E": 0},
        2039: {"A": 190, "B": 0, "C": 30, "D": 110, "E": 0},
        2040: {"A": 190, "B": 0, "C": 90, "D": 115, "E": 0},
    }
    return {
        "plan_id": "hybrid-starting-proposal",
        "yearly_orders": orders,
        "yearly_reservations": None,
        "investments": {"zbo_year": 2036, "option_c_year": 2035, "exercise_c_year": 2035, "isru_funding_year": 2037},
        "scenario": "BASE",
        "demand_profile": "BASE",
        "initial_inventory_t": DEFAULT_INITIAL_INVENTORY,
        "discount_rate": DEFAULT_DISCOUNT_RATE,
        "c_lead_months": SOURCES["C"]["lead_time_max_value"],
        "d_lead_months": SOURCES["D"]["lead_time_max_value"],
        "demand_factor": 1.0,
        "price_factor": 1.0,
    }
