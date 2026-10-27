"""FastAPI entry point for the calculator collection.

`/` is the tool hub; `/interest/`, `/tax/` and `/pension/` are static pages and
the remaining tools are rendered from a shared template. Each tool has its own
`/api/.../calculate` endpoint.
"""

from __future__ import annotations

import os
import signal
import threading
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field

from app import city_params, pension, pension_regions, tax, tool_registry
from app.calculator import InputError, analyze, to_response

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"
TEMPLATES_DIR = BASE_DIR / "app" / "templates"
PACKAGED = os.environ.get("CALC_TOOLKIT_APP") == "1"
templates = Jinja2Templates(directory=TEMPLATES_DIR)


Mode = Literal[
    "equal_installment",
    "equal_principal",
    "interest_only",
    "flat_rate",
    "simple_bullet",
]
PeriodUnit = Literal["year", "quarter", "month", "day"]
Concession = Literal["none", "full_waiver", "first_periods", "amount", "rate_discount"]


class CalcRequest(BaseModel):
    principal: str
    interest: str | None = None
    payment: str | None = None
    periods: str
    period_value: str = "1"
    period_unit: PeriodUnit = "month"
    mode: Mode
    concession: Concession = "none"
    concession_value: str | None = None


class ScheduleRow(BaseModel):
    period: int
    payment: str
    principal: str
    interest: str
    balance: str


class ScheduleTotal(BaseModel):
    payment: str
    principal: str
    interest: str


class ConcessionInfo(BaseModel):
    type: Concession
    label: str
    detail: str
    waived_interest: str
    net_interest: str
    base_annual_rate_percent: str | None


class CalcResponse(BaseModel):
    mode: Mode
    input_basis: Literal["interest", "payment"]
    payment: str | None
    concession: ConcessionInfo
    contract_annual_rate: str
    contract_annual_rate_percent: str
    contract_period_rate: str
    contract_period_rate_percent: str
    irr_annual_rate: str
    irr_annual_rate_percent: str
    irr_relation: Literal["equal", "higher", "lower"]
    total_years: str
    period_label: str
    formula: str
    note: str
    schedule: list[ScheduleRow]
    schedule_total: ScheduleTotal


class SpecialDeductions(BaseModel):
    child_education: str = "0"
    infant_care: str = "0"
    continuing_education: str = "0"
    mortgage_interest: str = "0"
    housing_rent: str = "0"
    elderly_support: str = "0"


class TaxRequest(BaseModel):
    income: str
    income_basis: Literal["month", "year"] = "month"
    bonus: str = "0"
    bonus_mode: Literal["separate", "combined"] = "separate"
    social: str = "0"
    special: SpecialDeductions = Field(default_factory=SpecialDeductions)
    serious_illness: str = "0"
    pension: str = "0"


class TaxDeductions(BaseModel):
    basic: str
    social: str
    special: str
    annual: str
    total: str


class BonusComparison(BaseModel):
    separate_tax: str
    combined_tax: str
    better: Literal["separate", "combined", "equal"]
    saving: str
    note: str


class TaxScheduleRow(BaseModel):
    month: int
    income: str
    deduction: str
    taxable: str
    tax: str
    cumulative_tax: str


class TaxScheduleTotal(BaseModel):
    tax: str
    income: str
    deduction: str


class TaxResponse(BaseModel):
    income_basis: Literal["month", "year"]
    annual_income: str
    monthly_income: str
    bonus: str
    bonus_mode: Literal["separate", "combined"]
    deductions: TaxDeductions
    taxable_income: str
    comprehensive_tax: str
    bonus_tax: str
    total_tax: str
    net_income: str
    effective_rate_percent: str
    marginal_rate_percent: str
    bonus_comparison: BonusComparison
    schedule: list[TaxScheduleRow]
    schedule_total: TaxScheduleTotal
    formula: str
    note: str


class PensionRequest(BaseModel):
    track: Literal["employee", "resident"] = "employee"
    paid_years: str = "0"
    remaining_years: str = "0"
    retirement_age: str = "60"
    base: str = "10000"
    social: str = "8000"
    growth: str = "3"
    rate: str = "3"
    balance: str = "0"
    years: str = "15"
    contribution: str = "1000"
    subsidy: str = "60"
    base_pension: str = "143"


class PensionScheduleRow(BaseModel):
    year: int
    base: str | None = None
    contribution: str
    subsidy: str | None = None
    balance: str


class PensionScheduleTotal(BaseModel):
    paid: str
    balance: str
    years: str


class PensionResponse(BaseModel):
    track: Literal["employee", "resident"]
    eligible: bool
    years: int
    retirement_age: int
    annuity_months: int
    monthly_total: str
    basic_pension: str
    account_pension: str
    account_balance: str
    social_at_retirement: str | None
    index: str | None
    replacement_rate_percent: str | None
    schedule: list[PensionScheduleRow]
    schedule_total: PensionScheduleTotal
    formula: str
    note: str


