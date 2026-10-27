from __future__ import annotations

from datetime import date
from decimal import Decimal

import pytest

from app import (
    age,
    childcare,
    deed_tax,
    deposit,
    fund_loan,
    maternity,
    mortgage,
    prepayment,
    property_tax,
    retirement,
    salary,
)
from app import resale as resale_module
from app.calculator import InputError


def amount(text: object) -> Decimal:
    return Decimal(str(text).replace(",", ""))


# --- 存款利息 -------------------------------------------------------------


def test_deposit_simple_interest() -> None:
    data = deposit.calculate(
        {"principal": "100000", "rate": "2", "term": "1", "unit": "year", "method": "simple"}
    )

    assert data["primary"] == "2,000.00"
    assert data["metrics"][0]["value"] == "100,000.00 元"
    assert data["metrics"][2]["value"] == "102,000.00 元"
    assert "单利" in data["facts"][1]


def test_deposit_compound_interest() -> None:
    data = deposit.calculate(
        {"principal": "100000", "rate": "2", "term": "3", "unit": "year", "method": "compound"}
    )

    assert data["primary"] == "6,120.80"
    assert data["metrics"][2]["value"] == "106,120.80 元"
    assert "复利" in data["facts"][1]


def test_deposit_months_use_fraction_of_a_year() -> None:
    simple = deposit.calculate(
        {"principal": "100000", "rate": "2", "term": "6", "unit": "month", "method": "simple"}
    )
    compound = deposit.calculate(
        {"principal": "100000", "rate": "2", "term": "6", "unit": "month", "method": "compound"}
    )

    assert simple["primary"] == "1,000.00"
    assert compound["primary"] == "995.05"
    assert simple["facts"][0] == "存期 0.5 年"


def test_deposit_rejects_zero_principal_and_long_terms() -> None:
    with pytest.raises(InputError) as exc_info:
        deposit.calculate({"principal": "0", "rate": "2", "term": "1", "unit": "year"})
    assert exc_info.value.field == "principal"

    with pytest.raises(InputError) as exc_info:
        deposit.calculate({"principal": "1000", "rate": "2", "term": "101", "unit": "year"})
    assert exc_info.value.field == "term"


def test_deposit_rejects_unknown_units() -> None:
    with pytest.raises(InputError) as exc_info:
        deposit.calculate({"principal": "1000", "rate": "2", "term": "1", "unit": "week"})
    assert exc_info.value.field == "unit"


# --- 房贷 -----------------------------------------------------------------


def test_mortgage_equal_installment() -> None:
    data = mortgage.calculate(
        {"amount": "1000000", "years": "30", "rate": "3.1", "method": "equal_installment"}
    )

    assert data["primary"] == "4,270.16"
    assert data["metrics"][1]["value"] == "1,537,259.04 元"
    assert data["metrics"][2]["value"] == "537,259.04 元"
    rows = data["schedule"]["rows"]
    assert len(rows) == 360
    assert rows[0] == ["1", "4,270.16", "1,686.83", "2,583.33", "998,313.17"]
    assert rows[-1][4] == "0.00"
    assert sum(amount(row[2]) for row in rows) == Decimal("1000000.00")
    assert sum(amount(row[3]) for row in rows) == Decimal("537259.04")


def test_mortgage_equal_principal() -> None:
    data = mortgage.calculate(
        {"amount": "1000000", "years": "30", "rate": "3.1", "method": "equal_principal"}
    )

    assert data["primary"] == "5,361.11"
    rows = data["schedule"]["rows"]
    assert rows[0][1] == "5,361.11"
    assert rows[-1][1] == "2,784.16"
    assert sum(amount(row[2]) for row in rows) == Decimal("1000000.00")
    assert sum(amount(row[3]) for row in rows) == amount(data["metrics"][2]["value"].split()[0])


def test_mortgage_zero_rate_is_a_straight_split() -> None:
    data = mortgage.calculate(
        {"amount": "120000", "years": "10", "rate": "0", "method": "equal_installment"}
    )

    assert data["primary"] == "1,000.00"
    assert data["metrics"][2]["value"] == "0.00 元"


@pytest.mark.parametrize("years", ["0", "41", "30.5"])
def test_mortgage_years_are_bounded_integers(years: str) -> None:
    with pytest.raises(InputError) as exc_info:
        mortgage.calculate({"amount": "1000000", "years": years, "rate": "3.1"})

    assert exc_info.value.field == "years"


