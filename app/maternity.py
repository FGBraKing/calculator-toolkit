"""Maternity leave days and dates under national rules plus local reward leave."""

from __future__ import annotations

from datetime import timedelta

from app import common
from app.calculator import InputError

BASE_DAYS = 98
PRENATAL_DAYS = 15
DIFFICULT_DAYS = 15
PER_EXTRA_CHILD_DAYS = 15
KINDS = ("normal", "difficult")


def calculate(payload: dict[str, str]) -> dict[str, object]:
    due = common.day(payload.get("due"), "due", "预产期")
    kind = payload.get("type", "normal")
    if kind not in KINDS:
        raise InputError("type", "生育类型无效")
    children = common.integer(payload.get("children"), "children", "胎儿数", 1, 4)
    reward = common.integer(payload.get("reward"), "reward", "地方奖励假", 0, 120)

    extra = (DIFFICULT_DAYS if kind == "difficult" else 0) + PER_EXTRA_CHILD_DAYS * (children - 1)
    national = BASE_DAYS + extra
    total = national + reward
    start = due - timedelta(days=PRENATAL_DAYS)
    end = start + timedelta(days=total - 1)

    facts = [
        f"产假 {start.isoformat()} 至 {end.isoformat()}",
        f"含产前 {PRENATAL_DAYS} 天（可依本人意愿与单位协商调整）",
    ]
    if extra:
        parts = []
        if kind == "difficult":
            parts.append(f"难产 +{DIFFICULT_DAYS} 天")
        if children > 1:
            parts.append(f"多胞胎 {children} 个 +{PER_EXTRA_CHILD_DAYS * (children - 1)} 天")
        facts.append("，".join(parts))
    if reward:
        facts.append(f"地方奖励假 {reward} 天")

    formula_lines = [
        f"国家规定产假 = {BASE_DAYS} 天",
    ]
    if kind == "difficult":
        formula_lines.append(f"难产 +{DIFFICULT_DAYS} 天")
    if children > 1:
        formula_lines.append(
            f"多胞胎（{children} 个）每多 1 个 +{PER_EXTRA_CHILD_DAYS} 天"
            f" → 共 +{PER_EXTRA_CHILD_DAYS * (children - 1)} 天"
        )
    formula_lines.append(f"地方奖励假 +{reward} 天")
    formula_lines.append(f"合计 = {total} 天")
    formula_lines.append(f"产假起点 = 预产期前 {PRENATAL_DAYS} 天 = {start.isoformat()}")
    formula_lines.append(f"产假终点 = 起点 + {total} 天 − 1 天 = {end.isoformat()}")

    return common.response(
        primary=str(total),
        primary_unit="天",
        facts=facts,
        metrics=[
            ("国家规定", f"{national} 天"),
            ("地方奖励", f"{reward} 天"),
            ("合计", f"{total} 天"),
        ],
        formula="\n".join(formula_lines),
        note="98 天为《女职工劳动保护特别规定》的基础产假；难产增加 15 天，"
        "多胞胎每多生育 1 个婴儿增加 15 天；奖励假天数由各省人口与计划生育条例规定"
        "（常见 30–90 天），请按所在省份填写。"
        "生育津贴与产假工资另按规定计发。",
    )
