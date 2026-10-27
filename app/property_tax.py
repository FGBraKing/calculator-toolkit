"""Property tax (房产税) under 从价计征 and 从租计征."""

from __future__ import annotations

from decimal import Decimal, localcontext

from app import common
from app.calculator import InputError

PRECISION = 50
MODES = ("value", "rent")
RENT_TYPES = ("personal", "other")
VALUE_RATE = Decimal("0.012")
RENT_RATE_PERSONAL = Decimal("0.04")
RENT_RATE_OTHER = Decimal("0.12")
DEDUCTION_MIN = Decimal("10")
DEDUCTION_MAX = Decimal("30")


def calculate(payload: dict[str, str]) -> dict[str, object]:
    mode = payload.get("mode", "value")
    if mode not in MODES:
        raise InputError("mode", "计税方式无效")

    with localcontext() as ctx:
        ctx.prec = PRECISION
        if mode == "value":
            original = common.amount(
                payload.get("original_value"),
                "original_value",
                "房产原值",
                allow_zero=False,
                maximum=Decimal("1e12"),
            )
            deduction = common.amount(
                payload.get("deduction"), "deduction", "扣除比例", maximum=Decimal("30")
            )
            if not DEDUCTION_MIN <= deduction <= DEDUCTION_MAX:
                raise InputError("deduction", "扣除比例需在 10%–30% 之间")
            taxable = original * (1 - deduction / 100)
            rate = VALUE_RATE
            tax = taxable * rate
            facts = [
                f"从价计征：原值减除 {common.decimal_plain(deduction)}% 后的余值",
                f"适用税率 {common.percent_plain(rate)}%",
            ]
            formula = "\n".join(
                [
                    "从价计征：年应纳税额 = 房产原值 × (1 − 扣除比例) × 1.2%",
                    f"  = {common.money(original)} × (1 − {common.decimal_plain(deduction)}%)"
                    f" × 1.2% = {common.money(tax)}",
                    f"计税余值 = {common.money(taxable)}，月均 {common.money(tax / 12)}",
                ]
            )
            metrics = [
                ("房产余值", f"{common.money(taxable)} 元"),
                ("税率", "1.2%"),
                ("月均税额", f"{common.money(tax / 12)} 元"),
            ]
        else:
            rent = common.amount(
                payload.get("annual_rent"),
                "annual_rent",
                "年租金",
                allow_zero=False,
                maximum=Decimal("1e12"),
            )
            rent_type = payload.get("rent_type", "personal")
            if rent_type not in RENT_TYPES:
                raise InputError("rent_type", "出租类型无效")
            rate = RENT_RATE_PERSONAL if rent_type == "personal" else RENT_RATE_OTHER
            tax = rent * rate
            facts = [
                "从租计征：按租金收入计征",
                "个人出租住房减按 4%" if rent_type == "personal" else "其他出租按 12%",
            ]
            formula = "\n".join(
                [
                    "从租计征：年应纳税额 = 年租金 × 税率",
                    f"  = {common.money(rent)} × {common.percent_plain(rate)}%"
                    f" = {common.money(tax)}",
                    f"月均 {common.money(tax / 12)}（按租金实际收取月份分摊）",
                ]
            )
            metrics = [
                ("年租金", f"{common.money(rent)} 元"),
                ("税率", f"{common.percent_plain(rate)}%"),
                ("月均税额", f"{common.money(tax / 12)} 元"),
            ]

    return common.response(
        primary=common.money(tax),
        facts=facts,
        metrics=metrics,
        formula=formula,
        note="依据《房产税暂行条例》：从价计征按房产原值一次减除 10%–30% 后的余值、税率 1.2%；"
        "从租计征按租金收入、税率 12%，个人出租住房减按 4%。房产原值为房产原价（不含增值税），"
        "扣除比例由省级政府确定。个人自住住房目前不征房产税（上海、重庆试点另有规定，未计入）。",
    )