# --- 退休年龄 -------------------------------------------------------------


@pytest.mark.parametrize(
    ("birth_year", "birth_month", "kind", "age", "months", "retire"),
    [
        ("1985", "6", "male", "63 岁", 36, "2048 年 6 月"),
        ("1965", "1", "male", "60 岁 1 个月", 1, "2025 年 2 月"),
        ("1964", "12", "male", "60 岁", 0, "2024 年 12 月"),
        ("1970", "1", "female55", "55 岁 1 个月", 1, "2025 年 2 月"),
        ("1981", "12", "female55", "58 岁", 36, "2039 年 12 月"),
        ("1975", "1", "female50", "50 岁 1 个月", 1, "2025 年 2 月"),
        ("1980", "3", "female50", "52 岁 8 个月", 32, "2032 年 11 月"),
        ("1984", "12", "female50", "55 岁", 60, "2039 年 12 月"),
    ],
)
def test_retirement_schedule(
    birth_year: str,
    birth_month: str,
    kind: str,
    age: str,
    months: int,
    retire: str,
) -> None:
    data = retirement.calculate(
        {"birth_year": birth_year, "birth_month": birth_month, "type": kind}
    )

    assert data["primary"] == age
    assert data["facts"][0] == f"退休时间 {retire}"
    assert next(m for m in data["metrics"] if m["label"] == "延迟月数")["value"] == f"{months} 个月"


def test_retirement_flexible_window_never_below_the_original_age() -> None:
    data = retirement.calculate({"birth_year": "1965", "birth_month": "3", "type": "male"})

    assert data["facts"][1] == "弹性区间 2025 年 3 月 – 2028 年 4 月"


@pytest.mark.parametrize("payload", [{"birth_year": "1930"}, {"birth_month": "13"}])
def test_retirement_bounds(payload: dict[str, str]) -> None:
    with pytest.raises(InputError):
        retirement.calculate({"birth_year": "1985", "birth_month": "6", **payload})


# --- 产假 -----------------------------------------------------------------


def test_maternity_base_leave() -> None:
    data = maternity.calculate(
        {"due": "2026-12-01", "type": "normal", "children": "1", "reward": "30"}
    )

    assert data["primary"] == "128"
    assert data["facts"][0] == "产假 2026-11-16 至 2027-03-23"
    assert data["metrics"][0]["value"] == "98 天"


def test_maternity_difficult_and_multiple_add_days() -> None:
    difficult = maternity.calculate(
        {"due": "2026-12-01", "type": "difficult", "children": "1", "reward": "0"}
    )
    multiple = maternity.calculate(
        {"due": "2026-12-01", "type": "normal", "children": "2", "reward": "0"}
    )
    both = maternity.calculate(
        {"due": "2026-12-01", "type": "difficult", "children": "3", "reward": "60"}
    )

    assert difficult["primary"] == "113"
    assert multiple["primary"] == "113"
    assert both["primary"] == "203"
    assert both["facts"][0].startswith("产假 2026-11-16")


def test_maternity_rejects_bad_dates() -> None:
    with pytest.raises(InputError) as exc_info:
        maternity.calculate({"due": "2026-02-30", "type": "normal", "children": "1", "reward": "0"})

    assert exc_info.value.field == "due"


# --- 育儿补贴 -------------------------------------------------------------


def test_childcare_full_three_years() -> None:
    data = childcare.calculate(
        {"birth_year": "2025", "birth_month": "1", "standard": "3600"},
        as_of=date(2026, 10, 27),
    )

    assert data["primary"] == "10,800.00"
    assert data["metrics"][0]["value"] == "36 个月"
    assert data["facts"][0] == "可领月份 2025 年 1 月 – 2027 年 12 月"
    assert data["facts"][1] == "剩余 15 个月（4,500.00 元）"


def test_childcare_born_before_the_programme_is_prorated() -> None:
    data = childcare.calculate(
        {"birth_year": "2024", "birth_month": "1", "standard": "3600"},
        as_of=date(2026, 10, 27),
    )

    assert data["metrics"][0]["value"] == "24 个月"
    assert data["primary"] == "7,200.00"


def test_childcare_over_three_years_pays_nothing() -> None:
    data = childcare.calculate(
        {"birth_year": "2020", "birth_month": "1", "standard": "3600"},
        as_of=date(2026, 10, 27),
    )

    assert data["primary"] == "0.00"
    assert data["facts"] == ["已超过 3 周岁，不再符合补贴条件"]


