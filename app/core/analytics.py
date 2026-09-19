"""Deterministic strategy, stress and risk experiments on the shared daily model."""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import hashlib
import json

from app.core.balance_engine import calculate_plan, locked_contracts
from app.core.configuration import model_data, config_version
from app.core.constants import MODEL_VERSION
from app.core.optimizer import optimize_supply_plan, OptimizationError
from app.schemas.plan import PlanRequest


def validated(plan: dict) -> dict:
    return PlanRequest.model_validate(plan).model_dump()


def summary(result: dict) -> dict:
    return {**result["kpi_summary"], "feasible":result["feasible"], "scenario_id":result["scenario_id"],
            "warning_count":len(result["warning_details"]), "violations":result["violation_details"]}


def compact(result: dict) -> dict:
    """Full annual/financial ledgers; daily trace supplied separately for the chosen plan."""
    return {key:value for key,value in result.items() if key not in {"inventory_trace","graph_data"}}


def standard_environment(plan: dict) -> dict:
    result = deepcopy(plan)
    result.update(scenario="BASE", demand_profile="BASE", demand_factor=1.0, price_factor=1.0,
                  research_shock=None, contract_lock=None)
    return result


def strategy_templates(plan: dict) -> list[dict]:
    templates = []
    base = standard_environment(plan)
    for strategy_id, name, description in (
        ("earth", "Земная", "A/B/C, ZBO; без пилота ISRU и его CAPEX/OPEX"),
        ("hybrid", "Гибридная", "C + ZBO + ISRU, нормативный физический резерв 45 дней"),
        ("reserve", "Усиленный резерв", "C + ISRU + ZBO с 2036; целевой физический резерв 60 дней"),
    ):
        candidate = deepcopy(base)
        candidate["plan_id"] = f"TEAM_{strategy_id.upper()}"
        candidate["investments"] = {"zbo_year":2036,"option_c_year":2035,"exercise_c_year":2035,"isru_funding_year":None if strategy_id=="earth" else 2037}
        candidate["reserve_target_days"] = 60.0 if strategy_id=="reserve" else 45.0
        candidate["initial_inventory_t"] = max(base["initial_inventory_t"], 100*candidate["reserve_target_days"]/365)
        # Explicit reservations remain a user constraint common to all alternatives.
        templates.append({"strategy_id":strategy_id,"name":name,"description":description,"plan":candidate})
    return templates


def compare_strategies(strategies_list: list[dict], scenario: str = "BASE") -> dict:
    rows = []
    reference = None
    for item in strategies_list:
        plan = validated({**item["plan"], "scenario":scenario})
        comparable = (config_version(plan), plan["demand_profile"], plan["demand_factor"],plan["price_factor"],plan["discount_rate"],json.dumps(plan.get("research_shock"),sort_keys=True))
        if reference is not None and comparable != reference:
            raise ValueError("Сравнение требует одинаковых данных, спроса, цен, шоков и ставки дисконта.")
        reference = comparable
        error = None
        try:
            optimized = optimize_supply_plan(plan)
            plan, result = optimized["plan"], optimized["result"]
        except OptimizationError as exc:
            result, error = calculate_plan(plan), {"message":str(exc),"details":exc.details}
        rows.append({**{k:v for k,v in item.items() if k != "plan"}, "plan":plan,
                     "kpi":summary(result),"result":compact(result),"optimization_error":error})
    eligible = [row for row in rows if not row["optimization_error"] and row["kpi"]["feasible"] and not row["kpi"]["has_shortage"]]
    winner = min(eligible,key=lambda row:row["kpi"]["npv"])["strategy_id"] if eligible else None
    return {"scenario":scenario,"rows":rows,"lowest_cost_feasible_strategy":winner,
            "selection_rule":"Minimum NPV among these templates with 100% service and all constraints; not global optimization over investments."}


