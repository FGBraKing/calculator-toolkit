"""Resale taxes for residential property: deed tax, VAT, surcharges, income tax."""

from __future__ import annotations

from decimal import Decimal, localcontext

from app import common
from app.calculator import InputError

PRECISION = 50
VAT_RATE = Decimal("0.05")
DEEMED_RATE = Decimal("0.01")
DIFFERENCE_RATE = Decimal("0.20")
CONCESSION_AREA = Decimal("140")
STATUTORY_MIN = Decimal("0.03")
STATUTORY_MAX = Decimal("0.05")
HOMES = ("first", "second", "third")
TAX_MODES = ("deemed", "difference")
HOME_LABELS = {"first": "首套", "second": "二套", "third": "三套及以上"}


def calculate(payload: dict[str, str]) -> dict[str, object]:
    price = common.amount(
        payload.get("price"), "price", "成交价", allow_zero=False, maximum=Decimal("1e12")
    )
    area = common.amount(
        payload.get("area"), "area", "建筑面积", allow_zero=False, maximum=Decimal("10000")
    )
    homes = payload.get("homes", "first")
    if homes not in HOMES:
        raise InputError("homes", "买方套数无效")
    paid_two = payload.get("paid_two", "no") == "yes"
    only_home = payload.get("only_home", "no") == "yes"
    if only_home and not paid_two:
        raise InputError("only_home", "满五唯一需同时满足满二")
    original = common.amount(
        payload.get("original"), "original", "卖方原值", maximum=Decimal("1e12")
    )
    tax_mode = payload.get("tax_mode", "deemed")
    if tax_mode not in TAX_MODES:
        raise InputError("tax_mode", "个税方式无效")
    statutory = common.rate(
        payload.get("statutory"), "statutory", "法定契税率", maximum=Decimal("5")
    )
    if not STATUTORY_MIN <= statutory <= STATUTORY_MAX:
        raise InputError("statutory", "法定契税率需在 3%–5% 之间")
    surcharge = common.rate(
        payload.get("surcharge"), "surcharge", "增值税附加", maximum=Decimal("20")
    )

    with localcontext() as ctx:
        ctx.prec = PRECISION
        if homes == "third":
            deed_rate = statutory
        elif homes == "first":
            deed_rate = Decimal("0.01") if area <= CONCESSION_AREA else Decimal("0.015")
        else:
            deed_rate = Decimal("0.01") if area <= CONCESSION_AREA else Decimal("0.02")
        deed = price * deed_rate

        vat = Decimal(0) if paid_two else price / (1 + VAT_RATE) * VAT_RATE
        surtax = vat * surcharge

        if only_home:
            income_tax = Decimal(0)
        elif tax_mode == "deemed":
            income_tax = price * DEEMED_RATE
        else:
            if original <= 0:
                raise InputError("original", "差额计税需填写卖方原值")
            income_tax = max(price - original, Decimal(0)) * DIFFERENCE_RATE

        buyer_total = deed
        seller_total = vat + surtax + income_tax
        total = buyer_total + seller_total
        share = total / price

    vat_base = price / (1 + VAT_RATE)
    facts = [
        f"{HOME_LABELS[homes]} · {common.decimal_plain(area)} ㎡ · "
        f"契税 {common.percent_plain(deed_rate)}%",
        ("满二：增值税免征" if paid_two else "未满二：按 5% 缴纳增值税")
        + (" · 满五唯一：个税免征" if only_home else " · 个税照常"),
        "个税按核定 1%" if tax_mode == "deemed" else "个税按差额 20%",
    ]
    formula = "\n".join(
        [
            f"契税 = 成交价 × {common.percent_plain(deed_rate)}% = {common.money(price)}"
            f" × {common.percent_plain(deed_rate)}% = {common.money(deed)}",
            (
                "增值税 = 0（满二免征）"
                if paid_two
                else f"增值税 = 成交价 ÷ (1 + 5%) × 5% = {common.money(vat_base)} × 5%"
                f" = {common.money(vat)}"
            ),
            f"城建及附加 = 增值税 × {common.percent_plain(surcharge)}% = {common.money(surtax)}",
            (
                "个人所得税 = 0（满五唯一免征）"
                if only_home
                else (
                    f"个人所得税 = 成交价 × 1%（核定） = {common.money(income_tax)}"
                    if tax_mode == "deemed"
                    else f"个人所得税 = (成交价 − 原值) × 20% = "
                    f"({common.money(price)} − {common.money(original)}) × 20%"
                    f" = {common.money(income_tax)}"
                )
            ),
            f"买卖双方合计 = {common.money(buyer_total)} + {common.money(seller_total)}"
            f" = {common.money(total)}（占成交价 {common.percent_plain(share)}%）",
        ]
    )
    return common.response(
        primary=common.money(total),
        facts=facts,
        metrics=[
            ("买方合计", f"{common.money(buyer_total)} 元"),
            ("卖方合计", f"{common.money(seller_total)} 元"),
            ("占成交价", f"{common.percent_plain(share)}%"),
        ],
        formula=formula,
        note="按住宅口径测算：契税按 2024-12-01 起的 140 ㎡ 与套数分档；增值税 5% 及附加"
        "（城建税与教育费附加合计通常为增值税的 12%，县城/镇 10%、其他 6%，可修改）；"
        "个人所得税按核定 1% 或差额 20%（合理费用未扣）。非住宅（商铺、写字楼）未涵盖，"
        "土地增值税、印花税等未计入，以当地税务口径为准。",
        schedule=common.table(
            columns=["税种", "承担方", "计税依据", "金额"],
            rows=[
                [
                    "契税",
                    "买方",
                    f"{common.money(price)} × {common.percent_plain(deed_rate)}%",
                    common.money(deed),
                ],
                [
                    "增值税",
                    "卖方",
                    "满二免征" if paid_two else f"{common.money(vat_base)} × 5%",
                    common.money(vat),
                ],
                [
                    "城建及附加",
                    "卖方",
                    f"增值税 × {common.percent_plain(surcharge)}%",
                    common.money(surtax),
                ],
                [
                    "个人所得税",
                    "卖方",
                    "满五唯一免征"
                    if only_home
                    else ("成交价 × 1%" if tax_mode == "deemed" else "差额 × 20%"),
                    common.money(income_tax),
                ],
            ],
            totals=[
                ("买方合计", f"{common.money(buyer_total)} 元"),
                ("卖方合计", f"{common.money(seller_total)} 元"),
                ("合计", f"{common.money(total)} 元"),
            ],
            meta=f"成交价 {common.money(price)} 元",
            note="金额单位：元；实际以当地税务部门核定为准。",
        ),
    )