def test_childcare_uses_the_local_standard() -> None:
    data = childcare.calculate(
        {"birth_year": "2025", "birth_month": "1", "standard": "5000"},
        as_of=date(2026, 1, 1),
    )

    assert data["primary"] == "15,000.00"
    assert data["metrics"][1]["value"] == "416.67 元"


# --- 契税 -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("payload", "tax"),
    [
        ({"homes": "first", "area": "90"}, "20,000.00"),
        ({"homes": "first", "area": "140"}, "20,000.00"),
        ({"homes": "first", "area": "141"}, "30,000.00"),
        ({"homes": "second", "area": "90"}, "20,000.00"),
        ({"homes": "second", "area": "141"}, "40,000.00"),
        ({"homes": "third", "area": "90"}, "60,000.00"),
    ],
)
def test_deed_tax_housing_brackets(payload: dict[str, str], tax: str) -> None:
    data = deed_tax.calculate(
        {"type": "housing", "price": "2000000", "statutory_rate": "3", **payload}
    )

    assert data["primary"] == tax


def test_deed_tax_non_housing_uses_the_statutory_rate() -> None:
    data = deed_tax.calculate({"type": "non_housing", "price": "2000000", "statutory_rate": "4"})

    assert data["primary"] == "80,000.00"
    assert data["facts"][1] == "适用当地法定税率 4%"


def test_deed_tax_requires_a_statutory_rate_between_three_and_five() -> None:
    with pytest.raises(InputError) as exc_info:
        deed_tax.calculate(
            {"type": "housing", "price": "2000000", "area": "90", "statutory_rate": "2"}
        )
    assert exc_info.value.field == "statutory_rate"


def test_deed_tax_housing_needs_an_area() -> None:
    with pytest.raises(InputError) as exc_info:
        deed_tax.calculate({"type": "housing", "price": "2000000", "statutory_rate": "3"})

    assert exc_info.value.field == "area"


# --- 房产税 ---------------------------------------------------------------


def test_property_tax_from_value() -> None:
    data = property_tax.calculate({"mode": "value", "original_value": "1000000", "deduction": "30"})

    assert data["primary"] == "8,400.00"
    assert data["metrics"][0]["value"] == "700,000.00 元"
    assert data["metrics"][2]["value"] == "700.00 元"


def test_property_tax_from_rent() -> None:
    personal = property_tax.calculate(
        {"mode": "rent", "annual_rent": "60000", "rent_type": "personal"}
    )
    other = property_tax.calculate({"mode": "rent", "annual_rent": "60000", "rent_type": "other"})

    assert personal["primary"] == "2,400.00"
    assert other["primary"] == "7,200.00"


def test_property_tax_deduction_bounds() -> None:
    with pytest.raises(InputError) as exc_info:
        property_tax.calculate({"mode": "value", "original_value": "1000000", "deduction": "5"})
    assert exc_info.value.field == "deduction"

    with pytest.raises(InputError) as exc_info:
        property_tax.calculate({"mode": "value", "original_value": "1000000", "deduction": "40"})
    assert exc_info.value.field == "deduction"


# --- 出生时长 -------------------------------------------------------------


@pytest.mark.parametrize(
    ("month", "day", "sign"),
    [
        (1, 19, "摩羯座"),
        (1, 20, "水瓶座"),
        (2, 18, "水瓶座"),
        (2, 19, "双鱼座"),
        (3, 21, "白羊座"),
        (6, 22, "巨蟹座"),
        (9, 23, "天秤座"),
        (11, 23, "射手座"),
        (12, 21, "射手座"),
        (12, 22, "摩羯座"),
    ],
)
def test_constellation_boundaries(month: int, day: int, sign: str) -> None:
    assert age.constellation(month, day) == sign


def test_age_counts_days_since_birth() -> None:
    data = age.calculate({"birth": "1995-06-15"}, as_of=date(2026, 10, 28))

    assert data["primary"] == "11,458"
    assert data["primary_unit"] == "天"
    assert data["facts"][0] == "出生于 1995-06-15"
    assert data["facts"][1] == "下次生日 2027-06-15（230 天后）"
    assert data["metrics"][0]["value"] == "31 岁"
    assert data["metrics"][1]["value"] == "双子座"
    assert data["metrics"][2]["value"] == "猪"