def comparison_bundle(plan: dict) -> dict:
    templates = strategy_templates(plan)
    base, stress = compare_strategies(templates,"BASE"), compare_strategies(templates,"MANDATORY_STRESS")
    naive = next((row for row in base["rows"] if row["strategy_id"]==base["lowest_cost_feasible_strategy"]),None)
    candidates = []
    for row in stress["rows"]:
        if row["optimization_error"]:
            continue
        # Same pre-shock contracts; later contracts may depend on the observed scenario.
        # Reusing every stress order in BASE would overfill storage, not prove resilience.
        try:
            base_optimized = optimize_supply_plan(with_contract_lock({**row["plan"],"scenario":"BASE"}))
        except OptimizationError:
            continue
        base_result = base_optimized["result"]
        if base_result["feasible"] and not base_result["kpi_summary"]["has_shortage"]:
            candidates.append((base_result["kpi_summary"]["npv"],row,base_result,base_optimized["plan"]))
    resilience = {"status":"no_common_feasible_candidate", "note":"No price of resilience asserted without two comparable feasible BASE plans."}
    if naive and candidates:
        _, resilient, resilient_base, resilient_base_plan = min(candidates,key=lambda item:item[0])
        resilient_stress_plan = validated({
            **with_contract_lock(resilient_base_plan),
            "scenario":"MANDATORY_STRESS",
            "yearly_orders":deepcopy(resilient["plan"]["yearly_orders"]),
        })
        naive_stress = calculate_plan({**naive["plan"],"scenario":"MANDATORY_STRESS"})
        resilience = {
            "status":"calculated", "naive_strategy":naive["strategy_id"],"resilient_strategy":resilient["strategy_id"],
            "price_of_resilience_mln":resilient_base["kpi_summary"]["npv"]-naive["kpi"]["npv"],
            "avoided_shortage_t":naive_stress["kpi_summary"]["total_shortage"]-resilient["kpi"]["total_shortage"],
            "naive_stress_shortage_t":naive_stress["kpi_summary"]["total_shortage"],
            "resilient_stress_shortage_t":resilient["kpi"]["total_shortage"],
            "naive_base_npv":naive["kpi"]["npv"], "resilient_base_npv":resilient_base["kpi_summary"]["npv"],
            "avoided_mission_loss_money":None,
            "resilient_base_plan":resilient_base_plan,"resilient_stress_plan":resilient_stress_plan,
            "note":"Contingent policy: identical pre-2038 annual commitments, later orders may differ with sufficient lead time. Extra NPV measured in BASE; avoided shortage in mandatory stress. Cheapest of constructed pairs, not globally optimal robust policy. Mission-loss prices unavailable.",
        }
    return {"base":base,"stress":stress,"resilience":resilience,
            "environment_note":"Standard BASE demand and unit price factors; research modifiers of the chosen plan are reset explicitly for a comparable organiser experiment. Configuration, discount and explicit reservations are retained."}


def with_contract_lock(plan: dict, shock_year: int = 2038) -> dict:
    result = deepcopy(plan)
    result["contract_lock"] = {
        "shock_year":shock_year,"baseline_orders":deepcopy(plan["yearly_orders"]),
        "baseline_reservations":deepcopy(plan.get("yearly_reservations")),
        "baseline_investments":deepcopy(plan["investments"]),
        "baseline_initial_inventory_t":plan["initial_inventory_t"],
        "baseline_c_lead_months":plan["c_lead_months"],"baseline_d_lead_months":plan["d_lead_months"],
        "policy":"freeze_annual_contract_if_first_order_precedes_shock",
    }
    return validated(result)


def stress_impact(plan: dict) -> dict:
    baseline = standard_environment(plan)
    base = calculate_plan(baseline)
    stressed = {**with_contract_lock(baseline),"scenario":"MANDATORY_STRESS"}
    stress = calculate_plan(stressed)
    adapted, error = None, None
    try:
        adapted = optimize_supply_plan(stressed)
    except OptimizationError as exc:
        error = {"message":str(exc),"details":exc.details}
    return {"base":base,"stress":stress,"base_plan":baseline,"stress_plan":stressed,
            "delta_npv_mln":stress["kpi_summary"]["npv"]-base["kpi_summary"]["npv"],
            "delta_shortage_t":stress["kpi_summary"]["total_shortage"]-base["kpi_summary"]["total_shortage"],
            "locked_contracts":[{"year":y,"source":s,"ordered_t":q} for (y,s),q in locked_contracts(stressed).items()],
            "adaptation":adapted,"adaptation_error":error,
            "note":"Whole annual contract frozen if its earliest order predates 2038. Investments and reservations stay fixed. This conservative rule may reject recovery possible with finer intra-year contracts; no perfect-foresight rebooking is claimed."}


def shock_plan(plan: dict, *, demand: float=1.0, delivery: float=1.0, delay: float=0.0, source: str="D", start_year: int=2038, end_year: int|None=None, price: float=1.0, scenario_id: str="TEAM_SENSITIVITY") -> dict:
    result = standard_environment(plan)
    years = model_data(result)[2]
    result["research_shock"] = {"scenario_id":scenario_id,"description":"Explicit deterministic research experiment; no assigned event probability.",
        "start_year":start_year,"end_year":end_year or years[-1],"demand_factor":demand,
        "sources":{source:{"delivery_factor":delivery,"price_factor":price,"capacity_factor":1.0,"delay_months":delay}},"combination_rule":"standalone"}
    return result


