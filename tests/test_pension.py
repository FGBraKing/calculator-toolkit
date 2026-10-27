from __future__ import annotations

import pytest

from app.calculator import InputError
from app.pension import ANNUITY_MONTHS, calculate_employee, calculate_resident, to_response


def employee(
    paid_years: str = "5",
    remaining_years: str = "30",
    retirement_age: str = "60",
    base: str = "10000",
    social: str = "8000",
    growth: str = "3",
    rate: str = "3",
    balance: str = "50000",
) -> dict[str, object]:
    return to_response(
        calculate_employee(
            paid_years_raw=paid_years,
            remaining_years_raw=remaining_years,
            retirement_age_raw=retirement_age,
            base_raw=base,
            social_raw=social,
            growth_raw=growth,
            rate_raw=rate,
            balance_raw=balance,
        )
    )


def resident(
    years: str = "15",
    contribution: str = "1000",
    subsidy: str = "60",
    rate: str = "3",
    base_pension: str = "143",
) -> dict[str, object]:
    return to_response(
        calculate_resident(
            years_raw=years,
            contribution_raw=contribution,
            subsidy_raw=subsidy,
            rate_raw=rate,
            base_pension_raw=base_pension,
        )
    )


@pytest.mark.parametrize(
    ("age", "months"),
    [(50, 195), (55, 170), (60, 139), (61, 132), (63, 117), (70, 56)],
)
def test_annuity_month_table(age: int, months: int) -> None:
    assert ANNUITY_MONTHS[age] == months
    data = employee(retirement_age=str(age))
    assert data["annuity_months"] == months


def test_employee_example() -> None:
    data = employee()

    assert data["track"] == "employee"
    assert data["years"] == 35
    assert data["eligible"] is True
    assert data["social_at_retirement"] == "19,418.10"
    assert data["index"] == "1.25"
    assert data["account_balance"] == "800,053.99"
    assert data["basic_pension"] == "7,645.88"
    assert data["account_pension"] == "5,755.78"
    assert data["monthly_total"] == "13,401.66"
    assert data["replacement_rate_percent"] == "55.2131"
    assert len(data["schedule"]) == 30
    assert data["schedule"][0] == {
        "year": 1,
        "base": "10,000.00",
        "contribution": "9,600.00",
        "balance": "61,100.00",
    }
    assert data["schedule_total"]["paid"] == "456,723.99"
    assert data["schedule_total"]["years"] == "30"


def test_retiring_now_uses_todays_social_average() -> None:
    data = employee(paid_years="15", remaining_years="0", balance="50000")

    assert data["social_at_retirement"] == "8,000.00"
    assert data["schedule"] == []
    assert data["basic_pension"] == "1,350.00"
    assert data["account_pension"] == "359.71"
    assert data["monthly_total"] == "1,709.71"
    assert data["replacement_rate_percent"] == "17.0971"


def test_zero_interest_account_only_sums_contributions() -> None:
    data = employee(paid_years="10", remaining_years="2", growth="0", rate="0", balance="0")

    assert data["account_balance"] == "19,200.00"
    assert data["account_pension"] == "138.13"
    assert data["basic_pension"] == "1,080.00"
    assert data["monthly_total"] == "1,218.13"
    assert data["schedule"][0]["balance"] == "9,600.00"


@pytest.mark.parametrize("base", ["4800", "24000"])
def test_contribution_base_bounds_are_inclusive(base: str) -> None:
    data = employee(base=base)

    assert data["index"] in ("0.6", "3")


@pytest.mark.parametrize("base", ["4700", "24100"])
def test_contribution_base_outside_bounds_is_rejected(base: str) -> None:
    with pytest.raises(InputError) as exc_info:
        employee(base=base)

    assert exc_info.value.field == "base"
    assert "60%–300%" in exc_info.value.message


@pytest.mark.parametrize("age", ["39", "71", "60.5"])
def test_retirement_age_range(age: str) -> None:
    with pytest.raises(InputError) as exc_info:
        employee(retirement_age=age)

    assert exc_info.value.field == "retirement_age"


def test_fifteen_years_are_required_to_receive_a_pension() -> None:
    short = employee(paid_years="3", remaining_years="5")
    exact = employee(paid_years="10", remaining_years="5")

    assert short["eligible"] is False
    assert "不足 15 年" in str(short["note"])
    assert short["monthly_total"] != "0.00"
    assert exact["eligible"] is True
    assert "不足 15 年" not in str(exact["note"])


@pytest.mark.parametrize("field_name", ["paid_years", "remaining_years"])
@pytest.mark.parametrize("raw", ["-1", "5.5", "abc", "51"])
def test_year_inputs_must_be_bounded_integers(field_name: str, raw: str) -> None:
    with pytest.raises(InputError) as exc_info:
        employee(**{field_name: raw})

    assert exc_info.value.field == field_name


def test_rate_out_of_range_is_rejected() -> None:
    with pytest.raises(InputError) as exc_info:
        employee(growth="25")

    assert exc_info.value.field == "growth"
    with pytest.raises(InputError) as exc_info:
        employee(rate="21")
    assert exc_info.value.field == "rate"


def test_employee_formula_shows_both_parts() -> None:
    formula = str(employee()["formula"])

    assert "基础养老金 = 退休时计发基数 × (1 + 平均缴费指数) ÷ 2 × 缴费年限 × 1%" in formula
    assert "= 19,418.10 × (1 + 1.25) ÷ 2 × 35 × 1% = 7,645.88" in formula
    assert "个人账户养老金 = 储存额 ÷ 计发月数 = 800,053.99 ÷ 139 = 5,755.78" in formula
    assert "月养老金 = 7,645.88 + 5,755.78 = 13,401.66" in formula


def test_resident_example() -> None:
    data = resident()

    assert data["track"] == "resident"
    assert data["years"] == 15
    assert data["eligible"] is True
    assert data["basic_pension"] == "143.00"
    assert data["account_balance"] == "19,714.85"
    assert data["account_pension"] == "141.83"
    assert data["monthly_total"] == "284.83"
    assert data["annuity_months"] == 139
    assert data["replacement_rate_percent"] is None
    assert len(data["schedule"]) == 15
    assert data["schedule_total"] == {
        "paid": "15,900.00",
        "balance": "19,714.85",
        "years": "15",
    }


def test_resident_zero_interest_sums_contributions_and_subsidies() -> None:
    data = resident(rate="0")

    assert data["account_balance"] == "15,900.00"
    assert data["account_pension"] == "114.39"
    assert data["monthly_total"] == "257.39"


def test_resident_years_must_be_positive_and_under_fifteen_is_flagged() -> None:
    with pytest.raises(InputError) as exc_info:
        resident(years="0")
    assert exc_info.value.field == "years"

    short = resident(years="10")
    assert short["eligible"] is False
    assert "不足 15 年" in str(short["note"])


def test_resident_formula_uses_the_local_base_pension() -> None:
    formula = str(resident()["formula"])

    assert "个人账户储存额 = 每年（缴费 1,000.00 + 补贴 60.00）" in formula
    assert "个人账户养老金 = 19,714.85 ÷ 139 = 141.83" in formula
    assert "月养老金 = 当地基础养老金 143.00 + 141.83 = 284.83" in formula


def test_resident_base_pension_is_parameterized() -> None:
    shanghai = resident(base_pension="1400")

    assert shanghai["basic_pension"] == "1,400.00"
    assert shanghai["monthly_total"] == "1,541.83"