def test_age_handles_a_leap_day_birthday() -> None:
    data = age.calculate({"birth": "2000-02-29"}, as_of=date(2026, 10, 28))

    assert data["facts"][1].startswith("下次生日 2027-03-01")
    assert data["metrics"][2]["value"] == "龙"


@pytest.mark.parametrize(
    ("birth", "animal"),
    [
        ("1990-01-26", "蛇"),
        ("1990-01-27", "马"),
        ("2024-02-09", "兔"),
        ("2024-02-10", "龙"),
        ("1995-06-15", "猪"),
    ],
)
def test_zodiac_switches_at_spring_festival(birth: str, animal: str) -> None:
    data = age.calculate({"birth": birth}, as_of=date(2026, 10, 28))

    assert data["metrics"][2]["value"] == animal


def test_zodiac_rejects_dates_before_1901() -> None:
    with pytest.raises(InputError) as exc_info:
        age.calculate({"birth": "1900-06-01"}, as_of=date(2026, 10, 28))

    assert exc_info.value.field == "birth"


def test_age_rejects_future_births() -> None:
    with pytest.raises(InputError) as exc_info:
        age.calculate({"birth": "2027-01-01"}, as_of=date(2026, 10, 28))

    assert exc_info.value.field == "birth"


# --- 税后工资 -------------------------------------------------------------


def test_net_salary_example() -> None:
    data = salary.calculate(
        {
            "salary": "15000",
            "base": "15000",
            "social_rate": "10.5",
            "fund_rate": "7",
            "deduction": "0",
        }
    )

    assert data["primary"] == "11,847.50"
    assert data["facts"][1] == "社保 10.5% + 公积金 7% = 每月 2,625.00 元"
    assert data["facts"][2] == "首月到手 12,153.75 元 · 末月 11,637.50 元"
    assert data["metrics"][0]["value"] == "2,625.00 元"
    assert data["metrics"][1]["value"] == "6,330.00 元"
    assert data["metrics"][2]["value"] == "142,170.00 元"

    rows = data["schedule"]["rows"]
    assert len(rows) == 12
    assert rows[0] == ["1", "15,000.00", "7,625.00", "221.25", "12,153.75"]
    assert rows[-1][4] == "11,637.50"
    assert sum(amount(row[3]) for row in rows) == Decimal("6330.00")


def test_net_salary_with_additional_deductions() -> None:
    data = salary.calculate(
        {
            "salary": "15000",
            "base": "15000",
            "social_rate": "10.5",
            "fund_rate": "7",
            "deduction": "2000",
        }
    )

    assert data["metrics"][1]["value"] == "3,930.00 元"
    assert data["primary"] == "12,047.50"


def test_net_salary_base_differs_from_salary() -> None:
    data = salary.calculate(
        {
            "salary": "30000",
            "base": "10000",
            "social_rate": "10.5",
            "fund_rate": "7",
            "deduction": "0",
        }
    )

    assert data["facts"][0] == "缴费基数 10,000.00 元"
    assert data["metrics"][0]["value"] == "1,750.00 元"


def test_net_salary_rejects_bad_rates() -> None:
    payload = {
        "salary": "15000",
        "base": "15000",
        "social_rate": "10.5",
        "fund_rate": "7",
        "deduction": "0",
    }
    with pytest.raises(InputError) as exc_info:
        salary.calculate({**payload, "fund_rate": "13"})
    assert exc_info.value.field == "fund_rate"

    with pytest.raises(InputError) as exc_info:
        salary.calculate({**payload, "salary": "0"})
    assert exc_info.value.field == "salary"


# --- 公积金组合贷 ---------------------------------------------------------


def test_fund_loan_combined_payment() -> None:
    data = fund_loan.calculate(
        {
            "total": "1000000",
            "fund": "600000",
            "years": "30",
            "fund_rate": "2.6",
            "commercial_rate": "3.1",
            "method": "equal_installment",
        }
    )

    assert data["primary"] == "4,110.10"
    assert data["facts"][0] == "公积金 600,000.00 元 · 商贷 400,000.00 元"
    assert data["metrics"][0]["label"] == "合计利息"


def test_fund_loan_without_fund_part_matches_the_mortgage() -> None:
    data = fund_loan.calculate(
        {
            "total": "1000000",
            "fund": "0",
            "years": "30",
            "fund_rate": "2.6",
            "commercial_rate": "3.1",
            "method": "equal_installment",
        }
    )

    assert data["primary"] == "4,270.16"