def crash_limits(plan: dict) -> dict:
    base = standard_environment(plan)
    baseline = calculate_plan(base)
    definitions = (
        ("demand_growth_pct",100.0,lambda x:shock_plan(base,demand=1+x/100)),
        ("D_shortfall_pct",100.0,lambda x:shock_plan(base,delivery=1-x/100)),
        ("D_delay_months",12.0,lambda x:shock_plan(base,delay=x,end_year=2038)),
    )
    limits = []
    for name, maximum, make_plan in definitions:
        def evaluate(value):
            result = calculate_plan(make_plan(value))
            return result, result["kpi_summary"]["total_shortage"] > 1e-6
        zero, failed = evaluate(0)
        if failed:
            limits.append({"parameter":name,"status":"baseline_already_short","safe_value":None,"failure_value":0.0,"failure_shortage_t":zero["kpi_summary"]["total_shortage"]})
            continue
        terminal, failed = evaluate(maximum)
        if not failed:
            limits.append({"parameter":name,"status":"not_reached_within_range","safe_value":maximum,"failure_value":None,"failure_shortage_t":None})
            continue
        low, high = 0.0, maximum
        for _ in range(18):
            middle = (low + high)/2
            result, failed = evaluate(middle)
            if failed:
                high = middle
            else:
                low = middle
        result, _ = evaluate(high)
        limits.append({"parameter":name,"status":"bounded","safe_value":low,"failure_value":high,"failure_shortage_t":result["kpi_summary"]["total_shortage"],"violations_at_failure":result["violations"]})
    return {"baseline":summary(baseline),"limits":limits,"criterion":"total shortage > 1e-6 t; does not imply all reserve/capacity constraints are satisfied", "method":"18 bisection steps, fixed plan, nonnegative demand/supply deterioration; no random simulation", "delay_semantics":"D arrival-window delay in 2038, ceil to model days; missed volume has no catch-up; committed fuel is paid. This is an adverse no-recovery bound, not a detailed transport backlog."}


def sensitivity_matrix(plan: dict) -> list[dict]:
    rows = []
    for demand in (1.0,1.1,1.25):
        for delivery in (1.0,0.75,0.55):
            result = calculate_plan(shock_plan(plan,demand=demand,delivery=delivery))
            rows.append({"demand_factor":demand,"D_delivery_factor":delivery, **summary(result)})
    for price in (0.8,1.25,1.5):
        result=calculate_plan(shock_plan(plan,source="A",price=price,scenario_id="TEAM_PRICE_SENSITIVITY"))
        rows.append({"A_price_factor":price,**summary(result)})
    return rows


