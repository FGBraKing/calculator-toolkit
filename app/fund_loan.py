"""Housing-fund loan, optionally combined with a commercial loan."""

from __future__ import annotations

from decimal import Decimal, localcontext

from app import common
from app.calculator import InputError
from app.loans import METHODS, level_payment, principal_rows

PRECISION = 50


def calculate(payload: dict[str, str]) -> dict[str, object]:
    total = common.amount(
        payload.get("total"), "total", "贷款总额", allow_zero=False, maximum=Decimal("1e9")
    )
    fund = common.amount(payload.get("fund"), "fund", "公积金贷款额度", maximum=Decimal("1e9"))
    years = common.integer(payload.get("years"), "years", "贷款年限", 1, 40)
    fund_rate = common.rate(
        payload.get("fund_rate"), "fund_rate", "公积金利率", maximum=Decimal("10")
    )
    commercial_rate = common.rate(
        payload.get("commercial_rate"), "commercial_rate", "商贷利率", maximum=Decimal("24")
    )
    method = payload.get("method", "equal_installment")
    if method not in METHODS:
        raise InputError("method", "还款方式无效")
    if fund > total:
        raise InputError("fund", "公积金贷款额度不能超过贷款总额")

    commercial = total - fund
    with localcontext() as ctx:
        ctx.prec = PRECISION
        months = years * 12
        rate_fund = fund_rate / 12
        rate_commercial = commercial_rate / 12
        if method == "equal_installment":
            payment_fund = level_payment(fund, rate_fund, months) if fund > 0 else Decimal(0)
            payment_commercial = (
                level_payment(commercial, rate_commercial, months) if commercial > 0 else Decimal(0)
            )
            interest_fund = payment_fund * months - fund
            interest_commercial = payment_commercial * months - commercial
            first_payment = last_payment = payment_fund + payment_commercial
            first_payment_fund = payment_fund
            first_payment_commercial = payment_commercial
        else:
            rows_fund = principal_rows(fund, rate_fund, months) if fund > 0 else []
            rows_commercial = (
                principal_rows(commercial, rate_commercial, months) if commercial > 0 else []
            )
            interest_fund = sum((interest for _, interest in rows_fund), Decimal(0))
            interest_commercial = sum((interest for _, interest in rows_commercial), Decimal(0))
            first_payment_fund = rows_fund[0][0] + rows_fund[0][1] if rows_fund else Decimal(0)
            first_payment_commercial = (
                rows_commercial[0][0] + rows_commercial[0][1] if rows_commercial else Decimal(0)
            )
            first_payment = first_payment_fund + first_payment_commercial
            last_payment_fund = rows_fund[-1][0] + rows_fund[-1][1] if rows_fund else Decimal(0)
            last_payment_commercial = (
                rows_commercial[-1][0] + rows_commercial[-1][1] if rows_commercial else Decimal(0)
            )
            last_payment = last_payment_fund + last_payment_commercial
        total_interest = interest_fund + interest_commercial

    facts = [
        f"公积金 {common.money(fund)} 元 · 商贷 {common.money(commercial)} 元",
        f"公积金利率 {common.percent_plain(fund_rate)}% · "
        f"商贷 {common.percent_plain(commercial_rate)}%",
    ]
    if method == "equal_installment":
        facts.append(f"共 {months} 期，月供固定")
        formula = "\n".join(
            [
                "公积金月供 = 公积金额度 × i ÷ (1 − (1 + i)^-n)",
                f"  = {common.money(fund)} × {common.percent_plain(fund_rate)}%/12"
                f" → {common.money(first_payment_fund)}",
                f"商贷月供 = {common.money(commercial)} 按 {common.percent_plain(commercial_rate)}%"
                f" → {common.money(first_payment_commercial)}",
                f"合计月供 = {common.money(first_payment_fund)}"
                f" + {common.money(first_payment_commercial)} = {common.money(first_payment)}",
                f"合计利息 = 月供 × {months} − {common.money(total)}"
                f" = {common.money(total_interest)}",
            ]
        )
    else:
        facts.append(
            f"首月 {common.money(first_payment)} 元 · 末月 {common.money(last_payment)} 元"
        )
        formula = "\n".join(
            [
                "等额本金：每月本金 = 贷款额 ÷ 期数，利息按剩余本金计",
                f"公积金每月本金 {common.money(fund / months)} + 首月利息"
                f" {common.money(fund * rate_fund)} = {common.money(first_payment_fund)}",
                f"商贷每月本金 {common.money(commercial / months)} + 首月利息"
                f" {common.money(commercial * rate_commercial)}"
                f" = {common.money(first_payment_commercial)}",
                f"首月合计 {common.money(first_payment)}，末月 {common.money(last_payment)}",
                f"合计利息 = {common.money(interest_fund)} + {common.money(interest_commercial)}"
                f" = {common.money(total_interest)}",
            ]
        )

    return common.response(
        primary=common.money(first_payment),
        facts=facts,
        metrics=[
            ("合计利息", f"{common.money(total_interest)} 元"),
            ("公积金利息", f"{common.money(interest_fund)} 元"),
            ("商贷利息", f"{common.money(interest_commercial)} 元"),
        ],
        formula=formula,
        note="公积金贷款 5 年以上年利率 2.6%（2025-05-08 起），5 年及以下 2.1%；"
        "商贷按合同或 LPR 加点填写。公积金额度受当地最高限额与账户余额限制，"
        "超出部分按商贷计算。",
    )
