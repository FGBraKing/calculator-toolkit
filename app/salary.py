"""Net salary: social insurance, housing fund and cumulative withholding."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, localcontext

from app import common
from app.tax import BRACKETS

PRECISION = 50
BASIC_DEDUCTION = Decimal("5000")
MONTHS = 12
_MONEY_QUANTUM = Decimal("0.01")


def calculate(payload: dict[str, str]) -> dict[str, object]:
    salary = common.amount(
        payload.get("salary"), "salary", "税前月薪", allow_zero=False, maximum=Decimal("1e9")
    )
    base = common.amount(
        payload.get("base"), "base", "社保缴费基数", allow_zero=False, maximum=Decimal("1e9")
    )
    social_rate = common.rate(
        payload.get("social_rate"), "social_rate", "社保个人比例", maximum=Decimal("30")
    )
    fund_rate = common.rate(
        payload.get("fund_rate"), "fund_rate", "公积金比例", maximum=Decimal("12")
    )
    deduction = common.amount(
        payload.get("deduction"), "deduction", "专项附加扣除", maximum=Decimal("1e6")
    )

    with localcontext() as ctx:
        ctx.prec = PRECISION
        social = base * social_rate
        fund = base * fund_rate
        insurance = social + fund
        monthly_deduction = BASIC_DEDUCTION + insurance + deduction

        rows: list[list[str]] = []
        taxes: list[Decimal] = []
        nets: list[Decimal] = []
        previous = Decimal(0)
        for month in range(1, MONTHS + 1):
            cumulative_income = salary * month
            cumulative_deduction = monthly_deduction * month
            cumulative_taxable = max(cumulative_income - cumulative_deduction, Decimal(0))
            cumulative_tax = _round(_tax(cumulative_taxable))
            tax = cumulative_tax - previous
            net = salary - insurance - tax
            taxes.append(tax)
            nets.append(net)
            rows.append(
                [
                    str(month),
                    common.money(cumulative_income),
                    common.money(cumulative_deduction),
                    common.money(tax),
                    common.money(net),
                ]
            )
            previous = cumulative_tax

        total_tax = previous
        total_insurance = insurance * MONTHS
        total_net = salary * MONTHS - total_insurance - total_tax
        average_net = total_net / MONTHS

        first_taxable = max(salary - monthly_deduction, Decimal(0))
        first_rate, first_quick = _bracket(first_taxable)
        first_tax = taxes[0]

    facts = [
        f"缴费基数 {common.money(base)} 元",
        f"社保 {common.percent_plain(social_rate)}% + 公积金 {common.percent_plain(fund_rate)}%"
        f" = 每月 {common.money(insurance)} 元",
        f"首月到手 {common.money(nets[0])} 元 · 末月 {common.money(nets[-1])} 元",
    ]
    formula = "\n".join(
        [
            "每月五险一金 = 缴费基数 × (社保比例 + 公积金比例)",
            f"  = {common.money(base)} × ({common.percent_plain(social_rate)}%"
            f" + {common.percent_plain(fund_rate)}%) = {common.money(insurance)}",
            "累计预扣：累计应纳税所得额 = 累计收入 − 5,000 × 月数"
            " − 累计五险一金 − 累计专项附加扣除",
            f"首月个税 = {common.money(first_taxable)}"
            f" × {common.percent_plain(first_rate)}% − {common.money(first_quick)}"
            f" = {common.money(first_tax)}",
            f"全年个税 = 累计预扣合计 = {common.money(total_tax)}",
            f"全年到手 = {common.money(salary)} × 12 − {common.money(insurance)} × 12"
            f" − {common.money(total_tax)} = {common.money(total_net)}",
            f"月均到手 = {common.money(total_net)} ÷ 12 = {common.money(average_net)}",
        ]
    )
    return common.response(
        primary=common.money(average_net),
        facts=facts,
        metrics=[
            ("每月五险一金", f"{common.money(insurance)} 元"),
            ("全年个税", f"{common.money(total_tax)} 元"),
            ("全年到手", f"{common.money(total_net)} 元"),
        ],
        formula=formula,
        note="五险一金只计个人缴纳部分，按缴费基数 × 比例计算；个税按累计预扣法逐月预缴，"
        "年终奖、一次性扣除、补充公积金等未计入，实际以工资条与汇算为准。",
        schedule=common.table(
            columns=["月份", "累计收入", "累计扣除", "当月个税", "当月到手"],
            rows=rows,
            totals=[
                ("全年到手", f"{common.money(total_net)} 元"),
                ("全年个税", f"{common.money(total_tax)} 元"),
                ("全年五险一金", f"{common.money(total_insurance)} 元"),
            ],
            meta=f"共 {MONTHS} 个月，税前月薪 {common.money(salary)} 元",
            note="金额单位：元；「累计扣除」= 5,000 × 月数 + 累计五险一金 + 累计专项附加扣除。",
        ),
    )


def _tax(taxable: Decimal) -> Decimal:
    if taxable <= 0:
        return Decimal(0)
    rate, quick = _bracket(taxable)
    return taxable * rate - quick


def _bracket(taxable: Decimal) -> tuple[Decimal, Decimal]:
    if taxable <= 0:
        return BRACKETS[0][1], BRACKETS[0][2]
    for limit, rate, quick in BRACKETS:
        if limit is None or taxable <= limit:
            return rate, quick
    return BRACKETS[-1][1], BRACKETS[-1][2]


def _round(value: Decimal) -> Decimal:
    return value.quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP)