def risk_register(plan: dict) -> dict:
    baseline = standard_environment(plan)
    base_result = calculate_plan(baseline)
    strengthened = strategy_templates(plan)[2]["plan"]
    try:
        mitigation = optimize_supply_plan(strengthened)["plan"]
    except OptimizationError:
        mitigation = baseline
    mitigation_base = calculate_plan(mitigation)
    definitions = [
        ("R01","Недопоставка ISRU","Снижение производительности пилота","Лунный оператор",{"delivery":0.55},"Контракт на земную подстраховку и увеличенный физический запас",["R02"]),
        ("R02","Задержка окна поставки D","Задержка приёмки и транспортной готовности","Оператор хаба / D",{"delay":2.0,"end_year":2038},"Предварительный запас, проверка готовности и альтернативные поставки",["R01"]),
        ("R03","Рост цены Earth-Core","Удорожание агрегированной поставки","Поставщик A / финансирующая сторона",{"source":"A","price":1.4},"Лимит индексации и сравнение диверсифицированных контрактов",[]),
        ("R04","Высокий спрос после 2038","Ускорение программы миссий","Оператор / заказчики миссий",{"demand":1.25},"Предварительная бронь мощности и согласование приоритетов выдачи",[]),
    ]
    rows=[]
    for rid,name,cause,owner,changes,measure,dependencies in definitions:
        shocked=shock_plan(baseline,scenario_id=f"TEAM_{rid}",**changes)
        before=calculate_plan(shocked)
        local_mitigation, local_base, local_base_plan = mitigation, mitigation_base, mitigation
        measure_status = "reserve_strategy_evaluated"
        try:
            local_mitigation = optimize_supply_plan({**strengthened,"research_shock":shocked["research_shock"]})["plan"]
            protected_base = optimize_supply_plan(with_contract_lock({**local_mitigation,"research_shock":None}))
            local_base = protected_base["result"]
            local_base_plan = protected_base["plan"]
            measure_status = "scenario_and_base_feasible_with_shared_pre_shock_contracts"
        except OptimizationError:
            local_mitigation, local_base, local_base_plan = mitigation, mitigation_base, mitigation
        mitigated={**local_mitigation,"research_shock":shocked["research_shock"]}
        after=calculate_plan(mitigated)
        rows.append({"id":rid,"risk_name":name,"cause":cause,"period":[shocked["research_shock"]["start_year"],shocked["research_shock"]["end_year"]],"owner":owner,
            "param_delta":shocked["research_shock"],"probability":None,"basis":"TEAM_ASSUMPTION: illustrative severity range; not calibrated event probability", "dependencies":dependencies,
            "impact_tons":before["kpi_summary"]["total_shortage"]-base_result["kpi_summary"]["total_shortage"],
            "impact_cost_mln":before["kpi_summary"]["npv"]-base_result["kpi_summary"]["npv"],"impact_rub":None,
            "impact_service_level":before["kpi_summary"]["min_service_level"]-base_result["kpi_summary"]["min_service_level"],
            "mitigation_measure":measure,"evaluated_measure":"60-day reserve policy, pre-event procurement and contingent later contracts; proposed legal clauses have no unpriced numerical effect", "measure_status":measure_status,
            "mitigation_cost_mln":local_base["kpi_summary"]["npv"]-base_result["kpi_summary"]["npv"],
            "avoided_shortage_t":before["kpi_summary"]["total_shortage"]-after["kpi_summary"]["total_shortage"],
            "residual_risk":summary(after),"before":summary(before),"mitigation_plan":local_mitigation,"mitigation_base_plan":local_base_plan})
    return {"rows":rows,"money_unit":"million constant-price 2035 monetary units; no RUB conversion", "method":"Deterministic severity scenarios, separate from mandatory stress; effects and residuals measured, never inferred from FMEA score products."}


def geopolitical(plan: dict) -> dict:
    baseline = standard_environment(plan)
    stressed=shock_plan(baseline,source="A",delivery=0.6,price=1.35,end_year=2039,scenario_id="TEAM_GEOPOLITICAL")
    stressed["research_shock"]["description"]="Hypothetical restrictions on terrestrial logistics: A delivered share 60% and aggregate unit price +35% in 2038–2039. Scenario assumptions, not a political forecast."
    alternatives=[]
    for template in strategy_templates(plan):
        try:
            normal=optimize_supply_plan(template["plan"])["plan"]
            after=calculate_plan({**normal,"research_shock":stressed["research_shock"]})
            alternatives.append({"strategy_id":template["strategy_id"],"name":template["name"],"before":summary(calculate_plan(normal)),"after":summary(after)})
        except OptimizationError as exc:
            alternatives.append({"strategy_id":template["strategy_id"],"error":str(exc)})
    return {"scenario":stressed["research_shock"],"before":summary(calculate_plan(baseline)),"after":summary(calculate_plan(stressed)),"alternatives":alternatives,
            "note":"ISRU and ZBO effects must be inferred from these results; autonomy does not guarantee immunity. Price coefficient applies to the aggregate channel price. Original prices restored by clearing research_shock."}


def build_report(plan: dict) -> dict:
    from app.core.validation_protocol import run_validation
    payload=validated(plan)
    return {"report_version":"1.0","generated_at":datetime.now(timezone.utc).isoformat(),"model_version":MODEL_VERSION,
            "input_version":config_version(payload),"plan_hash":hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest(),
            "plan":payload,"selected_result":calculate_plan(payload),"comparisons":comparison_bundle(payload),
            "stress_impact":stress_impact(payload),"crash_limits":crash_limits(payload),"sensitivity":sensitivity_matrix(payload),
            "risk_register":risk_register(payload),"geopolitical":geopolitical(payload),"validation":run_validation(),
            "units":{"fuel":"t","money":"million constant-price 2035 monetary units","service":"share"},
            "scope":"No probabilities or mission-loss monetary values asserted. Delays are no-catch-up adverse bounds. Research assumptions retained in each plan. Documents must use this report's hash/version."}
