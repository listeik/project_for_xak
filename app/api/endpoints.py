"""Stateless REST endpoints: all calculations use the shared domain engine."""

from __future__ import annotations

import hashlib
import io
import json
from typing import Literal
from threading import BoundedSemaphore
import csv

import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from app.core.balance_engine import calculate_plan, default_plan
from app.core.constants import INPUT_VERSION, MODEL_VERSION, case_metadata
from app.schemas.plan import HealthResponse, PlanRequest

router = APIRouter(prefix="/api/v1", tags=["Fuel planning"])
analytics_slot = BoundedSemaphore(1)


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(input_version=INPUT_VERSION, model_version=MODEL_VERSION)


@router.get("/case")
def get_case() -> dict:
    return case_metadata()


@router.get("/default-plan", response_model=PlanRequest)
def get_default_plan() -> dict:
    return default_plan()


@router.post("/calculate")
def calculate(plan: PlanRequest) -> dict:
    """Return balances and all violations; infeasible plans are valid calculations."""
    return calculate_plan(plan.model_dump())


@router.post("/optimize")
def optimize(plan: PlanRequest) -> dict:
    """Optimize orders at fixed investments and revalidate the resulting plan."""
    # Lazy loading keeps metadata and manual calculations independent of solver startup.
    from app.core.optimizer import OptimizationError, optimize_supply_plan

    try:
        return optimize_supply_plan(plan.model_dump())
    except OptimizationError as error:
        raise HTTPException(
            status_code=422,
            detail={
                "message": str(error),
                "details": getattr(error, "details", []),
                "code": "OPTIMIZATION_INFEASIBLE",
            },
        ) from error


def export_envelope(plan: dict, result: dict) -> dict:
    """Match the organiser export.schema.json and retain the complete engine result."""
    return {
        "scenario_id": result["scenario_id"],
        "plan_id": result["plan_id"],
        "units": result["units"],
        "assumptions_reference": {
            "document": "docs/MODEL.md",
            "input_version": result["input_version"],
            "model_version": result["model_version"],
            "assumptions": result["assumptions"],
        },
        "yearly_balance": result["annual_balances"],
        "source_schedule": result["source_schedule"],
        "inventory_trace": result["inventory_trace"],
        "financial_breakdown": result["financial_breakdown"]["annual"],
        "constraint_checks": [
            {
                "check": "overall_feasibility",
                "passed": result["feasible"],
                "violation_count": len(result["violation_details"]),
            },
            *result["violation_details"],
        ],
        "risk_register": [],
        "warning_details": result["warning_details"],
        "risk_register_note": "Реестр рисков рассчитывается отдельно в /analytics/risks или /contest-export; обычный экспорт содержит только текущий баланс.",
        "plan": plan,
        "result": result,
    }


def _flat_records(records: list[dict]) -> pd.DataFrame:
    """Nested values become explicit JSON cells instead of Python repr strings."""
    return pd.DataFrame(
        [
            {
                key: json.dumps(value, ensure_ascii=False, allow_nan=False)
                if isinstance(value, (dict, list))
                else value
                for key, value in row.items()
            }
            for row in records
        ]
    )


def _xlsx_bytes(plan: dict, result: dict) -> bytes:
    buffer = io.BytesIO()
    frames = {
        "annual_balances": _flat_records(result["annual_balances"]),
        "financial": _flat_records(result["financial_breakdown"]["annual"]),
        "source_schedule": _flat_records(result["source_schedule"]),
        "inventory": _flat_records(result["inventory_trace"]),
        "violations": _flat_records(result["violation_details"]),
        "warnings": _flat_records(result["warning_details"]),
        "assumptions": _flat_records(
            [{"parameter": key, "value": value} for key, value in result["assumptions"].items()]
        ),
        "plan": _flat_records([{"parameter": key, "value": value} for key, value in plan.items()]),
        "metadata": _flat_records(
            [
                {"parameter": "scenario_id", "value": result["scenario_id"]},
                {"parameter": "plan_id", "value": result["plan_id"]},
                {"parameter": "input_version", "value": result["input_version"]},
                {"parameter": "model_version", "value": result["model_version"]},
                {"parameter": "units", "value": result["units"]},
                {"parameter": "feasible", "value": result["feasible"]},
            ]
        ),
    }
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        for name, frame in frames.items():
            frame.to_excel(writer, index=False, sheet_name=name)
            sheet = writer.sheets[name]
            sheet.freeze_panes = "A2"
            if len(frame.columns):
                sheet.auto_filter.ref = sheet.dimensions
            for column in sheet.columns:
                sheet.column_dimensions[column[0].column_letter].width = min(
                    55, max(15, max(len(str(cell.value or "")) for cell in column) + 2)
                )
                for cell in column:
                    # User-supplied plan IDs must remain literal text, never Excel formulae.
                    if cell.data_type == "f":
                        cell.data_type = "s"
    return buffer.getvalue()


