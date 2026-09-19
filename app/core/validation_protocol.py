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
    return {"model_version":MODEL_VERSION,"tolerance":"absolute 1e-7; relative 1e-9","rows":rows,"passed":all(r["status"]=="PASSED" for r in rows),"note":"Independent organiser controls V01–V10; E-series extends them. Protocol execution is not proof of economic optimality."}
