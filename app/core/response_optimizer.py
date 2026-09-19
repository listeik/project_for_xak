"""Dated recourse and partial recovery, independently replayed by the daily engine.

Annual base contracts keep their original schedule. New contracts use a separate
post-decision window. MILP enforces greedy daily issue and Emergency-year supports;
it never invents inventory or postpones unmet demand into a later day.
"""
from copy import deepcopy
from time import perf_counter
import warnings

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

from app.core.balance_engine import (calculate_plan, source_contract,
    topup_availability, effective_year_data, locked_contracts, reserve_requirement, response_capacity_limit)
from app.core.configuration import model_data, source_shock
from app.core.constants import FIRST_YEAR, DAYS_PER_YEAR, EPSILON
from app.core.optimizer import OptimizationError
from app.schemas.plan import PlanRequest


def response_plan(plan: dict, shock_year: int = 2038) -> dict:
    """Retain original provenance when reopening a response; never lock it twice."""
    p = deepcopy(plan)
    lock = p.get("contract_lock")
    if lock and lock["policy"] == "preserve_commitments_allow_timed_topups":
        return PlanRequest.model_validate(p).model_dump()
    p["additional_orders"] = {}
    p["contract_lock"] = {
        "shock_year": shock_year, "baseline_orders":deepcopy(p["yearly_orders"]),
        "baseline_reservations":deepcopy(p.get("yearly_reservations")),
        "baseline_investments":deepcopy(p["investments"]),
        "baseline_initial_inventory_t":p["initial_inventory_t"],
        "baseline_c_lead_months":p["c_lead_months"], "baseline_d_lead_months":p["d_lead_months"],
        "baseline_c_delivery_lead_months":p.get("c_delivery_lead_months",4.0),
        "policy":"preserve_commitments_allow_timed_topups",
    }
    return PlanRequest.model_validate(p).model_dump()


class Program:
    def __init__(self):
        self.lower=[]; self.upper=[]; self.integrality=[]; self.cost=[]
        self.rows=[]; self.row_lower=[]; self.row_upper=[]

    def var(self, lower=0.0, upper=np.inf, integer=False, cost=0.0):
        i=len(self.lower)
        self.lower.append(lower); self.upper.append(upper)
        self.integrality.append(int(integer)); self.cost.append(cost)
        return i

    def row(self, values, lower=-np.inf, upper=np.inf):
        self.rows.append(values); self.row_lower.append(lower); self.row_upper.append(upper)

    def solve(self, objective):
        r=[]; c=[]; v=[]
        for i,row in enumerate(self.rows):
            for j,value in row.items():
                if value:
                    r.append(i);c.append(j);v.append(value)
        matrix=coo_matrix((v,(r,c)),shape=(len(self.rows),len(self.lower))).tocsc()
        with warnings.catch_warnings():
            # scipy forwards these native HiGHS tolerances verbatim.
            warnings.filterwarnings("ignore",message="Unrecognized options detected.*",category=RuntimeWarning)
            return milp(np.asarray(objective),integrality=np.asarray(self.integrality),
                        bounds=Bounds(self.lower,self.upper),
                        constraints=LinearConstraint(matrix,self.row_lower,self.row_upper),
                        options={"time_limit":25.0,"mip_rel_gap":1e-9,
                                 "mip_feasibility_tolerance":1e-9,"primal_feasibility_tolerance":1e-9})


