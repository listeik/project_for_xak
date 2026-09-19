"""Executable evidence protocol, preserving the organiser's V01–V10 identities."""
from copy import deepcopy
from math import isclose
import json

from app.core.constants import PROJECT_ROOT, MODEL_VERSION
from app.core.balance_engine import (allocate_demand, material_balance, take_or_pay, reservation_payment,
    throughput_losses, reserve_requirement, capacity_check, apply_delivery_share, calculate_plan,
    default_plan, check_capex_limits, source_availability, startup_stock)


def run_validation() -> dict:
    rows=[]
    expected={row["case_id"]:row["expected"] for row in json.loads((PROJECT_ROOT/"validation/expected_checks.json").read_text())}
    def record(case_id, inputs, target, actual):
        def equal(a,b):
            if isinstance(a,bool) or isinstance(b,bool):
                return a is b
            return isclose(a,b,abs_tol=1e-7,rel_tol=1e-9) if isinstance(a,(int,float)) and isinstance(b,(int,float)) else a==b
        passed=set(target)==set(actual) and all(equal(target[k],actual[k]) for k in target)
        rows.append({"test_id":case_id,"inputs":inputs,"expected":target,"actual":actual,"status":"PASSED" if passed else "FAILED"})
    allocation=allocate_demand(8,10,6)
    top=take_or_pay(50,100,.7,2)
    controls=[
        ("V01",{"opening":10,"delivered":30,"losses":2,"served":25},{"closing_inventory_t":material_balance(10,30,2,25)}),
        ("V02",{"available":8,"demand":10},{"served_t":allocation["served"],"shortage_t":allocation["shortage"],"closing_inventory_t":allocation["closing_inventory"]}),
        ("V03",{"order":50,"reserved":100,"TOP":.7,"price":2},{"payable_volume_t":top["payable_volume"],"variable_payment_mln":top["variable_payment"]}),
        ("V04",{"same_as":"V03"},{"variable_payment_mln":top["variable_payment"]}),
        ("V05",{"annual_capacity":100,"rate":.4,"period_fraction":.5},{"reservation_payment_mln":reservation_payment(100,.4,.5)}),
        ("V06",{"gross":20,"loss_rate":.05},{"losses_t":throughput_losses(20,.05)}),
        ("V07",{"annual_demand":365},{"reserve_t":reserve_requirement(365)}),
        ("V08",{"reserved":12,"capacity":10},capacity_check(12,10)),
        ("V09",{"total_demand":100,"critical_subset":60},{"total_demand_t":allocate_demand(100,100,60)["served"]}),
        ("V10",{"planned":20,"share":.5,"reliability_metadata":.8},{"actual_delivery_t":apply_delivery_share(20,.5)}),
    ]
    for cid,inputs,actual in controls:
        record(cid,inputs,expected[cid],actual)
    plan=default_plan(); result=calculate_plan(plan)
    record("E01",{"gross":100,"loss_rates":[.045,.012]}, {"base_losses":4.5,"zbo_losses":1.2}, {"base_losses":throughput_losses(100,.045),"zbo_losses":throughput_losses(100,.012)})
    record("E02",{"capex_2037":1800,"additional_2040":1000},{"violations":0},{"violations":len(check_capex_limits({2037:1800,2040:1000}))})
    record("E03",{"capex_2037":1801,"additional_2040":1000},{"violations":2},{"violations":len(check_capex_limits({2037:1801,2040:1000}))})
    stress=calculate_plan({**plan,"scenario":"MANDATORY_STRESS"})
    record("E04",{"D2038":80,"D2039":110,"scenario":"MANDATORY_STRESS"},{"D2038":44.0,"D2039":82.5},{"D2038":stress["annual_balances"][3]["source_breakdown"]["D"]["delivered_t"],"D2039":stress["annual_balances"][4]["source_breakdown"]["D"]["delivered_t"]})
    record("E05",{"source":"D","year":2037},{"active_days":0},{"active_days":source_availability(plan,"D",2037)["active_days"]})
    stock=startup_stock(plan)
    record("E06",{"net_startup_t":15,"loss_rate":.045,"price":6.2},{"gross_t":15/.955,"procurement_mln":15/.955*6.2,"order_date":"2034-01-01","accounting_year":2035},{"gross_t":stock["gross_delivery_t"],"procurement_mln":stock["variable_cost"],"order_date":stock["order_date"],"accounting_year":stock["accounting_year"]})
    record("E07",{"plan":"default BASE","tolerance_t":1e-7},{"balance_closes":True,"feasible":True},{"balance_closes":max(abs(r["balance_residual"]) for r in result["annual_balances"])<1e-7,"feasible":result["feasible"]})
    for profile,expected_total in (("LOW",1112.0),("HIGH",1673.0)):
        actual=calculate_plan({**plan,"demand_profile":profile})
        # Independent sum of organiser CSV values; HIGH total is 1673 t.
        record("E08" if profile=="LOW" else "E09",{"demand_profile":profile},{"total_demand":expected_total},{"total_demand":sum(r["demand_total"] for r in actual["annual_balances"])})
    from app.schemas.plan import PlanRequest
    from pydantic import ValidationError
    invalid=deepcopy(plan);invalid["yearly_orders"][2035]["A"]=-1
    try:
        PlanRequest.model_validate(invalid);rejected=False
    except ValidationError:
        rejected=True
    record("E10",{"A2035":-1},{"rejected":True},{"rejected":rejected})
    zero=calculate_plan({**plan,"demand_factor":0.0})
    record("E11",{"demand_factor":0},{"cost_per_ton_is_null":True},{"cost_per_ton_is_null":zero["kpi_summary"]["cost_per_served_ton"] is None})
    no_zbo=deepcopy(plan);no_zbo["investments"]["zbo_year"]=None;no_zbo["scenario"]="MANDATORY_STRESS"
    actual=calculate_plan(no_zbo)
    record("E12",{"scenario":"MANDATORY_STRESS","zbo":False},{"loss_limit_years":[2038,2039,2040]}, {"loss_limit_years":[r["year"] for r in actual["violation_details"] if r["code"]=="LOSS_CEILING_EXCEEDED"]})
    from app.core.analytics import with_contract_lock
    locked=with_contract_lock(PlanRequest.model_validate(plan).model_dump())
    locked["yearly_orders"][2038]["A"]-=1
    record("E13",{"shock_year":2038,"change_A2038":-1},{"contract_change_rejected":True},{"contract_change_rejected":"SUNK_CONTRACT_CHANGED_A_2038" in calculate_plan(locked)["violations"]})
    from app.core.configuration import extended_plan
    extension=calculate_plan(PlanRequest.model_validate(extended_plan(plan)).model_dump())
    record("E14",{"extra_source":"F","last_year":2042},{"years":8,"sources":6,"balance_closes":True},{"years":len(extension["annual_balances"]),"sources":len(extension["annual_balances"][-1]["source_breakdown"]),"balance_closes":max(abs(r["balance_residual"]) for r in extension["annual_balances"])<1e-7})
    record("E15",{"scenario":"MANDATORY_STRESS","plan":"default"},{"shortage_warnings":3},{"shortage_warnings":sum(w["code"].startswith("STRESS_SHORTAGE_") for w in stress["warning_details"])})
    from app.core.response_optimizer import response_plan, optimize_response
    from app.core.balance_engine import topup_availability, annual_contract, model_date, locked_contracts
    from app.core.analytics import shock_plan
    reaction=response_plan({**deepcopy(plan),"scenario":"MANDATORY_STRESS","yearly_reservations":{y:{"B":110.0} for y in (2038,2039,2040)}})
    b=topup_availability(reaction,"B",2038);e=topup_availability(reaction,"E",2038)
    record("E16",{"decision":"2038-01-01","B_lead_months":4,"E_lead_weeks":6},
           {"B_first":"2038-05-03","B_days":243,"E_first":"2038-02-12","E_days":323},
           {"B_first":model_date(b["day_start"]),"B_days":b["active_days"],"E_first":model_date(e["day_start"]),"E_days":e["active_days"]})
    adapted=optimize_response(reaction); adapted_plan=adapted["plan"]; after=adapted["result"]
    record("E17",{"plan":"STRESS, advance B reservation 110 t/year from 2038","baseline_B2038":0},
           {"full_recovery":True,"B_topup_positive":True,"critical_shortage":0.0,"total_shortage":0.0},
           {"full_recovery":adapted["optimization"]["full_recovery"],"B_topup_positive":adapted_plan["additional_orders"].get(2038,{}).get("B",0)>0,"critical_shortage":after["kpi_summary"]["total_critical_shortage"],"total_shortage":after["kpi_summary"]["total_shortage"]})
    record("E18",{"decision":"2038-01-01","policy":"preserve commitments"},
           {"commitments_unchanged":True,"historical_stock_unchanged":True},
           {"commitments_unchanged":all(abs(adapted_plan["yearly_orders"][y][s]-q)<1e-7 for (y,s),q in locked_contracts(reaction).items()),
            "historical_stock_unchanged":all(abs(a["inventory"]-b["inventory"])<1e-7 for a,b in zip(stress["inventory_trace"],after["inventory_trace"]) if a["year"]<2038)})
    overloaded=deepcopy(reaction);overloaded["additional_orders"]={2038:{"B":74.0}}
    record("E19",{"B_topup_t":74,"B_window_days":243,"capacity_t_per_year":110},
           {"rate_violation":True},{"rate_violation":"DELIVERY_RATE_EXCEEDED_B_2038" in calculate_plan(overloaded)["violations"]})
    booked=deepcopy(plan);booked["yearly_orders"][2039]["A"]=50.0;booked["yearly_reservations"]={2039:{"A":100.0}}
    booked=response_plan(booked);booked["additional_orders"]={2039:{"A":10.0}}
    contract=annual_contract(booked,"A",2039)
    record("E20",{"A_order":50,"A_topup":10,"paid_annual_capacity":100,"TOP":0.7},
           {"payable_t":70.0,"new_reservation_mln":0.0,"incremental_procurement_mln":0.0},
           {"payable_t":contract["payable_volume_t"],"new_reservation_mln":contract["components"][1]["reservation"],"incremental_procurement_mln":contract["components"][1]["procurement"]})
    heavy=shock_plan(plan,demand=2)
    heavy["yearly_reservations"]={y:{"E":80.0} for y in (2039,2040)}
    heavy["research_shock"]["sources"]["B"]={"delivery_factor":0.0,"price_factor":1.0,"capacity_factor":1.0,"delay_months":0.0}
    partial=optimize_response(heavy)
    emergency_years=[r["year"] for r in partial["result"]["annual_balances"] if r["source_breakdown"]["E"]["ordered_t"]>1e-7]
    record("E21",{"demand_factor_from_2038":2,"B_delivery_from_2038":0},
           {"full_recovery":False,"avoided_shortage_positive":True,"residual_critical_positive":True,"reserve_violation_visible":True,"E_years":[2039,2040]},
           {"full_recovery":partial["optimization"]["full_recovery"],"avoided_shortage_positive":partial["optimization"]["avoided_shortage_t"]>0,"residual_critical_positive":partial["result"]["kpi_summary"]["total_critical_shortage"]>0,"reserve_violation_visible":any(v.startswith("RESERVE_VIOLATED_") for v in partial["result"]["violations"]),"E_years":emergency_years})
    invalid_e=deepcopy(reaction);invalid_e["additional_orders"]={y:{"E":1.0} for y in (2038,2039,2040)}
    record("E22",{"E_topup_each_year_2038_2040":1},{"streak_rejected":True},
           {"streak_rejected":"EMERGENCY_STREAK_EXCEEDED_2040" in calculate_plan(invalid_e)["violations"]})
    record("E23",{"plan":"adapted default","discount_rate":adapted_plan["discount_rate"]},
           {"daily_material_residual":0.0,"npv_matches_annual_cash":True,"component_procurement_matches":True},
           {"daily_material_residual":max(abs(r["balance_residual"]) for r in after["annual_balances"]),
            "npv_matches_annual_cash":isclose(after["kpi_summary"]["npv"],sum(r["total_cost"]/(1+adapted_plan["discount_rate"])**(r["year"]-2035) for r in after["annual_balances"]),abs_tol=1e-7),
            "component_procurement_matches":all(isclose(sum(c["procurement"] for c in after["source_schedule"] if c["kind"]!="startup" and c["year"]==r["year"]),sum(c["procurement"] for c in r["source_breakdown"].values()),abs_tol=1e-7) for r in after["annual_balances"])})
    rejected=[]
    for extra in ({2038:{"B":-1}},{2037:{"B":1}}):
        try:
            PlanRequest.model_validate({**reaction,"additional_orders":extra});rejected.append(False)
        except ValidationError:
            rejected.append(True)
    record("E24",{"topups":["negative","before decision"]},{"schema_rejections":[True,True]},{"schema_rejections":rejected})
    late=deepcopy(plan);late["investments"]["exercise_c_year"]=2037
    late=response_plan(late);late["additional_orders"]={2038:{"C":1.0}}
    late_result=calculate_plan(late)
    record("E25",{"C_topup_in_shock_year":1.0,"C_preparation_months":24,"exercise_year":2037},
           {"unavailable_topup_flagged":True,"additional_delivered":0.0},
           {"unavailable_topup_flagged":"TOPUP_UNAVAILABLE_C_2038" in late_result["violations"],"additional_delivered":next(r["delivered_t"] for r in late_result["source_schedule"] if r["kind"]=="additional" and r["source_id"]=="C")})
    record("E26",{"CAPEX_through_2037":1790,"limit":1800},
           {"headroom_mln":10.0,"warning":True},
           {"headroom_mln":result["kpi_summary"]["capex_headroom_2037"],"warning":any(w["code"]=="CAPEX_HEADROOM_LOW_2037" for w in result["warning_details"])})
    unbooked=response_plan(deepcopy(plan));unbooked["additional_orders"]={2038:{"B":1.0}}
    record("E27",{"B_booking":0,"B_topup":1,"policy":"booked_only"},{"unsecured_flag":True},
           {"unsecured_flag":"UNSECURED_CAPACITY_B_2038" in calculate_plan(unbooked)["violations"]})
    conditional={**unbooked,"response_capacity_policy":"conditional_market"}
    record("E28",{"B_topup":1,"policy":"conditional_market","new_fraction":1},{"unsecured_flag":False},
           {"unsecured_flag":"UNSECURED_CAPACITY_B_2038" in calculate_plan(conditional)["violations"]})
    c=topup_availability(unbooked,"C",2038)
    record("E29",{"C_exercise":2035,"preparation_months":24,"delivery_months":4},
           {"commission":"2037-01-01","topup_first":"2038-05-03"},
           {"commission":model_date(c["commission_day"]),"topup_first":model_date(c["day_start"])})
    from app.core.analytics import common_earth_shock
    common=calculate_plan(common_earth_shock(plan))
    row=common["annual_balances"][3]["source_breakdown"]
    record("E30",{"common_earth_delivery":0.5,"year":2038,"D_independent":True},
           {"A_delivered":95.0,"D_delivered":80.0,"scenario":"BASE"},
           {"A_delivered":row["A"]["delivered_t"],"D_delivered":row["D"]["delivered_t"],"scenario":common["scenario"]})
    strict=optimize_response({**plan,"scenario":"MANDATORY_STRESS"})
    record("E31",{"plan":"default STRESS","no_extra_booking":True},
           {"full_recovery":False,"shortage_t":147.828,"no_new_capacity":True},
           {"full_recovery":strict["optimization"]["full_recovery"],"shortage_t":strict["result"]["kpi_summary"]["total_shortage"],"no_new_capacity":all(a.get("reservation_mln",0)<1e-7 for a in strict["actions"])})
    reduced=deepcopy(booked);reduced["yearly_orders"][2039]["A"]=40.0;reduced["additional_orders"]={}
    paid=annual_contract(reduced,"A",2039)
    record("E32",{"A_rebooked":40,"original_capacity":100,"TOP":0.7},
           {"reserved_rate":100.0,"payable_t":70.0},
           {"reserved_rate":paid["reserved_capacity_t_per_year"],"payable_t":paid["payable_volume_t"]})
    return {"model_version":MODEL_VERSION,"tolerance":"absolute 1e-7; relative 1e-9","rows":rows,"passed":all(r["status"]=="PASSED" for r in rows),"note":"Independent organiser controls V01–V10; E-series extends them. Protocol execution is not proof of economic optimality."}
