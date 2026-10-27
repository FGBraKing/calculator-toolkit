"""Childcare subsidy (国家育儿补贴) entitlement through the third birthday."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, localcontext

from app import common

PRECISION = 50
PROGRAM_START = (2025, 1)
MAX_MONTHS = 36


def calculate(payload: dict[str, str], *, as_of: date | None = None) -> dict[str, object]:
    year = common.integer(
        payload.get("birth_year"), "birth_year", "出生年份", 2019, date.today().year + 1
    )
    month = common.integer(payload.get("birth_month"), "birth_month", "出生月份", 1, 12)
    standard = common.amount(
        payload.get("standard"),
        "standard",
        "当地年标准",
        allow_zero=False,
        maximum=Decimal("100000"),
    )
    today = as_of or date.today()

    with localcontext() as ctx:
        ctx.prec = PRECISION
        birth_index = year * 12 + month - 1
        start_index = max(birth_index, PROGRAM_START[0] * 12 + PROGRAM_START[1] - 1)
        end_index = birth_index + MAX_MONTHS - 1
        months = max(0, end_index - start_index + 1)
        monthly = standard / 12
        total = monthly * months
        now_index = today.year * 12 + today.month - 1
        remaining = (
            max(0, end_index - max(start_index, now_index) + 1) if now_index <= end_index else 0
        )
        received = months - remaining

    if months == 0:
        facts = ["已超过 3 周岁，不再符合补贴条件"]
        metrics = [
            ("可领月数", "0 个月"),
            ("每月标准", f"{common.money(monthly)} 元"),
            ("合计", "0.00 元"),
        ]
        formula = "婴幼儿已满 3 周岁，且在 2025 年 1 月 1 日政策实施时已超过 3 周岁，不产生补贴。"
    else:
        facts = [
            f"可领月份 {_month_text(start_index)} – {_month_text(end_index)}",
            f"剩余 {remaining} 个月（{common.money(monthly * remaining)} 元）",
        ]
        metrics = [
            ("可领月数", f"{months} 个月"),
            ("每月标准", f"{common.money(monthly)} 元"),
            ("合计", f"{common.money(total)} 元"),
        ]
        formula = "\n".join(
            [
                "育儿补贴 = 年标准 ÷ 12 × 可领月数",
                f"  = {common.money(standard)} ÷ 12 × {months} = {common.money(total)}",
                f"可领月份 = max(出生月, 2025 年 1 月) 至 满 3 周岁前 1 个月 = {months} 个月",
                f"截至 {today.year}-{today.month:02d}：已领 {received} 个月，剩余 {remaining} 个月",
            ]
        )

    return common.response(
        primary=common.money(total),
        facts=facts,
        metrics=metrics,
        formula=formula,
        note="依据 2025 年《育儿补贴制度实施方案》：自 2025 年 1 月 1 日起，对 3 周岁以下婴幼儿"
        "按每孩每年 3,600 元的国家基础标准发放，地方可在此基础上提高；2025 年 1 月 1 日前出生"
        "且未满 3 周岁的按应补贴月数折算。多孩按每名婴幼儿分别计算后相加。"
        "本工具按月折算估算，实际发放频次以当地规定为准。",
    )


def _month_text(index: int) -> str:
    return f"{index // 12} 年 {index % 12 + 1} 月"