app = FastAPI(
    title="计算工具集",
    version="0.3.0",
    docs_url="/api/docs",
    openapi_url="/api/openapi.json",
)


@app.exception_handler(InputError)
def handle_input_error(request: Request, exc: InputError) -> JSONResponse:
    return JSONResponse(
        status_code=400,
        content={"detail": exc.message, "field": exc.field},
    )


@app.exception_handler(RequestValidationError)
def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    return JSONResponse(status_code=422, content={"detail": "请求参数格式不正确"})


@app.post("/api/calculate", response_model=CalcResponse)
def calculate(payload: CalcRequest) -> CalcResponse:
    analysis = analyze(
        principal_raw=payload.principal,
        interest_raw=payload.interest,
        periods_raw=payload.periods,
        period_value_raw=payload.period_value,
        period_unit=payload.period_unit,
        mode=payload.mode,
        payment_raw=payload.payment,
        concession=payload.concession,
        concession_value_raw=payload.concession_value,
    )
    return CalcResponse(**to_response(analysis))


@app.post("/api/tax/calculate", response_model=TaxResponse)
def calculate_tax(payload: TaxRequest) -> TaxResponse:
    result = tax.calculate(
        income_raw=payload.income,
        income_basis=payload.income_basis,
        bonus_raw=payload.bonus,
        bonus_mode=payload.bonus_mode,
        social_raw=payload.social,
        special_raw=payload.special.model_dump(),
        serious_illness_raw=payload.serious_illness,
        pension_raw=payload.pension,
    )
    return TaxResponse(**tax.to_response(result))


@app.post("/api/pension/calculate", response_model=PensionResponse)
def calculate_pension(payload: PensionRequest) -> PensionResponse:
    if payload.track == "employee":
        result = pension.calculate_employee(
            paid_years_raw=payload.paid_years,
            remaining_years_raw=payload.remaining_years,
            retirement_age_raw=payload.retirement_age,
            base_raw=payload.base,
            social_raw=payload.social,
            growth_raw=payload.growth,
            rate_raw=payload.rate,
            balance_raw=payload.balance,
        )
    else:
        result = pension.calculate_resident(
            years_raw=payload.years,
            contribution_raw=payload.contribution,
            subsidy_raw=payload.subsidy,
            rate_raw=payload.rate,
            base_pension_raw=payload.base_pension,
        )
    return PensionResponse(**pension.to_response(result))


@app.get("/api/city-params")
def list_city_params() -> dict[str, object]:
    return {
        "regions": city_params.as_options(),
        "year": city_params.YEAR,
        "note": city_params.NOTE,
    }


@app.get("/api/pension/regions")
def list_pension_regions() -> dict[str, object]:
    return {"regions": pension_regions.as_options(), "note": pension_regions.NOTE}


@app.get("/", response_class=HTMLResponse)
def home(request: Request) -> HTMLResponse:
    return templates.TemplateResponse(
        request,
        "home.html",
        {"groups": tool_registry.home_groups(), "packaged": PACKAGED},
    )


@app.post("/api/shutdown")
def shutdown_app(request: Request) -> dict[str, bool]:
    """Quit the packaged desktop app from the browser (loopback only)."""
    if not PACKAGED:
        raise HTTPException(status_code=404, detail="仅打包版可用")
    if request.headers.get("x-requested-with") != "calculator-toolkit":
        raise HTTPException(status_code=403, detail="forbidden")
    threading.Timer(0.3, _stop_process).start()
    return {"ok": True}


def _stop_process() -> None:
    if os.name == "nt":
        os._exit(0)
    os.kill(os.getpid(), signal.SIGINT)


def _render_tool(slug: str):
    def handler(request: Request) -> HTMLResponse:
        config = tool_registry.page_config(slug)
        if config is None:
            raise HTTPException(status_code=404, detail="工具不存在")
        return templates.TemplateResponse(request, "tool.html", {"tool": config})

    return handler


for _slug in tool_registry.TOOLS:
    app.get(f"/{_slug}/", response_class=HTMLResponse, name=f"tool-{_slug}")(_render_tool(_slug))


@app.post("/api/{slug}/calculate")
def calculate_tool(slug: str, payload: dict[str, str]) -> dict[str, object]:
    handler = tool_registry.HANDLERS.get(slug)
    if handler is None:
        raise HTTPException(status_code=404, detail="工具不存在")
    return handler(payload)


app.mount("/", StaticFiles(directory=STATIC_DIR, html=True), name="static")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("app.main:app", host="127.0.0.1", port=8765)
