"""Shared parsing, formatting, and response helpers for the small calculators."""

from __future__ import annotations

import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from app.calculator import InputError

MAX_AMOUNT = Decimal("1000000000000")
MAX_RAW_LENGTH = 40

_MONEY_QUANTUM = Decimal("0.01")
_PERCENT_QUANTUM = Decimal("0.0001")


def money(value: Decimal) -> str:
    return f"{value.quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP):,.2f}"


def percent(value: Decimal) -> str:
    return f"{(value * 100).quantize(_PERCENT_QUANTUM, rounding=ROUND_HALF_UP):,.4f}"


def percent_plain(value: Decimal) -> str:
    text = percent(value)
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def decimal_plain(value: Decimal) -> str:
    text = f"{value.quantize(Decimal('0.0001'), rounding=ROUND_HALF_UP):f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def amount(
    raw: str | None,
    field: str,
    label: str,
    *,
    allow_zero: bool = True,
    maximum: Decimal = MAX_AMOUNT,
) -> Decimal:
    value = _decimal(raw, field, label)
    if value < 0:
        raise InputError(field, f"{label}不能为负")
    if value == 0 and not allow_zero:
        raise InputError(field, f"{label}必须大于 0")
    if value > maximum:
        raise InputError(field, f"{label}超出可计算范围")
    return value


def integer(
    raw: str | None,
    field: str,
    label: str,
    minimum: int,
    maximum: int,
) -> int:
    if raw is None:
        raise InputError(field, f"请输入{label}")
    if not isinstance(raw, str) or len(raw) > MAX_RAW_LENGTH:
        raise InputError(field, f"{label}必须为整数")
    text = _clean(raw)
    if not text:
        raise InputError(field, f"请输入{label}")
    if re.fullmatch(r"[0-9]+", text) is None:
        raise InputError(field, f"{label}必须为整数")
    value = int(text)
    if not minimum <= value <= maximum:
        raise InputError(field, f"{label}需在 {minimum}–{maximum} 之间")
    return value


def rate(
    raw: str | None,
    field: str,
    label: str,
    *,
    maximum: Decimal = Decimal("100"),
) -> Decimal:
    """Parse a percentage input such as "3.1" into the fraction 0.031."""
    value = _decimal(raw, field, label, allow_fraction=True)
    if value < 0:
        raise InputError(field, f"{label}不能为负")
    if value > maximum:
        raise InputError(field, f"{label}需在 0–{percent_plain(maximum / 100)}% 之间")
    return value / 100


def day(raw: str | None, field: str, label: str) -> date:
    if raw is None:
        raise InputError(field, f"请选择{label}")
    if not isinstance(raw, str) or len(raw) > MAX_RAW_LENGTH:
        raise InputError(field, f"{label}格式不正确")
    text = _clean(raw)
    if not text:
        raise InputError(field, f"请选择{label}")
    try:
        return date.fromisoformat(text)
    except ValueError as exc:
        raise InputError(field, f"{label}格式不正确") from exc


def response(
    *,
    primary: str,
    facts: list[str],
    metrics: list[tuple[str, str]],
    formula: str,
    note: str,
    schedule: dict[str, object] | None = None,
    primary_unit: str | None = None,
) -> dict[str, object]:
    return {
        "primary": primary,
        "primary_unit": primary_unit,
        "facts": facts,
        "metrics": [{"label": label, "value": value} for label, value in metrics],
        "schedule": schedule,
        "formula": formula,
        "note": note,
    }


def table(
    *,
    columns: list[str],
    rows: list[list[str]],
    totals: list[tuple[str, str]],
    note: str,
    meta: str,
) -> dict[str, object]:
    return {
        "columns": columns,
        "rows": rows,
        "totals": [{"label": label, "value": value} for label, value in totals],
        "note": note,
        "meta": meta,
    }


def _clean(raw: str) -> str:
    return re.sub(r"[\s,，]", "", raw)


def _decimal(
    raw: str | None,
    field: str,
    label: str,
    *,
    allow_fraction: bool = False,
) -> Decimal:
    if raw is None:
        raise InputError(field, f"请输入{label}")
    if not isinstance(raw, str) or len(raw) > MAX_RAW_LENGTH:
        raise InputError(field, f"{label}格式不正确")
    text = _clean(raw)
    if not text:
        raise InputError(field, f"请输入{label}")

    if "/" in text:
        if not allow_fraction:
            raise InputError(field, f"{label}格式不正确")
        parts = text.split("/")
        if len(parts) != 2 or not all(parts):
            raise InputError(field, f"{label}格式不正确")
        try:
            numerator = Decimal(parts[0])
            denominator = Decimal(parts[1])
        except InvalidOperation as exc:
            raise InputError(field, f"{label}格式不正确") from exc
        if not numerator.is_finite() or not denominator.is_finite() or denominator == 0:
            raise InputError(field, f"{label}格式不正确")
        return numerator / denominator

    try:
        value = Decimal(text)
    except InvalidOperation as exc:
        raise InputError(field, f"{label}格式不正确") from exc
    if not value.is_finite():
        raise InputError(field, f"{label}格式不正确")
    return value
