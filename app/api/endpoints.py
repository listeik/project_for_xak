"""Stateless REST endpoints: all calculations use the shared domain engine."""

from __future__ import annotations

import hashlib
import io
import json
from typing import Literal

import pandas as pd
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import Response

from app.core.balance_engine import calculate_plan, default_plan
from app.core.constants import INPUT_VERSION, case_metadata
from app.schemas.plan import HealthResponse, PlanRequest

router = APIRouter(prefix="/api/v1", tags=["Fuel planning"])


@router.get("/health", response_model=HealthResponse)
def health() -> HealthResponse:
    return HealthResponse(input_version=INPUT_VERSION, model_version="1.0-daily")


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
        "scenario_id": result["scenario"],
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
        "risk_register_note": "Реестр FMEA не заполнен; вероятностная модель риска не выполнялась.",
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
        "assumptions": _flat_records(
            [{"parameter": key, "value": value} for key, value in result["assumptions"].items()]
        ),
        "plan": _flat_records([{"parameter": key, "value": value} for key, value in plan.items()]),
        "metadata": _flat_records(
            [
                {"parameter": "scenario_id", "value": result["scenario"]},
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
        "scenario_id": result["scenario"],
        "plan_id": result["plan_id"],
        "input_version": result["input_version"],
        "model_version": result["model_version"],
        "fuel_unit": result["units"]["fuel"],
        "money_unit": result["units"]["money"],
        "assumptions_json": json.dumps(result["assumptions"], ensure_ascii=False, allow_nan=False),
        "plan_json": json.dumps(plan, ensure_ascii=False, allow_nan=False),
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
