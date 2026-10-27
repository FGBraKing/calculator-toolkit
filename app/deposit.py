"""Deposit interest for simple interest and annual compounding."""

from __future__ import annotations

from decimal import Decimal, localcontext

from app import common
from app.calculator import InputError

UNITS = {"year": Decimal(1), "month": Decimal(12), "day": Decimal(365)}
METHODS = ("simple", "compound")
PRECISION = 50


def calculate(payload: dict[str, str]) -> dict[str, object]:
    principal = common.amount(
        payload.get("principal"), "principal", "本金", allow_zero=False, maximum=Decimal("1e12")
    )
    annual_rate = common.rate(payload.get("rate"), "rate", "年利率", maximum=Decimal("30"))
    term = common.amount(
        payload.get("term"), "term", "存期", allow_zero=False, maximum=Decimal("36500")
    )
    unit = payload.get("unit", "year")
    if unit not in UNITS:
        raise InputError("unit", "存期单位无效")
    method = payload.get("method", "simple")
    if method not in METHODS:
        raise InputError("method", "计息方式无效")

    with localcontext() as ctx:
        ctx.prec = PRECISION
        years = term / UNITS[unit]
        if years > 100:
            raise InputError("term", "存期折合不能超过 100 年")
        if method == "simple":
            interest = principal * annual_rate * years
        else:
            interest = principal * ((1 + annual_rate) ** years - 1)
        total = principal + interest

    years_text = _years_text(years)
    method_text = "单利（到期一次还本付息）" if method == "simple" else "按年复利"
    if method == "simple":
        formula = "\n".join(
            [
                "利息 = 本金 × 年利率 × 存期",
                f"  = {common.money(principal)} × {common.percent_plain(annual_rate)}%"
                f" × {years_text} = {common.money(interest)}",
                f"本息合计 = {common.money(principal)} + {common.money(interest)}"
                f" = {common.money(total)}",
            ]
        )
    else:
        formula = "\n".join(
            [
                "本息合计 = 本金 × (1 + 年利率)^存期",
                f"  = {common.money(principal)} × (1 + {common.percent_plain(annual_rate)}%)"
                f"^{years_text} = {common.money(total)}",
                f"利息 = {common.money(total)} − {common.money(principal)}"
                f" = {common.money(interest)}",
            ]
        )

    return common.response(
        primary=common.money(interest),
        facts=[f"存期 {years_text} 年", method_text],
        metrics=[
            ("本金", f"{common.money(principal)} 元"),
            ("利息", f"{common.money(interest)} 元"),
            ("本息合计", f"{common.money(total)} 元"),
        ],
        formula=formula,
        note="银行定期存款一般按单利计息，到期自动转存可视为按年复利；"
        "储蓄存款利息自 2008 年 10 月 9 日起暂免征收利息税。",
    )


def _years_text(value: Decimal) -> str:
    text = f"{value.quantize(Decimal('0.000001')):f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text
