from __future__ import annotations

from decimal import Decimal

import pytest

from app.calculator import InputError
from app.tax import calculate, to_response

SPECIAL_KEYS = (
    "child_education",
    "infant_care",
    "continuing_education",
    "mortgage_interest",
    "housing_rent",
    "elderly_support",
)


def response(
    income: str = "20000",
    basis: str = "month",
    bonus: str = "0",
    bonus_mode: str = "separate",
    social: str = "0",
    serious_illness: str = "0",
    pension: str = "0",
    **special: str,
) -> dict[str, object]:
    values = {key: "0" for key in SPECIAL_KEYS}
    values.update(special)
    return to_response(
        calculate(
            income_raw=income,
            income_basis=basis,
            bonus_raw=bonus,
            bonus_mode=bonus_mode,
            social_raw=social,
            special_raw=values,
            serious_illness_raw=serious_illness,
            pension_raw=pension,
        )
    )


def amount(text: object) -> Decimal:
    return Decimal(str(text).replace(",", ""))


def test_income_below_the_basic_deduction_pays_nothing() -> None:
    data = response(income="5000")

    assert data["taxable_income"] == "0.00"
    assert data["total_tax"] == "0.00"
    assert data["net_income"] == "60,000.00"
    assert data["marginal_rate_percent"] == "0.0000"
    assert data["effective_rate_percent"] == "0.0000"


def test_zero_income_and_zero_deductions() -> None:
    data = response(income="0")

    assert data["taxable_income"] == "0.00"
    assert data["net_income"] == "0.00"
    assert [row["tax"] for row in data["schedule"]] == ["0.00"] * 12


@pytest.mark.parametrize(
    ("taxable", "expected"),
    [
        ("36000", "1,080.00"),
        ("36001", "1,080.10"),
        ("144000", "11,880.00"),
        ("144001", "11,880.20"),
        ("300000", "43,080.00"),
        ("300001", "43,080.25"),
        ("420000", "73,080.00"),
        ("420001", "73,080.30"),
        ("660000", "145,080.00"),
        ("660001", "145,080.35"),
        ("960000", "250,080.00"),
        ("960001", "250,080.45"),
    ],
)
def test_bracket_boundaries_are_continuous(taxable: str, expected: str) -> None:
    income = str(Decimal(taxable) + Decimal("60000"))
    data = response(income=income, basis="year")

    assert data["taxable_income"] == f"{Decimal(taxable):,.2f}"
    assert data["comprehensive_tax"] == expected


def test_bonus_separate_uses_the_monthly_bracket() -> None:
    assert response(bonus="12000")["bonus_tax"] == "360.00"
    assert response(bonus="36000")["bonus_tax"] == "1,080.00"


def test_bonus_separate_cliff_just_above_the_threshold() -> None:
    data = response(income="5000", bonus="36001")

    assert data["bonus_tax"] == "3,390.10"
    assert data["total_tax"] == "3,390.10"
    assert data["bonus_comparison"]["better"] == "combined"
    assert data["bonus_comparison"]["saving"] == "2,310.00"


def test_bonus_combined_uses_the_annual_table() -> None:
    data = response(income="60000", basis="year", bonus="36001", bonus_mode="combined")

    assert data["taxable_income"] == "0.00"
    assert data["total_tax"] == "1,080.10"
    assert data["bonus_tax"] == "1,080.10"
    assert data["bonus_comparison"]["combined_tax"] == "1,080.10"
    assert "并入综合所得：应纳税所得额 36,001.00" in str(data["formula"])


def test_full_example_with_bonus_and_pension() -> None:
    data = response(
        income="20000",
        bonus="60000",
        social="3000",
        child_education="2000",
        pension="12000",
    )

    assert data["annual_income"] == "240,000.00"
    assert data["deductions"] == {
        "basic": "60,000.00",
        "social": "36,000.00",
        "special": "24,000.00",
        "annual": "12,000.00",
        "total": "132,000.00",
    }
    assert data["taxable_income"] == "108,000.00"
    assert data["comprehensive_tax"] == "8,280.00"
    assert data["bonus_tax"] == "5,790.00"
    assert data["total_tax"] == "14,070.00"
    assert data["net_income"] == "249,930.00"
    assert data["effective_rate_percent"] == "4.6900"
    assert data["marginal_rate_percent"] == "10.0000"
    assert data["bonus_comparison"]["better"] == "separate"
    assert data["bonus_comparison"]["saving"] == "2,610.00"
    assert "单独计税更省 2,610.00 元" in data["bonus_comparison"]["note"]


