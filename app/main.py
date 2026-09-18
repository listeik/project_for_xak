"""FastAPI entry point: run with uvicorn app.main:app."""

from __future__ import annotations

import logging
import math
import os

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.endpoints import router

logger = logging.getLogger(__name__)


def _safe_error_value(value):
    """Validation errors can contain exception objects and rejected NaN inputs."""
    if isinstance(value, dict):
        return {str(key): _safe_error_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_safe_error_value(item) for item in value]
    if isinstance(value, float) and not math.isfinite(value):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


app = FastAPI(
    title="Топливный космоконтур 2035–2040",
    description="Суточный материальный и финансовый баланс орбитального топливного узла.",
    version="1.0.0",
)

origins = [
    origin.strip().rstrip("/")
    for origin in os.getenv(
        "ALLOWED_ORIGINS", "http://localhost:5173,http://localhost:8080"
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
    expose_headers=["Content-Disposition"],
)


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, error: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content={
            "message": "Проверьте JSON, все годы 2035–2040, каналы A–E и допустимые значения полей.",
            "detail": _safe_error_value(error.errors()),
        },
    )


@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, error: HTTPException):
    message = error.detail.get("message", "Ошибка запроса.") if isinstance(error.detail, dict) else str(error.detail)
    return JSONResponse(
        status_code=error.status_code,
        content={"message": message, "detail": _safe_error_value(error.detail)},
        headers=error.headers,
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, error: Exception):
    logger.exception("Unhandled API error on %s", request.url.path, exc_info=error)
    return JSONResponse(
        status_code=500,
        content={
            "message": "Не удалось выполнить расчёт. Повторите запрос или проверьте журнал сервера.",
            "detail": "INTERNAL_SERVER_ERROR",
        },
    )


app.include_router(router)
