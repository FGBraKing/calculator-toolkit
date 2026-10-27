"""Early repayment: shorten the term or lower the monthly payment."""

from __future__ import annotations

from decimal import ROUND_CEILING, Decimal, localcontext

from app import common
from app.calculator import InputError
from app.loans import METHODS, level_payment

PRECISION = 50


def calculate(payload: dict[str, str]) -> dict[str, object]:
    principal = common.amount(
        payload.get("principal"), "principal", "剩余本金", allow_zero=False, maximum=Decimal("1e9")
    )
    annual_rate = common.rate(payload.get("rate"), "rate", "年利率", maximum=Decimal("24"))
    months = common.integer(payload.get("months"), "months", "剩余期数", 1, 480)
    extra = common.amount(
        payload.get("extra"), "extra", "提前还款额", allow_zero=False, maximum=Decimal("1e9")
    )
    penalty = common.amount(payload.get("penalty"), "penalty", "违约金", maximum=Decimal("1e9"))
    method = payload.get("method", "equal_installment")
    if method not in METHODS:
        raise InputError("method", "还款方式无效")
    if extra >= principal:
        raise InputError("extra", "提前还款额需小于剩余本金")

    with localcontext() as ctx:
        ctx.prec = PRECISION
        rate = annual_rate / 12
        remaining = principal - extra
        if method == "equal_installment":
            payment = level_payment(principal, rate, months)
            original_payment = payment
            old_interest = payment * months - principal
            short_months, short_paid = _shorten(remaining, rate, payment)
            interest_short = short_paid - remaining
            short_payment = payment
            new_payment = level_payment(remaining, rate, months)
            interest_lower = new_payment * months - remaining
            lower_months = months
        else:
            per_principal = principal / months
            original_payment = per_principal + principal * rate
            old_interest = rate * principal * (months + 1) / 2
            short_months = _ceil(remaining / per_principal)
            interest_short = rate * (
                remaining * short_months - per_principal * short_months * (short_months - 1) / 2
            )
            short_payment = per_principal + remaining * rate
            new_per_principal = remaining / months
            new_payment = new_per_principal + remaining * rate
            interest_lower = rate * remaining * (months + 1) / 2
            lower_months = months

        saving_short = old_interest - interest_short
        saving_lower = old_interest - interest_lower
        net_saving = saving_short - penalty

    facts = [
        f"原月供 {common.money(original_payment)} 元",
        f"提前还款 {common.money(extra)} 元后剩余本金 {common.money(remaining)} 元",
        f"违约金 {common.money(penalty)} 元",
    ]
    better = "缩短年限" if saving_short >= saving_lower else "减少月供"
    schedule = common.table(
        columns=["方案", "新月供", "剩余期数", "总利息", "节省利息"],
        rows=[
            [
                "缩短年限",
                common.money(short_payment),
                f"{short_months} 期",
                common.money(interest_short),
                common.money(saving_short),
            ],
            [
                "减少月供",
                common.money(new_payment),
                f"{lower_months} 期",
                common.money(interest_lower),
                common.money(saving_lower),
            ],
        ],
        totals=[
            (
                "更省的方案",
                f"{better}，多省 {common.money(abs(saving_short - saving_lower))} 元",
            )
        ],
        meta=f"剩余本金 {common.money(principal)} 元 · 剩余 {months} 期"
        f" · 年利率 {common.percent_plain(annual_rate)}%",
        note="节省利息 = 原剩余利息 − 提前还款后的剩余利息；净节省还需扣除违约金。",
    )
    formula = "\n".join(
        [
            f"原剩余利息 = {common.money(old_interest)}",
            f"缩年限：月供不变（{common.money(short_payment)}），"
            f"剩余期数 {months} → {short_months}，利息 {common.money(interest_short)}，"
            f"省 {common.money(saving_short)}",
            f"降月供：期数不变（{lower_months}），月供 {common.money(new_payment)}，"
            f"利息 {common.money(interest_lower)}，省 {common.money(saving_lower)}",
            f"净节省（缩短年限 − 违约金）= {common.money(saving_short)} − {common.money(penalty)}"
            f" = {common.money(net_saving)}",
        ]
    )
    return common.response(
        primary=common.money(net_saving),
        facts=facts,
        metrics=[
            ("原剩余利息", f"{common.money(old_interest)} 元"),
            ("缩年限后利息", f"{common.money(interest_short)} 元"),
            ("净节省（缩年限）", f"{common.money(net_saving)} 元"),
        ],
        formula=formula,
        note="提前还款后按剩余本金重算；缩年限保持月供不变、期数缩短，降月供保持期数不变、"
        "月供降低。部分银行对提前还款收取违约金或限制次数，以贷款合同为准。",
        schedule=schedule,
    )


def _shorten(principal: Decimal, rate: Decimal, payment: Decimal) -> tuple[int, Decimal]:
    balance = principal
    paid = Decimal(0)
    months = 0
    while balance > 0:
        interest = balance * rate
        due = balance + interest
        if due <= payment:
            paid += due
            balance = Decimal(0)
        else:
            paid += payment
            balance = due - payment
        months += 1
        if months > 1200:
            raise InputError("extra", "按当前月供无法还清剩余本金，请检查输入")
    return months, paid


def _ceil(value: Decimal) -> int:
    integral = value.to_integral_value(rounding=ROUND_CEILING)
    return int(integral)
