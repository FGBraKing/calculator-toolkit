"""Resident individual income tax for salary income and annual bonus.

Rules encoded for the current 综合所得 regime:

* 年度基本减除费用 60,000 元（5,000 元/月）。
* 六项按月享受的专项附加扣除；住房贷款利息与住房租金不得同时享受。
* 大病医疗：医保目录内个人自付超过 15,000 元的部分，限额 80,000 元（汇算时扣除）。
* 个人养老金：每年限额 12,000 元（汇算时扣除）。
* 综合所得 3%–45% 七级超额累进；全年一次性奖金单独计税时按奖金 ÷ 12 查月度税率表。
* 月度预扣采用累计预扣法。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext

from app.calculator import InputError

MAX_AMOUNT = Decimal("1000000000000")
MAX_RAW_LENGTH = 40
PRECISION = 50

BASIC_DEDUCTION_MONTHLY = Decimal("5000")
SERIOUS_ILLNESS_THRESHOLD = Decimal("15000")
SERIOUS_ILLNESS_CAP = Decimal("80000")
PENSION_CAP = Decimal("12000")

INCOME_BASES = ("month", "year")
BONUS_MODES = ("separate", "combined")

# key, label, 每月上限（None：按子女数或分摊比例据实填写，不设硬上限）
SPECIAL_ITEMS = (
    ("child_education", "子女教育", None),
    ("infant_care", "3 岁以下婴幼儿照护", None),
    ("continuing_education", "继续教育", Decimal("400")),
    ("mortgage_interest", "住房贷款利息", Decimal("1000")),
    ("housing_rent", "住房租金", Decimal("1500")),
    ("elderly_support", "赡养老人", Decimal("3000")),
)

# 综合所得年度税率表：(上限, 税率, 速算扣除数)
BRACKETS = (
    (Decimal("36000"), Decimal("0.03"), Decimal("0")),
    (Decimal("144000"), Decimal("0.10"), Decimal("2520")),
    (Decimal("300000"), Decimal("0.20"), Decimal("16920")),
    (Decimal("420000"), Decimal("0.25"), Decimal("31920")),
    (Decimal("660000"), Decimal("0.30"), Decimal("52920")),
    (Decimal("960000"), Decimal("0.35"), Decimal("85920")),
    (None, Decimal("0.45"), Decimal("181920")),
)
# 奖金单独计税的月度税率表 = 年度表 ÷ 12
MONTHLY_BRACKETS = tuple(
    (None if limit is None else limit / 12, rate, quick / 12) for limit, rate, quick in BRACKETS
)

_MONEY_QUANTUM = Decimal("0.01")
_PERCENT_QUANTUM = Decimal("0.0001")


@dataclass(frozen=True, slots=True)
class MonthlyRow:
    month: int
    cumulative_income: Decimal
    cumulative_deduction: Decimal
    cumulative_taxable: Decimal
    tax: Decimal
    cumulative_tax: Decimal


@dataclass(frozen=True, slots=True)
class TaxResult:
    income_basis: str
    annual_income: Decimal
    monthly_income: Decimal
    bonus: Decimal
    bonus_mode: str
    social_monthly: Decimal
    social_annual: Decimal
    special_monthly: Decimal
    special_annual: Decimal
    special_values: tuple[tuple[str, Decimal], ...]
    serious_illness_paid: Decimal
    serious_illness_deductible: Decimal
    pension: Decimal
    pension_deductible: Decimal
    basic_deduction: Decimal
    annual_extra_deduction: Decimal
    deductions_total: Decimal
    taxable_income: Decimal
    comprehensive_tax: Decimal
    bonus_separate_tax: Decimal
    bonus_tax: Decimal
    total_tax: Decimal
    net_income: Decimal
    effective_rate: Decimal
    marginal_rate: Decimal
    combined_taxable: Decimal
    combined_total: Decimal
    schedule: tuple[MonthlyRow, ...]


def calculate(
    income_raw: str,
    income_basis: str,
    bonus_raw: str,
    bonus_mode: str,
    social_raw: str,
    special_raw: dict[str, str],
    serious_illness_raw: str,
    pension_raw: str,
) -> TaxResult:
    if income_basis not in INCOME_BASES:
        raise InputError("income_basis", "收入口径无效")
    if bonus_mode not in BONUS_MODES:
        raise InputError("bonus_mode", "年终奖计税方式无效")

    with localcontext() as ctx:
        ctx.prec = PRECISION
        income = _parse_amount(income_raw, "income", "收入")
        bonus = _parse_amount(bonus_raw, "bonus", "年终奖")
        social = _parse_amount(social_raw, "social", "三险一金")

        special_values: dict[str, Decimal] = {}
        special_monthly = Decimal(0)
        for key, label, cap in SPECIAL_ITEMS:
            value = _parse_amount(special_raw.get(key), key, label)
            if cap is not None and value > cap:
                raise InputError(key, f"{label}每月最多 {_money(cap)} 元")
            special_values[key] = value
            special_monthly += value

        if special_values["mortgage_interest"] > 0 and special_values["housing_rent"] > 0:
            raise InputError("housing_rent", "住房贷款利息与住房租金不能同时享受")

        illness_paid = _parse_amount(serious_illness_raw, "serious_illness", "大病医疗自付")
        pension = _parse_amount(pension_raw, "pension", "个人养老金")

        annual_income = income * 12 if income_basis == "month" else income
        monthly_income = annual_income / 12
        social_annual = social * 12
        if social_annual > annual_income:
            raise InputError("social", "三险一金合计不能超过年收入")

        special_annual = special_monthly * 12
        basic_deduction = BASIC_DEDUCTION_MONTHLY * 12
        illness_deductible = min(
            max(illness_paid - SERIOUS_ILLNESS_THRESHOLD, Decimal(0)),
            SERIOUS_ILLNESS_CAP,
        )
        pension_deductible = min(pension, PENSION_CAP)
        annual_extra = illness_deductible + pension_deductible

        deductions_total = basic_deduction + social_annual + special_annual + annual_extra
        taxable = max(annual_income - deductions_total, Decimal(0))
        comprehensive_tax = _tax(taxable, BRACKETS)
        bonus_separate_tax = _bonus_tax(bonus)
        combined_taxable = max(annual_income + bonus - deductions_total, Decimal(0))
        combined_total = _tax(combined_taxable, BRACKETS)

        if bonus_mode == "separate":
            bonus_tax = bonus_separate_tax
            total_tax = comprehensive_tax + bonus_separate_tax
            marginal_rate = _bracket_rate(taxable, BRACKETS)
        else:
            bonus_tax = combined_total - comprehensive_tax
            total_tax = combined_total
            marginal_rate = _bracket_rate(combined_taxable, BRACKETS)

        gross = annual_income + bonus
        net_income = gross - social_annual - total_tax
        effective_rate = total_tax / gross if gross > 0 else Decimal(0)
        schedule = _withholding_schedule(monthly_income, social, special_monthly)

    return TaxResult(
        income_basis=income_basis,
        annual_income=annual_income,
        monthly_income=monthly_income,
        bonus=bonus,
        bonus_mode=bonus_mode,
        social_monthly=social,
        social_annual=social_annual,
        special_monthly=special_monthly,
        special_annual=special_annual,
        special_values=tuple(special_values.items()),
        serious_illness_paid=illness_paid,
        serious_illness_deductible=illness_deductible,
        pension=pension,
        pension_deductible=pension_deductible,
        basic_deduction=basic_deduction,
        annual_extra_deduction=annual_extra,
        deductions_total=deductions_total,
        taxable_income=taxable,
        comprehensive_tax=comprehensive_tax,
        bonus_separate_tax=bonus_separate_tax,
        bonus_tax=bonus_tax,
        total_tax=total_tax,
        net_income=net_income,
        effective_rate=effective_rate,
        marginal_rate=marginal_rate,
        combined_taxable=combined_taxable,
        combined_total=combined_total,
        schedule=schedule,
    )


def to_response(result: TaxResult) -> dict[str, object]:
    with localcontext() as ctx:
        ctx.prec = PRECISION
        separate_total = result.comprehensive_tax + result.bonus_separate_tax
        comparison = _comparison(result, separate_total)
        schedule = [
            {
                "month": row.month,
                "income": _money(row.cumulative_income),
                "deduction": _money(row.cumulative_deduction),
                "taxable": _money(row.cumulative_taxable),
                "tax": _money(row.tax),
                "cumulative_tax": _money(row.cumulative_tax),
            }
            for row in result.schedule
        ]
        schedule_tax = result.schedule[-1].cumulative_tax if result.schedule else Decimal(0)

        return {
            "income_basis": result.income_basis,
            "annual_income": _money(result.annual_income),
            "monthly_income": _money(result.monthly_income),
            "bonus": _money(result.bonus),
            "bonus_mode": result.bonus_mode,
            "deductions": {
                "basic": _money(result.basic_deduction),
                "social": _money(result.social_annual),
                "special": _money(result.special_annual),
                "annual": _money(result.annual_extra_deduction),
                "total": _money(result.deductions_total),
            },
            "taxable_income": _money(result.taxable_income),
            "comprehensive_tax": _money(result.comprehensive_tax),
            "bonus_tax": _money(result.bonus_tax),
            "total_tax": _money(result.total_tax),
            "net_income": _money(result.net_income),
            "effective_rate_percent": _format_percent(result.effective_rate),
            "marginal_rate_percent": _format_percent(result.marginal_rate),
            "bonus_comparison": comparison,
            "schedule": schedule,
            "schedule_total": {
                "tax": _money(schedule_tax),
                "income": _money(result.annual_income),
                "deduction": _money(result.schedule[-1].cumulative_deduction)
                if result.schedule
                else "0.00",
            },
            "formula": _formula(result, separate_total),
            "note": _note(result),
        }


def _withholding_schedule(
    monthly_income: Decimal,
    social_monthly: Decimal,
    special_monthly: Decimal,
) -> tuple[MonthlyRow, ...]:
    """累计预扣法：按累计所得查表，再减去已预扣税额。"""
    per_month_deduction = BASIC_DEDUCTION_MONTHLY + social_monthly + special_monthly
    rows: list[MonthlyRow] = []
    previous = Decimal(0)
    for month in range(1, 13):
        cumulative_income = monthly_income * month
        cumulative_deduction = per_month_deduction * month
        cumulative_taxable = max(cumulative_income - cumulative_deduction, Decimal(0))
        cumulative_tax = _round_money(_tax(cumulative_taxable, BRACKETS))
        rows.append(
            MonthlyRow(
                month=month,
                cumulative_income=cumulative_income,
                cumulative_deduction=cumulative_deduction,
                cumulative_taxable=cumulative_taxable,
                tax=cumulative_tax - previous,
                cumulative_tax=cumulative_tax,
            )
        )
        previous = cumulative_tax
    return tuple(rows)


def _tax(
    taxable: Decimal, brackets: tuple[tuple[Decimal | None, Decimal, Decimal], ...]
) -> Decimal:
    if taxable <= 0:
        return Decimal(0)
    rate, quick = _bracket(taxable, brackets)
    return taxable * rate - quick


def _bracket(
    taxable: Decimal,
    brackets: tuple[tuple[Decimal | None, Decimal, Decimal], ...],
) -> tuple[Decimal, Decimal]:
    for limit, rate, quick in brackets:
        if limit is None or taxable <= limit:
            return rate, quick
    return brackets[-1][1], brackets[-1][2]


def _bracket_rate(
    taxable: Decimal,
    brackets: tuple[tuple[Decimal | None, Decimal, Decimal], ...],
) -> Decimal:
    if taxable <= 0:
        return Decimal(0)
    return _bracket(taxable, brackets)[0]


def _bonus_tax(bonus: Decimal) -> Decimal:
    """全年一次性奖金单独计税：按奖金 ÷ 12 查月度税率表。"""
    if bonus <= 0:
        return Decimal(0)
    rate, quick = _bracket(bonus / 12, MONTHLY_BRACKETS)
    return bonus * rate - quick


def _comparison(result: TaxResult, separate_total: Decimal) -> dict[str, object]:
    separate = _round_money(separate_total)
    combined = _round_money(result.combined_total)
    if result.bonus <= 0:
        better = "equal"
        saving = Decimal(0)
        note = "未填写年终奖，不涉及计税方式选择"
    elif separate < combined:
        better = "separate"
        saving = combined - separate
        note = f"单独计税更省 {_money(saving)} 元"
    elif combined < separate:
        better = "combined"
        saving = separate - combined
        note = f"并入综合所得更省 {_money(saving)} 元"
    else:
        better = "equal"
        saving = Decimal(0)
        note = "两种计税方式税额相同"
    return {
        "separate_tax": _money(separate),
        "combined_tax": _money(combined),
        "better": better,
        "saving": _money(saving),
        "note": note,
    }


def _formula(result: TaxResult, separate_total: Decimal) -> str:
    lines = [
        "综合所得应纳税所得额 = 年收入 − 基本减除 − 三险一金 − 专项附加扣除 − 年度扣除",
        f"  = {_money(result.annual_income)} − {_money(result.basic_deduction)}"
        f" − {_money(result.social_annual)} − {_money(result.special_annual)}"
        f" − {_money(result.annual_extra_deduction)} = {_money(result.taxable_income)}",
    ]
    if result.taxable_income > 0:
        rate, quick = _bracket(result.taxable_income, BRACKETS)
        lines.append(
            f"工资薪金应纳税额 = {_money(result.taxable_income)} × {_whole_percent(rate)}"
            f" − {_money(quick)} = {_money(result.comprehensive_tax)}"
        )
    else:
        lines.append("应纳税所得额 ≤ 0，工资薪金部分无需缴税")

    if result.bonus > 0:
        if result.bonus_mode == "separate":
            rate, quick = _bracket(result.bonus / 12, MONTHLY_BRACKETS)
            lines.append(
                f"年终奖 {_money(result.bonus)} 单独计税：÷ 12 = "
                f"{_money(result.bonus / 12)} → 适用 {_whole_percent(rate)}"
            )
            lines.append(
                f"  = {_money(result.bonus)} × {_whole_percent(rate)}"
                f" − {_money(quick)} = {_money(result.bonus_separate_tax)}"
            )
        else:
            rate, quick = _bracket(result.combined_taxable, BRACKETS)
            lines.append(
                f"年终奖 {_money(result.bonus)} 并入综合所得："
                f"应纳税所得额 {_money(result.combined_taxable)}"
            )
            lines.append(
                f"  = {_money(result.combined_taxable)} × {_whole_percent(rate)}"
                f" − {_money(quick)} = {_money(result.combined_total)}"
            )
        lines.append(f"合计应纳税额 = {_money(result.total_tax)}")
    elif result.bonus_mode == "separate":
        lines.append("合计应纳税额 = 工资薪金应纳税额")

    if result.bonus > 0 and result.bonus_mode == "separate":
        lines.append(
            f"对照：并入综合所得应纳税额 {_money(result.combined_total)}"
            f"（单独计税合计 {_money(_round_money(separate_total))}）"
        )
    return "\n".join(lines)


def _note(result: TaxResult) -> str:
    parts = [
        "按居民个人综合所得年度汇算口径计算；月度预扣采用累计预扣法，仅供对照，最终以汇算为准。",
    ]
    if result.annual_extra_deduction > 0:
        parts.append(
            "大病医疗与个人养老金在汇算时扣除，不计入月度预扣，预扣合计可能与汇算税额不同。"
        )
    if result.bonus > 0:
        parts.append("全年一次性奖金单独计税政策按现行规定执行至 2027 年 12 月 31 日。")
    return "".join(parts)


def _parse_amount(raw: str | None, field: str, label: str) -> Decimal:
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
    if value > MAX_AMOUNT:
        raise InputError(field, f"{label}超出可计算范围")
    return value


def _round_money(value: Decimal) -> Decimal:
    return value.quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _money(value: Decimal) -> str:
    return f"{_round_money(value):,.2f}"


def _format_percent(value: Decimal) -> str:
    return f"{(value * 100).quantize(_PERCENT_QUANTUM, rounding=ROUND_HALF_UP):,.4f}"


def _whole_percent(rate: Decimal) -> str:
    return f"{(rate * 100).quantize(Decimal('1')):f}%"
