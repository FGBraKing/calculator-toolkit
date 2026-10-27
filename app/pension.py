"""Basic pension estimates for the two-track system.

Employee (城镇职工) rules encoded:

* 基础养老金 = 退休时上年度社平工资 × (1 + 平均缴费指数) ÷ 2 × 缴费年限 × 1%
* 个人账户养老金 = 个人账户储存额 ÷ 计发月数（按退休年龄查表）
* 缴费基数须在社平工资的 60%–300% 之间；累计缴费满 15 年方可按月领取

Resident (城乡居民) rules encoded:

* 月养老金 = 当地基础养老金 + 个人账户储存额 ÷ 139
* 个人账户 = 个人缴费 + 政府补贴 + 利息；累计缴费满 15 年方可领取

Provinces differ, so 社平工资、基础养老金标准、缴费补贴、记账利率 are inputs.
过渡性养老金、职业年金与视同缴费年限未建模。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext

from app.calculator import InputError

MAX_AMOUNT = Decimal("1000000000000")
MAX_RAW_LENGTH = 40
MAX_YEARS = 50
PRECISION = 50

MIN_YEARS = 15
ACCOUNT_CONTRIBUTION_RATE = Decimal("0.08")
BASE_FLOOR = Decimal("0.6")
BASE_CAP = Decimal("3")
MAX_RATE_PERCENT = Decimal("20")
RESIDENT_ANNUITY_MONTHS = 139

TRACKS = ("employee", "resident")

# 个人账户养老金计发月数表（按退休年龄）
ANNUITY_MONTHS = {
    40: 233,
    41: 230,
    42: 226,
    43: 223,
    44: 220,
    45: 216,
    46: 212,
    47: 208,
    48: 204,
    49: 199,
    50: 195,
    51: 190,
    52: 185,
    53: 180,
    54: 175,
    55: 170,
    56: 164,
    57: 158,
    58: 152,
    59: 145,
    60: 139,
    61: 132,
    62: 125,
    63: 117,
    64: 109,
    65: 101,
    66: 93,
    67: 84,
    68: 75,
    69: 65,
    70: 56,
}

_MONEY_QUANTUM = Decimal("0.01")
_PERCENT_QUANTUM = Decimal("0.0001")
_RATIO_QUANTUM = Decimal("0.0001")


@dataclass(frozen=True, slots=True)
class EmployeeYear:
    year: int
    base: Decimal
    contribution: Decimal
    balance: Decimal


@dataclass(frozen=True, slots=True)
class ResidentYear:
    year: int
    contribution: Decimal
    subsidy: Decimal
    balance: Decimal


@dataclass(frozen=True, slots=True)
class PensionResult:
    track: str
    years: int
    eligible: bool
    retirement_age: int
    annuity_months: int
    basic_pension: Decimal
    account_pension: Decimal
    monthly_total: Decimal
    account_balance: Decimal
    social_at_retirement: Decimal | None = None
    index: Decimal | None = None
    replacement_rate: Decimal | None = None
    employee_rows: tuple[EmployeeYear, ...] = ()
    resident_rows: tuple[ResidentYear, ...] = ()


def calculate_employee(
    paid_years_raw: str,
    remaining_years_raw: str,
    retirement_age_raw: str,
    base_raw: str,
    social_raw: str,
    growth_raw: str,
    rate_raw: str,
    balance_raw: str,
) -> PensionResult:
    paid_years = _parse_years(paid_years_raw, "paid_years", "已缴费年限", allow_zero=True)
    remaining = _parse_years(remaining_years_raw, "remaining_years", "距退休年数", allow_zero=True)
    retirement_age = _parse_age(retirement_age_raw)
    base = _parse_amount(base_raw, "base", "月缴费基数", allow_zero=False)
    social = _parse_amount(social_raw, "social", "社平工资", allow_zero=False)
    growth = _parse_rate(growth_raw, "growth", "社平工资增长率")
    rate = _parse_rate(rate_raw, "rate", "记账利率")
    current = _parse_amount(balance_raw, "balance", "个人账户余额")

    with localcontext() as ctx:
        ctx.prec = PRECISION
        index = base / social
        if index < BASE_FLOOR or index > BASE_CAP:
            raise InputError("base", "缴费基数应在社平工资的 60%–300% 之间")

        years = paid_years + remaining
        social_retirement = social * (1 + growth) ** remaining
        balance = current
        base_year = base
        rows: list[EmployeeYear] = []
        for year in range(1, remaining + 1):
            contribution = base_year * ACCOUNT_CONTRIBUTION_RATE * 12
            balance = balance * (1 + rate) + contribution
            rows.append(
                EmployeeYear(
                    year=year,
                    base=base_year,
                    contribution=contribution,
                    balance=balance,
                )
            )
            base_year *= 1 + growth

        basic_pension = social_retirement * (1 + index) / 2 * years / 100
        account_pension = balance / ANNUITY_MONTHS[retirement_age]
        monthly_total = basic_pension + account_pension
        wage_at_retirement = social_retirement * index
        replacement = monthly_total / wage_at_retirement if wage_at_retirement > 0 else None

    return PensionResult(
        track="employee",
        years=years,
        eligible=years >= MIN_YEARS,
        retirement_age=retirement_age,
        annuity_months=ANNUITY_MONTHS[retirement_age],
        basic_pension=basic_pension,
        account_pension=account_pension,
        monthly_total=monthly_total,
        account_balance=balance,
        social_at_retirement=social_retirement,
        index=index,
        replacement_rate=replacement,
        employee_rows=tuple(rows),
    )


def calculate_resident(
    years_raw: str,
    contribution_raw: str,
    subsidy_raw: str,
    rate_raw: str,
    base_pension_raw: str,
) -> PensionResult:
    years = _parse_years(years_raw, "years", "缴费年限", allow_zero=False)
    contribution = _parse_amount(contribution_raw, "contribution", "每年个人缴费")
    subsidy = _parse_amount(subsidy_raw, "subsidy", "每年政府补贴")
    rate = _parse_rate(rate_raw, "rate", "记账利率")
    base_pension = _parse_amount(base_pension_raw, "base_pension", "当地基础养老金")

    with localcontext() as ctx:
        ctx.prec = PRECISION
        balance = Decimal(0)
        rows: list[ResidentYear] = []
        for year in range(1, years + 1):
            balance = balance * (1 + rate) + contribution + subsidy
            rows.append(
                ResidentYear(
                    year=year,
                    contribution=contribution,
                    subsidy=subsidy,
                    balance=balance,
                )
            )

        account_pension = balance / RESIDENT_ANNUITY_MONTHS
        monthly_total = base_pension + account_pension

    return PensionResult(
        track="resident",
        years=years,
        eligible=years >= MIN_YEARS,
        retirement_age=60,
        annuity_months=RESIDENT_ANNUITY_MONTHS,
        basic_pension=base_pension,
        account_pension=account_pension,
        monthly_total=monthly_total,
        account_balance=balance,
        resident_rows=tuple(rows),
    )


def to_response(result: PensionResult) -> dict[str, object]:
    with localcontext() as ctx:
        ctx.prec = PRECISION
        return {
            "track": result.track,
            "eligible": result.eligible,
            "years": result.years,
            "retirement_age": result.retirement_age,
            "annuity_months": result.annuity_months,
            "monthly_total": _money(result.monthly_total),
            "basic_pension": _money(result.basic_pension),
            "account_pension": _money(result.account_pension),
            "account_balance": _money(result.account_balance),
            "social_at_retirement": (
                _money(result.social_at_retirement)
                if result.social_at_retirement is not None
                else None
            ),
            "index": _ratio(result.index) if result.index is not None else None,
            "replacement_rate_percent": (
                _format_percent(result.replacement_rate)
                if result.replacement_rate is not None
                else None
            ),
            "schedule": _schedule(result),
            "schedule_total": _schedule_total(result),
            "formula": _formula(result),
            "note": _note(result),
        }


def _schedule_total(result: PensionResult) -> dict[str, object]:
    if result.track == "employee":
        paid = sum((row.contribution for row in result.employee_rows), Decimal(0))
    else:
        paid = sum(
            (row.contribution + row.subsidy for row in result.resident_rows),
            Decimal(0),
        )
    return {
        "paid": _money(paid),
        "balance": _money(result.account_balance),
        "years": str(
            len(result.employee_rows) if result.track == "employee" else len(result.resident_rows)
        ),
    }


def _schedule(result: PensionResult) -> list[dict[str, object]]:
    if result.track == "employee":
        return [
            {
                "year": row.year,
                "base": _money(row.base),
                "contribution": _money(row.contribution),
                "balance": _money(row.balance),
            }
            for row in result.employee_rows
        ]
    return [
        {
            "year": row.year,
            "contribution": _money(row.contribution),
            "subsidy": _money(row.subsidy),
            "balance": _money(row.balance),
        }
        for row in result.resident_rows
    ]


def _formula(result: PensionResult) -> str:
    if result.track == "employee":
        index = result.index or Decimal(0)
        social = result.social_at_retirement or Decimal(0)
        lines = [
            "基础养老金 = 退休时计发基数 × (1 + 平均缴费指数) ÷ 2 × 缴费年限 × 1%",
            f"  = {_money(social)} × (1 + {_ratio(index)})"
            f" ÷ 2 × {result.years} × 1% = {_money(result.basic_pension)}",
            f"个人账户养老金 = 储存额 ÷ 计发月数"
            f" = {_money(result.account_balance)} ÷ {result.annuity_months}"
            f" = {_money(result.account_pension)}",
            f"月养老金 = {_money(result.basic_pension)} + {_money(result.account_pension)}"
            f" = {_money(result.monthly_total)}",
        ]
        wage = social * index
        if wage > 0 and result.replacement_rate is not None:
            lines.append(
                f"退休时本人缴费工资 = {_money(wage)}"
                f"，替代率 {_format_percent(result.replacement_rate)}%"
            )
        return "\n".join(lines)

    first = result.resident_rows[0] if result.resident_rows else None
    contribution = first.contribution if first else Decimal(0)
    subsidy = first.subsidy if first else Decimal(0)
    return "\n".join(
        [
            f"个人账户储存额 = 每年（缴费 {_money(contribution)} + 补贴 {_money(subsidy)}）"
            f"按记账利率滚存 {result.years} 年 = {_money(result.account_balance)}",
            f"个人账户养老金 = {_money(result.account_balance)} ÷ {result.annuity_months}"
            f" = {_money(result.account_pension)}",
            f"月养老金 = 当地基础养老金 {_money(result.basic_pension)}"
            f" + {_money(result.account_pension)} = {_money(result.monthly_total)}",
        ]
    )


def _note(result: PensionResult) -> str:
    if result.track == "employee":
        parts = [
            "按城镇职工基本养老保险口径估算：基础养老金与个人账户养老金合计，"
            "个人账户按 8% 划入并计息（当年划入不计当年利息）。",
            "过渡性养老金、职业年金与视同缴费年限未计入；退休年龄按你填写的法定退休年龄，"
            "2025 年起实施渐进式延迟退休。",
        ]
    else:
        parts = [
            "按城乡居民基本养老保险口径估算：个人账户 = 个人缴费 + 政府补贴 + 利息，"
            "60 岁起按月领取，计发月数 139。",
            "基础养老金为地方标准（全国最低标准 2025 年为 143 元/月），"
            "缴费补贴与记账利率由各省确定。",
        ]
    if not result.eligible:
        parts.append(
            f"累计缴费 {result.years} 年，不足 {MIN_YEARS} 年，暂不能按月领取基本养老金，"
            "可延长缴费或按规定补缴。"
        )
    return "".join(parts)


def _parse_years(raw: str | None, field: str, label: str, *, allow_zero: bool) -> int:
    if raw is None:
        raise InputError(field, f"请输入{label}")
    if not isinstance(raw, str) or len(raw) > MAX_RAW_LENGTH:
        raise InputError(field, f"{label}必须为整数")
    text = re.sub(r"[\s,，]", "", raw)
    if not text:
        raise InputError(field, f"请输入{label}")
    if re.fullmatch(r"[0-9]+", text) is None:
        raise InputError(field, f"{label}必须为非负整数")
    value = int(text)
    if value == 0 and not allow_zero:
        raise InputError(field, f"{label}必须大于 0")
    if value > MAX_YEARS:
        raise InputError(field, f"{label}需在 0–{MAX_YEARS} 之间")
    return value


def _parse_age(raw: str | None) -> int:
    if raw is None:
        raise InputError("retirement_age", "请输入退休年龄")
    if not isinstance(raw, str) or len(raw) > MAX_RAW_LENGTH:
        raise InputError("retirement_age", "退休年龄必须为整数")
    text = re.sub(r"[\s,，]", "", raw)
    if not text:
        raise InputError("retirement_age", "请输入退休年龄")
    if re.fullmatch(r"[0-9]+", text) is None:
        raise InputError("retirement_age", "退休年龄必须为整数")
    age = int(text)
    if age not in ANNUITY_MONTHS:
        low, high = min(ANNUITY_MONTHS), max(ANNUITY_MONTHS)
        raise InputError("retirement_age", f"退休年龄需在 {low}–{high} 岁之间")
    return age


def _parse_rate(raw: str | None, field: str, label: str) -> Decimal:
    if raw is None:
        raise InputError(field, f"请输入{label}")
    if not isinstance(raw, str) or len(raw) > MAX_RAW_LENGTH:
        raise InputError(field, f"{label}格式不正确")
    text = re.sub(r"[\s,，]", "", raw)
    if not text:
        raise InputError(field, f"请输入{label}")
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise InputError(field, f"{label}格式不正确") from exc
    if not value.is_finite() or value < 0:
        raise InputError(field, f"{label}不能为负")
    if value > MAX_RATE_PERCENT:
        raise InputError(field, f"{label}需在 0–{MAX_RATE_PERCENT}% 之间")
    return value / 100


def _parse_amount(raw: str | None, field: str, label: str, *, allow_zero: bool = True) -> Decimal:
    if raw is None:
        raise InputError(field, f"请输入{label}")
    if not isinstance(raw, str) or len(raw) > MAX_RAW_LENGTH:
        raise InputError(field, f"{label}格式不正确")
    text = re.sub(r"[\s,，]", "", raw)
    if not text:
        raise InputError(field, f"请输入{label}")
    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise InputError(field, f"{label}格式不正确") from exc
    if not value.is_finite():
        raise InputError(field, f"{label}格式不正确")
    if value < 0:
        raise InputError(field, f"{label}不能为负")
    if value == 0 and not allow_zero:
        raise InputError(field, f"{label}必须大于 0")
    if value > MAX_AMOUNT:
        raise InputError(field, f"{label}超出可计算范围")
    return value


def _round_money(value: Decimal) -> Decimal:
    return value.quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _money(value: Decimal) -> str:
    return f"{_round_money(value):,.2f}"


def _format_percent(value: Decimal) -> str:
    return f"{(value * 100).quantize(_PERCENT_QUANTUM, rounding=ROUND_HALF_UP):,.4f}"


def _ratio(value: Decimal) -> str:
    text = f"{value.quantize(_RATIO_QUANTUM, rounding=ROUND_HALF_UP):f}"
    return text.rstrip("0").rstrip(".") if "." in text else text