def test_combined_mode_reports_the_bonus_share() -> None:
    data = response(
        income="20000",
        bonus="60000",
        social="3000",
        child_education="2000",
        bonus_mode="combined",
    )

    assert data["total_tax"] == "19,080.00"
    assert data["bonus_tax"] == "9,600.00"
    assert data["marginal_rate_percent"] == "20.0000"


def test_annual_basis_matches_monthly_basis() -> None:
    monthly = response(income="20000", basis="month", social="3000")
    annual = response(income="240000", basis="year", social="3000")

    for key in ("annual_income", "taxable_income", "total_tax", "net_income"):
        assert monthly[key] == annual[key]
    assert monthly["schedule"] == annual["schedule"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("continuing_education", "401"),
        ("mortgage_interest", "1001"),
        ("housing_rent", "1501"),
        ("elderly_support", "3001"),
    ],
)
def test_special_deductions_respect_their_monthly_caps(field: str, value: str) -> None:
    with pytest.raises(InputError) as exc_info:
        response(**{field: value})

    assert exc_info.value.field == field
    assert "每月最多" in exc_info.value.message


def test_mortgage_and_rent_cannot_both_be_claimed() -> None:
    with pytest.raises(InputError) as exc_info:
        response(mortgage_interest="1000", housing_rent="1500")

    assert exc_info.value.field == "housing_rent"
    assert "不能同时享受" in exc_info.value.message


@pytest.mark.parametrize(
    ("paid", "deductible"),
    [("10000", "0.00"), ("15000", "0.00"), ("20000", "5,000.00"), ("200000", "80,000.00")],
)
def test_serious_illness_threshold_and_cap(paid: str, deductible: str) -> None:
    data = response(serious_illness=paid)

    assert data["deductions"]["annual"] == deductible


def test_pension_is_capped_at_twelve_thousand() -> None:
    assert response(pension="12000")["deductions"]["annual"] == "12,000.00"
    assert response(pension="20000")["deductions"]["annual"] == "12,000.00"


def test_social_insurance_cannot_exceed_income() -> None:
    with pytest.raises(InputError) as exc_info:
        response(income="5000", social="6000")

    assert exc_info.value.field == "social"


@pytest.mark.parametrize("field_value", ["-1", "abc", "1/2"])
def test_negative_or_malformed_amounts_are_rejected(field_value: str) -> None:
    with pytest.raises(InputError) as exc_info:
        response(income=field_value)

    assert exc_info.value.field == "income"


def test_withholding_schedule_reconciles_with_the_annual_tax() -> None:
    data = response(income="20000", social="3000", child_education="2000")
    rows = data["schedule"]

    assert len(rows) == 12
    assert rows[0]["tax"] == "300.00"
    assert rows[3]["tax"] == "580.00"
    assert rows[-1]["cumulative_tax"] == "9,480.00"
    assert data["total_tax"] == "9,480.00"
    assert sum(amount(row["tax"]) for row in rows) == amount(data["schedule_total"]["tax"])
    cumulative = [amount(row["cumulative_tax"]) for row in rows]
    assert cumulative == sorted(cumulative)


def test_annual_only_deductions_stay_out_of_the_withholding_schedule() -> None:
    without_extra = response(income="20000", social="3000")
    with_pension = response(income="20000", social="3000", pension="12000")

    assert without_extra["total_tax"] == "11,880.00"
    assert with_pension["total_tax"] == "10,680.00"
    assert with_pension["schedule_total"]["tax"] == "11,880.00"
    assert "汇算" in with_pension["note"]


def test_formula_shows_the_deduction_chain_and_bonus() -> None:
    data = response(income="20000", bonus="60000", social="3000", child_education="2000")
    formula = str(data["formula"])

    assert "综合所得应纳税所得额 = 年收入 − 基本减除" in formula
    assert "= 240,000.00 − 60,000.00 − 36,000.00 − 24,000.00 − 0.00 = 120,000.00" in formula
    assert "年终奖 60,000.00 单独计税：÷ 12 = 5,000.00 → 适用 10%" in formula
    assert "合计应纳税额 = 15,270.00" in formula