def test_fund_loan_equal_principal_first_month() -> None:
    data = fund_loan.calculate(
        {
            "total": "1000000",
            "fund": "600000",
            "years": "30",
            "fund_rate": "2.6",
            "commercial_rate": "3.1",
            "method": "equal_principal",
        }
    )

    assert data["primary"] == "5,111.11"
    assert data["facts"][2] == "首月 5,111.11 元 · 末月 2,784.26 元"


def test_fund_loan_cannot_exceed_the_total() -> None:
    with pytest.raises(InputError) as exc_info:
        fund_loan.calculate(
            {
                "total": "500000",
                "fund": "600000",
                "years": "30",
                "fund_rate": "2.6",
                "commercial_rate": "3.1",
            }
        )

    assert exc_info.value.field == "fund"


# --- 提前还款 -------------------------------------------------------------


def test_prepayment_compares_both_options() -> None:
    data = prepayment.calculate(
        {
            "principal": "800000",
            "rate": "3.1",
            "months": "300",
            "extra": "200000",
            "penalty": "0",
            "method": "equal_installment",
        }
    )

    assert data["primary"] == "180,974.98"
    rows = data["schedule"]["rows"]
    assert rows[0][0] == "缩短年限"
    assert rows[0][2] == "201 期"
    assert rows[1][0] == "减少月供"
    assert rows[1][2] == "300 期"
    assert data["schedule"]["totals"][0]["label"] == "更省的方案"
    assert "缩短年限" in data["schedule"]["totals"][0]["value"]


def test_prepayment_penalty_reduces_the_net_saving() -> None:
    data = prepayment.calculate(
        {
            "principal": "800000",
            "rate": "3.1",
            "months": "300",
            "extra": "200000",
            "penalty": "5000",
            "method": "equal_installment",
        }
    )

    assert data["primary"] == "175,974.98"


def test_prepayment_equal_principal() -> None:
    data = prepayment.calculate(
        {
            "principal": "800000",
            "rate": "3.1",
            "months": "300",
            "extra": "200000",
            "penalty": "0",
            "method": "equal_principal",
        }
    )

    assert data["primary"] == "135,883.33"


def test_prepayment_must_leave_a_balance() -> None:
    with pytest.raises(InputError) as exc_info:
        prepayment.calculate(
            {
                "principal": "800000",
                "rate": "3.1",
                "months": "300",
                "extra": "800000",
                "penalty": "0",
            }
        )

    assert exc_info.value.field == "extra"


# --- 二手房税费 -----------------------------------------------------------


def resale(payload: dict[str, str]) -> dict[str, object]:
    return resale_module.calculate(
        {
            "price": "2000000",
            "area": "90",
            "homes": "first",
            "paid_two": "yes",
            "only_home": "no",
            "original": "1000000",
            "tax_mode": "deemed",
            "statutory": "3",
            "surcharge": "12",
            **payload,
        }
    )


def test_resale_default_case() -> None:
    data = resale({})

    assert data["primary"] == "40,000.00"
    assert data["metrics"][0]["value"] == "20,000.00 元"
    assert data["metrics"][1]["value"] == "20,000.00 元"
    assert data["metrics"][2]["value"] == "2%"
    rows = data["schedule"]["rows"]
    assert rows[1] == ["增值税", "卖方", "满二免征", "0.00"]


def test_resale_vat_when_not_two_years() -> None:
    data = resale({"paid_two": "no"})

    assert data["primary"] == "146,666.67"
    rows = data["schedule"]["rows"]
    assert rows[1][3] == "95,238.10"
    assert rows[2][3] == "11,428.57"


def test_resale_only_home_exempts_income_tax() -> None:
    data = resale({"only_home": "yes"})

    assert data["primary"] == "20,000.00"


def test_resale_difference_tax_mode() -> None:
    data = resale({"tax_mode": "difference"})

    assert data["primary"] == "220,000.00"


def test_resale_requires_original_value_for_difference_mode() -> None:
    with pytest.raises(InputError) as exc_info:
        resale({"tax_mode": "difference", "original": "0"})

    assert exc_info.value.field == "original"


def test_resale_only_home_needs_two_years() -> None:
    with pytest.raises(InputError) as exc_info:
        resale({"only_home": "yes", "paid_two": "no"})

    assert exc_info.value.field == "only_home"


def test_resale_deed_tax_tiers() -> None:
    assert resale({"homes": "third"})["primary"] == "80,000.00"
    assert resale({"area": "141"})["primary"] == "50,000.00"
