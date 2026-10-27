"""Deed tax (契税) for housing and non-housing transfers."""

from __future__ import annotations

from decimal import Decimal, localcontext

from app import common
from app.calculator import InputError

PRECISION = 50
CONCESSION_AREA = Decimal("140")
HOUSE_TYPES = ("housing", "non_housing")
HOME_TYPES = ("first", "second", "third")
STATUTORY_MIN = Decimal("0.03")
STATUTORY_MAX = Decimal("0.05")


def calculate(payload: dict[str, str]) -> dict[str, object]:
    kind = payload.get("type", "housing")
    if kind not in HOUSE_TYPES:
        raise InputError("type", "房屋类型无效")
    price = common.amount(
        payload.get("price"), "price", "成交价格", allow_zero=False, maximum=Decimal("1e12")
    )
    statutory = common.rate(
        payload.get("statutory_rate"), "statutory_rate", "当地法定税率", maximum=Decimal("5")
    )
    if not STATUTORY_MIN <= statutory <= STATUTORY_MAX:
        raise InputError("statutory_rate", "法定税率需在 3%–5% 之间")

    with localcontext() as ctx:
        ctx.prec = PRECISION
        if kind == "non_housing":
            rate = statutory
            facts = [
                "非住房（商铺、写字楼等）",
                f"适用当地法定税率 {common.percent_plain(statutory)}%",
            ]
            basis = "非住房按当地法定税率 3%–5% 计征"
        else:
            homes = payload.get("homes", "first")
            if homes not in HOME_TYPES:
                raise InputError("homes", "住房套数无效")
            area = common.amount(
                payload.get("area"), "area", "建筑面积", allow_zero=False, maximum=Decimal("10000")
            )
            if homes == "third":
                rate = statutory
            elif homes == "first":
                rate = Decimal("0.01") if area <= CONCESSION_AREA else Decimal("0.015")
            else:
                rate = Decimal("0.01") if area <= CONCESSION_AREA else Decimal("0.02")
            home_label = {"first": "首套", "second": "第二套", "third": "三套及以上"}[homes]
            facts = [
                f"住房（{home_label}）",
                f"建筑面积 {common.decimal_plain(area)} ㎡",
                f"适用税率 {common.percent_plain(rate)}%",
            ]
            basis = _housing_basis(homes, area)
        tax = price * rate
        statutory_tax = price * statutory

    formula = "\n".join(
        [
            f"计税规则：{basis}",
            f"应纳税额 = 成交价格 × 税率 = {common.money(price)} × {common.percent_plain(rate)}%"
            f" = {common.money(tax)}",
            f"对照：若按当地法定税率 {common.percent_plain(statutory)}% 计征，"
            f"应纳税额 {common.money(statutory_tax)}，优惠 {common.money(statutory_tax - tax)}",
        ]
    )
    return common.response(
        primary=common.money(tax),
        facts=facts,
        metrics=[
            ("成交价格", f"{common.money(price)} 元"),
            ("适用税率", f"{common.percent_plain(rate)}%"),
            ("按法定税率应纳税额", f"{common.money(statutory_tax)} 元"),
        ],
        formula=formula,
        note="依据财政部 税务总局 住房城乡建设部公告 2024 年第 16 号，自 2024 年 12 月 1 日起："
        "个人购买家庭唯一住房，面积 140 ㎡及以下减按 1%、140 ㎡以上减按 1.5%；"
        "家庭第二套住房，140 ㎡及以下减按 1%、140 ㎡以上减按 2%；三套及以上与非住房按当地"
        "法定税率（3%–5%）计征。北京、上海、广州、深圳同样适用上述规定。",
    )


def _housing_basis(homes: str, area: Decimal) -> str:
    small = area <= CONCESSION_AREA
    if homes == "first":
        return f"家庭唯一住房，{'140 ㎡及以下减按 1%' if small else '140 ㎡以上减按 1.5%'}"
    if homes == "second":
        return f"家庭第二套住房，{'140 ㎡及以下减按 1%' if small else '140 ㎡以上减按 2%'}"
    return "家庭三套及以上住房，按当地法定税率计征"