def optimize_response(plan: dict, *, service_targets: tuple[float,float] | None = None) -> dict:
    """Partial recovery is lexicographic: critical, total, reserve gap, NPV.

    service_targets selects an ex-ante minimum-cost benchmark at fixed investments.
    There is no service rationing policy: daily issue remains greedy critical-first.
    """
    started=perf_counter()
    p=PlanRequest.model_validate(plan).model_dump()
    response=service_targets is None
    if response:
        p=response_plan(p)
    elif p.get("contract_lock") or p.get("additional_orders"):
        raise OptimizationError("Сравнение целей сервиса выполняется для предварительного плана без режима реакции.")
    sources,_,years=model_data(p)
    lock=p.get("contract_lock")
    if response:
        # Reset to original commitments before planning another reaction.
        p["yearly_orders"]=deepcopy(lock["baseline_orders"])
        p["additional_orders"]={}
    before=calculate_plan(p)
    fixed_codes=("CAPEX_", "FUTURE_CAPEX", "INVESTMENT_", "ZBO_TOO", "C_OPTION", "ISRU_FUNDING", "LOSS_CEILING", "SUNK_RESERVATION")
    blocked=[r for r in before["violation_details"] if r["code"].startswith(fixed_codes)]
    if blocked:
        raise OptimizationError("Закупки не исправят фиксированные инвестиционные или договорные нарушения.",blocked)
    frozen=locked_contracts(p) if response else {}
    decision=(lock["shock_year"]-FIRST_YEAR)*DAYS_PER_YEAR if response else 0
    count=len(years)*DAYS_PER_YEAR
    prefix=[t for t in before["inventory_trace"] if t["day"]>0]
    model=Program(); net=[{} for _ in range(count)]
    orders={}; extras={}; payables={}; reserves={}; emergency={}
    year_data={y:effective_year_data(p,y) for y in years}
    constant=0.0
    for y in years:
        data=year_data[y]; disc=(1+p["discount_rate"])**-(y-FIRST_YEAR)
        e=model.var(upper=1,integer=True); emergency[y]=e
        for s,source in sources.items():
            contract=source_contract(p,s,y)
            f=contract["period_fraction"]; startup=contract["startup_ordered_t"]
            cap=source["capacity_t_per_year"]*source_shock(p,s,y).get("capacity_factor",1.0)
            upper=max(0.0,cap*f-startup)
            if contract["reservation_explicit"]:
                upper=min(upper,max(0.0,contract["reserved_period_t"]-startup))
            committed=frozen.get((y,s))
            if committed is not None and committed>upper+EPSILON:
                raise OptimizationError("Ранее принятые обязательства превышают мощность или бронь.",[{"year":y,"source":s}])
            q=model.var(lower=committed if committed is not None else 0.0,
                        upper=committed if committed is not None else upper)
            orders[y,s]=q
            avail=topup_availability(p,s,y) if response else None
            g=avail["period_fraction"] if avail else 0.0
            x=model.var(upper=cap*g if g and avail["active_days"] else 0.0); extras[y,s]=x
            # Rate capacity is shared during the overlapping delivery windows.
            rate={q:1/f if f else 0.0,x:1/g if g else 0.0}
            model.row(rate,upper=cap-(startup/f if f else 0.0))
            if response and y>=lock["shock_year"]:
                permitted=response_capacity_limit(p,s,y,contract["reserved_capacity_t_per_year"])
                model.row(rate,upper=permitted-(startup/f if f else 0.0))
            if s=="E":
                model.row({q:1,x:1,e:-source["capacity_t_per_year"]},upper=0)
            new_reserved=model.var(upper=cap*g if g else 0.0,
                                   cost=source["reservation_rate_mln_per_t_year_capacity"]*disc)
            reserves[y,s]=new_reserved
            if contract["reservation_explicit"]:
                r=contract["reserved_capacity_t_per_year"]
                # New rate fills only the shortfall after reusing previously paid capacity.
                model.row({q:g/f if f else 0.0,x:1,new_reserved:-1},upper=r*g-(startup*g/f if f else 0.0))
                model.row({new_reserved:1},upper=max(0.0,(cap-r)*g))
                reserved_constant=contract["reserved_period_t"]
                reserved_coeff={new_reserved:1}
                constant+=contract["reservation"]*disc
            else:
                # Automatic regular reservation equals its volume, topup volume likewise.
                model.row({x:1,new_reserved:-1},lower=0,upper=0)
                model.cost[q]+=source["reservation_rate_mln_per_t_year_capacity"]*disc
                constant+=startup*source["reservation_rate_mln_per_t_year_capacity"]*disc
                reserved_constant=startup
                reserved_coeff={q:1,new_reserved:1}
            pay=model.var(cost=data["prices"][s]*disc);payables[y,s]=pay
            model.row({q:1,x:1,pay:-1},upper=-startup)
            model.row({**{i:a*source["take_or_pay_share"] for i,a in reserved_coeff.items()},pay:-1},upper=-reserved_constant*source["take_or_pay_share"])
            for var,a in ((q,contract),(x,avail)):
                if a and a["active_days"]:
                    coefficient=data["delivery_shares"][s]*a["timely_share"]*(1-data["loss_rate"])/a["active_days"]
                    for day in range(a["day_start"],a["day_end"]):
                        net[day][var]=coefficient
        row=before["annual_balances"][y-FIRST_YEAR]
        constant+=(row["fixed_opex"]+row["capex"])*disc
    for i in range(len(years)-2):
        model.row({emergency[y]:1 for y in years[i:i+3]},upper=2)
    inventories=[]; shortages=[]; critical=[]; reserve_gaps=[]
    for day in range(count):
        y=years[day//365]; data=year_data[y]
        demand=data["demand_total"]/365; crit=data["demand_critical"]/365
        capacity=data["storage_capacity"]
        inventory=model.var(upper=capacity);short=model.var(upper=demand);cs=model.var(upper=crit)
        inventories.append(inventory);shortages.append(short);critical.append(cs)
        row={inventory:1,short:-1,**{i:-v for i,v in net[day].items()}}
        if day:
            row[inventories[day-1]]=-1;opening=0
        else:
            opening=p["initial_inventory_t"]
        model.row(row,lower=opening-demand,upper=opening-demand)
        pre={**net[day]}
        if day: pre[inventories[day-1]]=1
        model.row(pre,upper=capacity-opening)
        model.row({short:1,cs:-1},upper=demand-crit)
        if day<decision:
            # Replay historical state exactly; no retrospective rationing or extra supply.
            for var,value in ((inventory,prefix[day]["inventory"]),(short,prefix[day]["shortage"])):
                model.lower[var]=model.upper[var]=max(0.0,value)
        elif service_targets != (1.0,1.0):
            binary=model.var(upper=1,integer=True)
            model.row({inventory:1,binary:capacity},upper=capacity)
            model.row({short:1,binary:-demand},upper=0)
        if service_targets == (1.0,1.0):
            model.upper[short]=0;model.upper[cs]=0
        weight=data["holding_rate"]/365*(1+p["discount_rate"])**-(y-FIRST_YEAR)
        # Mean of pre-issue and closing stock = closing + (demand-shortage)/2.
        model.cost[inventory]+=weight;model.cost[short]-=weight/2;constant+=weight*demand/2
        if day%365==0:
            required=reserve_requirement(data["demand_total"],p["reserve_target_days"])
            gap=model.var(upper=required if response else 0.0);reserve_gaps.append(gap)
            values={gap:1}
            if day: values[inventories[day-1]]=1
            model.row(values,lower=required-opening)
    if service_targets:
        total_target,critical_target=service_targets
        for y in years:
            start=(y-FIRST_YEAR)*365
            model.row({shortages[i]:1 for i in range(start,start+365)},upper=year_data[y]["demand_total"]*(1-total_target))
            model.row({critical[i]:1 for i in range(start,start+365)},upper=year_data[y]["demand_critical"]*(1-critical_target))
    stages=[]
    objectives=([("critical_shortage",critical),("total_shortage",shortages),("reserve_gap",reserve_gaps)] if response else [])
    allowed_prefixes=("RESERVE_VIOLATED_","SERVICE_LEVEL_VIOLATED_","CRITICAL_SERVICE_LEVEL_VIOLATED_")
    baseline_attainable=not any(not r["code"].startswith(allowed_prefixes) for r in before["violation_details"])
    baseline_objectives={"critical_shortage":before["kpi_summary"]["total_critical_shortage"],
                         "total_shortage":before["kpi_summary"]["total_shortage"],
                         "reserve_gap":before["kpi_summary"]["reserve_deficit_t"]}
    # Prove each lexicographic stage before optimizing the next one.
    for name,indices in objectives:
        objective=np.zeros(len(model.lower));objective[indices]=1
        if baseline_attainable and baseline_objectives[name]<1e-7:
            optimum=0.0
            proof="Feasible baseline attains the nonnegative lower bound."
        else:
            solved=model.solve(objective)
            if not solved.success:
                raise OptimizationError("Решатель не подтвердил результат реакции за отведённое время или ограничения несовместимы.",[{"stage":name,"status":int(solved.status),"message":solved.message}])
            optimum=float(objective@solved.x)
            proof="HiGHS optimal status."
        baseline_attainable=baseline_attainable and baseline_objectives[name]<=optimum+1e-7
        stages.append({"objective":name,"value":optimum,"proof":proof})
        # HiGHS' mixed-integer feasibility tolerance is larger than 1e-8.
        # Keep zero targets exact; allow one microton for positive stage optima.
        model.row({i:1 for i in indices},upper=0.0 if optimum<1e-7 else optimum+1e-6)
    solved=model.solve(model.cost)
    if not solved.success:
        raise OptimizationError("Не найден подтверждённый допустимый план для выбранной цели сервиса.",[{"stage":"cost","status":int(solved.status),"message":solved.message}])
    optimized=deepcopy(p)
    optimized["yearly_orders"]={y:{s:max(0.0,float(solved.x[orders[y,s]])) for s in sources} for y in years}
    optimized["additional_orders"]={y:{s:float(solved.x[extras[y,s]]) for s in sources if solved.x[extras[y,s]]>1e-7} for y in years}
    optimized["additional_orders"]={y:q for y,q in optimized["additional_orders"].items() if q}
    if response:
        # Equivalent windows should not produce artificial cancel-and-reorder actions.
        for y,quantities in optimized["additional_orders"].items():
            for s in list(quantities):
                regular=source_contract(p,s,y);extra=topup_availability(p,s,y)
                if (y,s) not in frozen and regular["day_start"]==extra["day_start"] and regular["period_fraction"]==extra["period_fraction"]:
                    moved=min(quantities[s],max(0.0,model.upper[orders[y,s]]-optimized["yearly_orders"][y][s]))
                    optimized["yearly_orders"][y][s]+=moved;quantities[s]-=moved
            optimized["additional_orders"][y]={s:q for s,q in quantities.items() if q>1e-7}
        optimized["additional_orders"]={y:q for y,q in optimized["additional_orders"].items() if q}
    result=calculate_plan(optimized)
    physical=[r for r in result["violation_details"] if not r["code"].startswith(("RESERVE_VIOLATED_","SERVICE_LEVEL_VIOLATED_","CRITICAL_SERVICE_LEVEL_VIOLATED_"))]
    lp_total=sum(solved.x[i] for i in shortages)
    lp_critical=sum(solved.x[i] for i in critical)
    lp_npv=float(np.dot(model.cost,solved.x)+constant)
    if physical or abs(result["kpi_summary"]["total_shortage"]-lp_total)>2e-5 or abs(result["kpi_summary"]["npv"]-lp_npv)>2e-5 or (response and abs(result["kpi_summary"]["total_critical_shortage"]-lp_critical)>2e-5):
        raise OptimizationError("Результат не прошёл независимый суточный пересчёт.",[{"violations":physical,"engine_npv":result["kpi_summary"]["npv"],"solver_npv":lp_npv,"engine_shortage":result["kpi_summary"]["total_shortage"],"solver_shortage":lp_total,"engine_critical":result["kpi_summary"]["total_critical_shortage"],"solver_critical":lp_critical}])
    if service_targets and not result["feasible"]:
        raise OptimizationError("План не проходит требования сервиса и резерва при повторной проверке.",result["violation_details"])
    if response and result["violations"]==before["violations"] and all(abs(result["kpi_summary"][k]-before["kpi_summary"][k])<2e-5 for k in ("npv","total_shortage","total_critical_shortage","reserve_deficit_t")):
        optimized=deepcopy(p);result=before
    actions=[]
    for item in result["source_schedule"]:
        if item["kind"]=="additional" and item["ordered_t"]>1e-7:
            actions.append({"kind":"additional","year":item["year"],"source":item["source_id"],"ordered_t":item["ordered_t"],"delivered_t":item["delivered_t"],"first_order_date":item["first_order_date"],"first_arrival_date":item["first_arrival_date"],"procurement_mln":item["procurement"],"reservation_mln":item["reservation"]})
        elif item["kind"]=="regular" and response:
            old=p["yearly_orders"][item["year"]][item["source_id"]]
            if abs(item["ordered_t"]-old)>1e-7:
                actions.append({"kind":"future_rebooking","year":item["year"],"source":item["source_id"],"before_t":old,"ordered_t":item["ordered_t"],"delivered_t":item["delivered_t"],"first_order_date":item["first_order_date"],"first_arrival_date":item["first_arrival_date"]})
    return {"plan":optimized,"result":result,"actions":actions,"optimization":{
        "status":"optimal_within_model", "elapsed_seconds":perf_counter()-started,"stages":stages,
        "npv_before":before["kpi_summary"]["npv"],"npv_after":result["kpi_summary"]["npv"],
        "additional_npv_mln":result["kpi_summary"]["npv"]-before["kpi_summary"]["npv"],
        "avoided_shortage_t":before["kpi_summary"]["total_shortage"]-result["kpi_summary"]["total_shortage"],
        "full_recovery":result["feasible"] and not result["kpi_summary"]["has_shortage"],
        "explanation":("Последовательные цели: критический дефицит, общий дефицит, недостаток резерва, NPV. Ограничения склада, сроков, мощности и Emergency не ослабляются. Недостаток резерва отображается нарушением; выдача ежедневная с приоритетом критического спроса. Известна вся траектория сценария: это условный план реакции, не прогноз будущих шоков." if response else "Минимум NPV при заданных годовых порогах общего и критического сервиса, фиксированных инвестициях, начальном запасе и физическом резерве. Ежедневная выдача с приоритетом критического спроса; дефицит не переносится.")}}
