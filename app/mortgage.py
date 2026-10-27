"""Mortgage payments for 等额本息 and 等额本金."""

from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal, localcontext

from app import common
from app.calculator import InputError
from app.loans import level_payment, level_rows, principal_rows

METHODS = ("equal_installment", "equal_principal")
PRECISION = 50
_CENT = Decimal("1")


def calculate(payload: dict[str, str]) -> dict[str, object]:
    principal = common.amount(
        payload.get("amount"), "amount", "贷款金额", allow_zero=False, maximum=Decimal("1e9")
    )
    years = common.integer(payload.get("years"), "years", "贷款年限", 1, 40)
    annual_rate = common.rate(payload.get("rate"), "rate", "年利率", maximum=Decimal("24"))
    method = payload.get("method", "equal_installment")
    if method not in METHODS:
        raise InputError("method", "还款方式无效")

    with localcontext() as ctx:
        ctx.prec = PRECISION
        months = years * 12
        monthly_rate = annual_rate / 12
        if method == "equal_installment":
            payment = level_payment(principal, monthly_rate, months)
            rows = level_rows(principal, monthly_rate, months, payment)
            first_payment = last_payment = payment
        else:
            rows = principal_rows(principal, monthly_rate, months)

        total_interest = sum((interest for _, interest in rows), Decimal(0))
        total_payment = principal + total_interest
        schedule_rows, first_cents, last_cents = _reconcile(rows, principal, total_interest)
        first_payment = Decimal(first_cents) / 100
        last_payment = Decimal(last_cents) / 100

    facts = [f"共 {months} 期", "等额本息" if method == "equal_installment" else "等额本金"]
    if method == "equal_principal":
        facts.append(
            f"首月 {common.money(first_payment)} 元 · 末月 {common.money(last_payment)} 元"
            f" · 每月递减 {common.money(principal / months * monthly_rate)} 元"
        )
        formula = _principal_formula(principal, monthly_rate, months, total_interest)
    else:
        formula = _level_formula(
            principal, annual_rate, monthly_rate, months, payment, total_interest
        )

    return common.response(
        primary=common.money(first_payment),
        facts=facts,
        metrics=[
            ("贷款总额", f"{common.money(principal)} 元"),
            ("还款总额", f"{common.money(total_payment)} 元"),
            ("总利息", f"{common.money(total_interest)} 元"),
        ],
        formula=formula,
        note="月供四舍五入到分，最后一期吸收分位尾差；实际放款以银行核定的利率与还款计划为准。",
        schedule=common.table(
            columns=["期次", "月供", "本金", "利息", "剩余本金"],
            rows=schedule_rows,
            totals=[
                ("还款总额", f"{common.money(total_payment)} 元"),
                ("本金合计", f"{common.money(principal)} 元"),
                ("利息合计", f"{common.money(total_interest)} 元"),
            ],
            meta=f"共 {months} 期",
            note="金额单位：元；本金列合计等于贷款金额，利息列合计等于总利息。",
        ),
    )


def _to_cents(value: Decimal) -> int:
    return int((value * 100).quantize(_CENT, rounding=ROUND_HALF_UP))


def _reconcile(
    rows: list[tuple[Decimal, Decimal]],
    total_principal: Decimal,
    total_interest: Decimal,
) -> tuple[list[list[str]], int, int]:
    total_p = _to_cents(total_principal)
    total_i = _to_cents(total_interest)
    p_cents = [_to_cents(value) for value, _ in rows]
    i_cents = [_to_cents(value) for _, value in rows]
    p_cents[-1] = total_p - sum(p_cents[:-1])
    i_cents[-1] = total_i - sum(i_cents[:-1])

    out: list[list[str]] = []
    balance = total_p
    for index in range(len(rows)):
        balance -= p_cents[index]
        out.append(
            [
                str(index + 1),
                common.money(Decimal(p_cents[index] + i_cents[index]) / 100),
                common.money(Decimal(p_cents[index]) / 100),
                common.money(Decimal(i_cents[index]) / 100),
                common.money(Decimal(max(balance, 0)) / 100),
            ]
        )
    return out, p_cents[0] + i_cents[0], p_cents[-1] + i_cents[-1]


def _level_formula(
    principal: Decimal,
    annual_rate: Decimal,
    monthly_rate: Decimal,
    months: int,
    payment: Decimal,
    total_interest: Decimal,
) -> str:
    return "\n".join(
        [
            "等额本息：A = P × i × (1 + i)^n ÷ ((1 + i)^n − 1)",
            f"  P = {common.money(principal)}，i = {common.percent_plain(annual_rate)}% ÷ 12"
            f" = {common.percent_plain(monthly_rate)}%，n = {months}",
            f"  A = {common.money(payment)}",
            f"总利息 = A × n − P = {common.money(total_interest)}",
        ]
    )


def _principal_formula(
    principal: Decimal,
    monthly_rate: Decimal,
    months: int,
    total_interest: Decimal,
) -> str:
    per_principal = principal / months
    return "\n".join(
        [
            "等额本金：每月本金 = P ÷ n；利息 = 剩余本金 × 月利率",
            f"  每月本金 = {common.money(principal)} ÷ {months} = {common.money(per_principal)}",
            f"  首月利息 = {common.money(principal)} × {common.percent_plain(monthly_rate)}%"
            f" = {common.money(principal * monthly_rate)}",
            f"  每月递减 = 每月本金 × 月利率 = {common.money(per_principal * monthly_rate)}",
            f"总利息 = (n + 1) × P × i ÷ 2 = {common.money(total_interest)}",
        ]
    )
