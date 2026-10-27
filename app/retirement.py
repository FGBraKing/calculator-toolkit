"""Statutory retirement age under the 2025 gradual delay schedule."""

from __future__ import annotations

from decimal import localcontext

from app import common
from app.calculator import InputError

PRECISION = 50

# 出生年月锚点、每 step 个月出生延迟 1 个月、最多延迟 cap 个月
RULES = {
    "male": {"base": 60, "anchor": (1965, 1), "step": 4, "cap": 36, "label": "男职工"},
    "female55": {
        "base": 55,
        "anchor": (1970, 1),
        "step": 4,
        "cap": 36,
        "label": "女职工（原 55 岁）",
    },
    "female50": {
        "base": 50,
        "anchor": (1975, 1),
        "step": 2,
        "cap": 60,
        "label": "女职工（原 50 岁）",
    },
}


def calculate(payload: dict[str, str]) -> dict[str, object]:
    year = common.integer(payload.get("birth_year"), "birth_year", "出生年份", 1940, 2020)
    month = common.integer(payload.get("birth_month"), "birth_month", "出生月份", 1, 12)
    kind = payload.get("type", "male")
    if kind not in RULES:
        raise InputError("type", "人员类型无效")

    rule = RULES[kind]
    with localcontext() as ctx:
        ctx.prec = PRECISION
        birth_index = year * 12 + month - 1
        anchor_year, anchor_month = rule["anchor"]
        anchor_index = anchor_year * 12 + anchor_month - 1
        delay = (birth_index - anchor_index) // rule["step"] + 1
        delay = max(0, min(rule["cap"], delay))
        base_months = rule["base"] * 12
        retirement_index = birth_index + base_months + delay
        earliest_index = max(retirement_index - 36, birth_index + base_months)
        latest_index = retirement_index + 36
        age_text = _age_text(base_months + delay)
        original_text = _age_text(base_months)

    facts = [
        f"退休时间 {_month_text(retirement_index)}",
        f"弹性区间 {_month_text(earliest_index)} – {_month_text(latest_index)}",
    ]
    if delay == 0:
        facts.append("不受延迟退休影响")
    formula = "\n".join(
        [
            f"人员类型：{rule['label']}，出生 {year} 年 {month} 月",
            f"原法定退休年龄 {original_text}；按出生年月对应延迟 {delay} 个月",
            f"法定退休年龄 = {original_text} + {delay} 个月 = {age_text}",
            f"退休时间 = 出生年月 + 法定退休年龄 = {_month_text(retirement_index)}",
            "弹性提前不超过 3 年且不低于原法定年龄；弹性延迟不超过 3 年，需本人自愿并与单位协商",
        ]
    )
    return common.response(
        primary=age_text,
        primary_unit="",
        facts=facts,
        metrics=[
            ("原法定退休年龄", original_text),
            ("延迟月数", f"{delay} 个月"),
            ("退休年龄", age_text),
        ],
        formula=formula,
        note="依据 2024 年 9 月《关于实施渐进式延迟法定退休年龄的决定》，"
        "自 2025 年 1 月 1 日起施行：男职工每 4 个月延迟 1 个月至 63 岁，"
        "原 55 岁女职工每 4 个月延迟 1 个月至 58 岁，"
        "原 50 岁女职工每 2 个月延迟 1 个月至 55 岁。"
        "特殊工种提前退休、病退等另有规定，未计入。",
    )


def _age_text(total_months: int) -> str:
    years, months = divmod(total_months, 12)
    return f"{years} 岁" if months == 0 else f"{years} 岁 {months} 个月"


def _month_text(index: int) -> str:
    return f"{index // 12} 年 {index % 12 + 1} 月"