def _csv_bytes(plan: dict, result: dict) -> bytes:
    metadata = {
        "scenario_id": result["scenario_id"],
        "demand_profile": result["demand_profile"],
        "plan_id": result["plan_id"],
        "input_version": result["input_version"],
        "model_version": result["model_version"],
        "fuel_unit": result["units"]["fuel"],
        "money_unit": result["units"]["money"],
        "assumptions_json": json.dumps(result["assumptions"], ensure_ascii=False, allow_nan=False),
        "plan_json": json.dumps(plan, ensure_ascii=False, allow_nan=False),
        "warnings_json": json.dumps(result["warning_details"], ensure_ascii=False, allow_nan=False),
    }
    frame = _flat_records([{**metadata, **row} for row in result["annual_balances"]])
    # Spreadsheet programs interpret these prefixes as executable formulae.
    # Keep the original string in JSON/XLSX while making CSV cells literal text.
    for column in frame.columns:
        frame[column] = frame[column].map(
            lambda value: "'" + value
            if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@"))
            else value
        )
    return frame.to_csv(index=False).encode("utf-8-sig")


@router.post("/export")
def export_plan(
    plan: PlanRequest,
    format: Literal["csv", "xlsx", "json"] = Query(default="csv"),
) -> Response:
    """Recalculate exactly the submitted plan and return a downloadable result."""
    payload = plan.model_dump()
    result = calculate_plan(payload)
    # Only a digest of the user plan name enters the filename/header.
    digest = hashlib.sha256(result["plan_id"].encode("utf-8")).hexdigest()[:10]
    filename = f"fuel-contour-{result['scenario'].lower()}-{digest}.{format}"
    if format == "json":
        content = json.dumps(export_envelope(payload, result), ensure_ascii=False, allow_nan=False).encode("utf-8")
        media_type = "application/json"
    elif format == "xlsx":
        content = _xlsx_bytes(payload, result)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    else:
        content = _csv_bytes(payload, result)
        media_type = "text/csv; charset=utf-8"
    return Response(
        content=content,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.post("/extension-demo")
def extension_demo(plan: PlanRequest, last_year: int = Query(default=2042, ge=2041, le=2045)) -> dict:
    from app.core.configuration import extended_plan, model_data
    payload = PlanRequest.model_validate(extended_plan(plan.model_dump(), last_year)).model_dump()
    sources, demand, years = model_data(payload)
    metadata = case_metadata()
    metadata.update(years=list(years),sources=list(sources.values()),demand=list(demand.values()))
    return {"plan":payload,"case_data":metadata,"result":calculate_plan(payload)}


@router.post("/analytics/{kind}")
def analytics(plan: PlanRequest, kind: Literal["comparison","stress","limits","risks","geopolitical","report"]) -> dict:
    from app.core.analytics import comparison_bundle, stress_impact, crash_limits, risk_register, geopolitical, build_report
    if not analytics_slot.acquire(blocking=False):
        raise HTTPException(429,"Аналитический расчёт уже выполняется. Повторите запрос после его завершения.")
    try:
        operation={"comparison":comparison_bundle,"stress":stress_impact,"limits":crash_limits,"risks":risk_register,"geopolitical":geopolitical,"report":build_report}[kind]
        return operation(plan.model_dump())
    finally:
        analytics_slot.release()


@router.post("/contest-export")
def contest_export(plan: PlanRequest, format: Literal["json","csv"] = Query(default="json")) -> Response:
    report = analytics(plan, "report")
    if format == "json":
        content=json.dumps(report,ensure_ascii=False,allow_nan=False).encode("utf-8")
        media_type="application/json"
    else:
        buffer=io.StringIO(newline="")
        writer=csv.writer(buffer)
        writer.writerow(["section","path","value_json","money_unit","fuel_unit"])
        def visit(value, path):
            if isinstance(value,dict) and value:
                for key,item in value.items():
                    visit(item,path+[str(key)])
            elif isinstance(value,list) and value:
                for index,item in enumerate(value):
                    visit(item,path+[str(index)])
            else:
                # JSON strings start with a quote; untrusted content cannot become a formula.
                writer.writerow([path[0],"/".join(path),json.dumps(value,ensure_ascii=False,allow_nan=False),"million constant-price 2035 units","t"])
        visit(report,[])
        content=buffer.getvalue().encode("utf-8-sig")
        media_type="text/csv; charset=utf-8"
    return Response(content,media_type=media_type,headers={"Content-Disposition":f'attachment; filename="contest-report-{report["plan_hash"][:10]}.{format}"'})
