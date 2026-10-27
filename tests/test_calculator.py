from __future__ import annotations

from decimal import Decimal, localcontext

import pytest

from app.calculator import InputError, analyze, to_response

SAMPLE = ("100000", "3650", "12", "1", "month")
ALL_MODES = (
    "equal_installment",
    "equal_principal",
    "interest_only",
    "flat_rate",
    "simple_bullet",
)


def response(
    mode: str,
    inputs: tuple[str, str | None, str, str, str] = SAMPLE,
    *,
    payment: str | None = None,
    concession: str = "none",
    concession_value: str | None = None,
) -> dict[str, object]:
    principal, interest, periods, period_value, period_unit = inputs
    return to_response(
        analyze(
            principal,
            interest,
            periods,
            period_value,
            period_unit,
            mode,
            payment_raw=payment,
            concession=concession,
            concession_value_raw=concession_value,
        )
    )


def amount(text: object) -> Decimal:
    return Decimal(str(text).replace(",", ""))


@pytest.mark.parametrize(
    ("mode", "contract", "period", "irr", "relation", "fragment"),
    [
        ("equal_installment", "6.6707", "0.5559", "6.6707", "equal", "解 P = A"),
        ("equal_principal", "6.7385", "0.5615", "6.7385", "equal", "期数 + 1"),
        ("interest_only", "3.6500", "0.3042", "3.6500", "equal", "本金 × 期数"),
        ("flat_rate", "3.6500", "0.3042", "6.6707", "higher", "期费率"),
        ("simple_bullet", "3.6500", "0.3042", "3.5903", "lower", "到期本息合计"),
    ],
)
def test_sample_table_for_every_mode(
    mode: str,
    contract: str,
    period: str,
    irr: str,
    relation: str,
    fragment: str,
) -> None:
    data = response(mode)

    assert data["contract_annual_rate_percent"] == contract
    assert data["contract_period_rate_percent"] == period
    assert data["irr_annual_rate_percent"] == irr
    assert data["irr_relation"] == relation
    assert data["total_years"] == "1"
    assert data["period_label"] == "1 月"
    assert fragment in str(data["formula"])
    assert f"≈ {contract}%" in str(data["formula"])


def test_interest_only_raw_rates() -> None:
    data = response("interest_only")

    assert data["contract_annual_rate"] == "0.0365000000"
    assert data["contract_period_rate"] == "0.0030416667"
    assert data["irr_annual_rate"] == "0.0365000000"


def test_flat_rate_and_equal_installment_share_the_same_irr() -> None:
    equal_installment = response("equal_installment")
    flat = response("flat_rate")

    assert equal_installment["contract_annual_rate_percent"] == "6.6707"
    assert flat["contract_annual_rate_percent"] == "3.6500"
    assert flat["irr_annual_rate_percent"] == equal_installment["irr_annual_rate_percent"]
    assert flat["irr_annual_rate_percent"] == "6.6707"


def test_equal_installment_formula_shows_level_payment() -> None:
    data = response("equal_installment")

    assert "8,637.50" in str(data["formula"])
    assert "1 − (1 + r)^-n" in str(data["formula"])
    assert "n = 12" in str(data["formula"])
    assert "≈ 6.6707%" in str(data["formula"])


@pytest.mark.parametrize("mode", ALL_MODES)
def test_schedule_reconciles_to_contract_totals(mode: str) -> None:
    data = response(mode)
    rows = data["schedule"]
    assert isinstance(rows, list)
    totals = data["schedule_total"]
    assert isinstance(totals, dict)

    assert len(rows) == 12
    assert rows[0]["period"] == 1
    assert rows[-1]["period"] == 12

    total_principal = amount(totals["principal"])
    total_interest = amount(totals["interest"])
    total_payment = amount(totals["payment"])
    assert total_principal == Decimal("100000.00")
    assert total_interest == Decimal("3650.00")
    assert total_payment == Decimal("103650.00")
    assert totals["payment"] == "103,650.00"

    principal_sum = Decimal(0)
    interest_sum = Decimal(0)
    payment_sum = Decimal(0)
    previous_balance = total_principal
    for row in rows:
        row_principal = amount(row["principal"])
        row_interest = amount(row["interest"])
        row_payment = amount(row["payment"])
        row_balance = amount(row["balance"])

        assert row_principal >= 0
        assert row_interest >= 0
        assert row_payment == row_principal + row_interest
        assert row_balance <= previous_balance
        previous_balance = row_balance

        principal_sum += row_principal
        interest_sum += row_interest
        payment_sum += row_payment

    assert principal_sum == total_principal
    assert interest_sum == total_interest
    assert payment_sum == total_payment
    assert amount(rows[-1]["balance"]) == 0


def test_interest_only_schedule_shape() -> None:
    data = response("interest_only")
    rows = data["schedule"]
    assert isinstance(rows, list)

    for row in rows[:-1]:
        assert row["principal"] == "0.00"
        assert row["interest"] == "304.17"
        assert row["payment"] == "304.17"
        assert row["balance"] == "100,000.00"

    last = rows[-1]
    assert last["principal"] == "100,000.00"
    assert last["interest"] == "304.13"
    assert last["payment"] == "100,304.13"
    assert last["balance"] == "0.00"


def test_flat_rate_schedule_has_constant_payment_and_fixed_interest() -> None:
    data = response("flat_rate")
    rows = data["schedule"]
    assert isinstance(rows, list)

    for row in rows[:-1]:
        assert row["principal"] == "8,333.33"
        assert row["interest"] == "304.17"
        assert row["payment"] == "8,637.50"

    last = rows[-1]
    assert last["principal"] == "8,333.37"
    assert last["interest"] == "304.13"
    assert last["payment"] == "8,637.50"


def test_equal_installment_schedule_starts_interest_heavy() -> None:
    data = response("equal_installment")
    rows = data["schedule"]
    assert isinstance(rows, list)

    first = rows[0]
    assert first["principal"] == "8,081.61"
    assert first["interest"] == "555.89"
    assert first["payment"] == "8,637.50"
    assert amount(rows[-1]["balance"]) == 0


def test_schedule_handles_tiny_amounts_without_negative_cents() -> None:
    data = response("interest_only", ("100000", "0.07", "12", "1", "month"))
    rows = data["schedule"]
    totals = data["schedule_total"]
    assert isinstance(rows, list)
    assert isinstance(totals, dict)

    principal_sum = sum((amount(row["principal"]) for row in rows), Decimal(0))
    interest_sum = sum((amount(row["interest"]) for row in rows), Decimal(0))
    assert principal_sum == Decimal("100000.00")
    assert interest_sum == Decimal("0.07")
    assert totals["interest"] == "0.07"
    assert amount(rows[-1]["balance"]) == 0
    assert all(
        amount(row["principal"]) >= 0
        and amount(row["interest"]) >= 0
        and amount(row["balance"]) >= 0
        for row in rows
    )


def test_bullet_schedule_has_no_interim_payments() -> None:
    data = response("simple_bullet")
    rows = data["schedule"]
    assert isinstance(rows, list)

    for row in rows[:-1]:
        assert row["payment"] == "0.00"
        assert row["principal"] == "0.00"
        assert row["interest"] == "0.00"
        assert row["balance"] == "100,000.00"

    last = rows[-1]
    assert last["payment"] == "103,650.00"
    assert last["principal"] == "100,000.00"
    assert last["interest"] == "3,650.00"


@pytest.mark.parametrize(
    ("periods", "period_value", "unit"),
    [
        ("12", "1", "month"),
        ("1", "1", "year"),
        ("4", "1", "quarter"),
        ("365", "1", "day"),
    ],
)
def test_equivalent_period_units_give_the_same_annual_rate(
    periods: str,
    period_value: str,
    unit: str,
) -> None:
    data = response("interest_only", ("100000", "3650", periods, period_value, unit))
    labels = {"year": "年", "quarter": "季", "month": "月", "day": "日"}

    assert data["contract_annual_rate_percent"] == "3.6500"
    assert data["total_years"] == "1"
    assert data["period_label"] == f"1 {labels[unit]}"


def test_equal_principal_reverses_a_real_schedule() -> None:
    principal = Decimal("240000")
    periods = 24
    monthly_rate = Decimal("0.004")
    per_period_principal = principal / periods

    with localcontext() as ctx:
        ctx.prec = 50
        remaining = principal
        total_interest = Decimal(0)
        pv = Decimal(0)
        for period in range(1, periods + 1):
            interest = remaining * monthly_rate
            payment = per_period_principal + interest
            total_interest += interest
            pv += payment / (1 + monthly_rate) ** period
            remaining -= per_period_principal

    assert remaining == 0
    assert total_interest == Decimal("12000.00")
    assert abs(pv - principal) < Decimal("1e-30")

    data = response(
        "equal_principal",
        (str(principal), str(total_interest), "24", "1", "month"),
    )
    assert data["contract_annual_rate_percent"] == "4.8000"
    assert data["irr_annual_rate_percent"] == "4.8000"
    assert data["irr_relation"] == "equal"


def test_equal_installment_solver_round_trip() -> None:
    principal = Decimal("100000")
    periods = 12
    monthly_rate = Decimal("0.005")

    with localcontext() as ctx:
        ctx.prec = 50
        payment = principal * monthly_rate / (1 - (1 + monthly_rate) ** (-periods))
        total_interest = (payment * periods - principal).quantize(Decimal("0.000001"))

    data = response(
        "equal_installment",
        (str(principal), str(total_interest), str(periods), "1", "month"),
    )
    assert data["contract_period_rate_percent"] == "0.5000"
    assert data["contract_annual_rate_percent"] == "6.0000"
    assert data["irr_relation"] == "equal"


@pytest.mark.parametrize("mode", ALL_MODES)
def test_single_period_collapses_every_mode(mode: str) -> None:
    data = response(mode, ("1000", "10", "1", "1", "month"))

    assert data["contract_annual_rate_percent"] == "12.0000"
    assert data["irr_annual_rate_percent"] == "12.0000"
    assert data["contract_period_rate_percent"] == "1.0000"
    assert data["irr_relation"] == "equal"


@pytest.mark.parametrize("mode", ALL_MODES)
def test_zero_interest_is_allowed(mode: str) -> None:
    data = response(mode, ("100000", "0", "12", "1", "month"))

    assert data["contract_annual_rate_percent"] == "0.0000"
    assert data["irr_annual_rate_percent"] == "0.0000"
    assert data["irr_relation"] == "equal"
    assert "≈ 0.0000%" in str(data["formula"])


def test_amounts_accept_grouping_separators() -> None:
    data = response("interest_only", ("100,000", "3，650", "12", "1", "month"))

    assert data["contract_annual_rate_percent"] == "3.6500"
    assert data["total_years"] == "1"


def test_formula_keeps_the_entered_amount_precision() -> None:
    data = response("interest_only", ("100000.50", "3650.125", "12", "1", "month"))

    assert "100,000.50" in str(data["formula"])
    assert "3,650.125" in str(data["formula"])


def test_fractional_period_length_and_total_years() -> None:
    data = response("interest_only", ("8000", "300", "3", "1", "quarter"))

    assert data["contract_annual_rate_percent"] == "5.0000"
    assert data["total_years"] == "0.75"
    assert data["period_label"] == "1 季"
    assert "1/4" in str(data["formula"])


def test_decimal_period_value() -> None:
    data = response("interest_only", ("100000", "3650", "8", "1.5", "month"))

    assert data["period_label"] == "1.5 月"
    assert data["total_years"] == "1"
    assert data["contract_annual_rate_percent"] == "3.6500"


@pytest.mark.parametrize(
    ("args", "field"),
    [
        (("0", "10", "12", "1", "month", "interest_only"), "principal"),
        (("-1", "10", "12", "1", "month", "interest_only"), "principal"),
        (("1000", "-1", "12", "1", "month", "interest_only"), "interest"),
        (("1000", "10", "0", "1", "month", "interest_only"), "periods"),
        (("1000", "10", "1.5", "1", "month", "interest_only"), "periods"),
        (("1000", "10", "1201", "1", "month", "interest_only"), "periods"),
        (("1000", "10", "12", "0", "month", "interest_only"), "period_value"),
        (("1000", "10", "12", "abc", "month", "interest_only"), "period_value"),
        (("1000", "10", "12", "1/0", "month", "interest_only"), "period_value"),
        (("1000", "10", "12", "101", "year", "interest_only"), "period_value"),
        (("1000", "10", "12", "1213", "month", "interest_only"), "period_value"),
        (("1000", "10", "12", "1", "week", "interest_only"), "period_unit"),
        (("1000", "10", "12", "1", "month", "annuity"), "mode"),
    ],
)
def test_invalid_inputs_report_the_right_field(args: tuple[str, ...], field: str) -> None:
    with pytest.raises(InputError) as exc_info:
        analyze(*args)

    assert exc_info.value.field == field
    assert exc_info.value.message


@pytest.mark.parametrize("raw", ["", "   ", "0", "-1", "1.5", "12a", "１a", "1/12"])
def test_invalid_period_counts(raw: str) -> None:
    with pytest.raises(InputError) as exc_info:
        analyze("1000", "10", raw, "1", "month", "interest_only")

    assert exc_info.value.field == "periods"


@pytest.mark.parametrize("raw", ["", "0", "-1", "abc", "1/0", "nan", "Infinity", "1/2/3"])
def test_invalid_period_values(raw: str) -> None:
    with pytest.raises(InputError) as exc_info:
        analyze("1000", "10", "12", raw, "month", "interest_only")

    assert exc_info.value.field == "period_value"


@pytest.mark.parametrize("mode", ["equal_installment", "flat_rate"])
def test_payment_input_reproduces_the_interest_input(mode: str) -> None:
    from_interest = response(mode)
    from_payment = response(mode, ("100000", None, "12", "1", "month"), payment="8637.5")

    assert from_payment["input_basis"] == "payment"
    assert from_interest["input_basis"] == "interest"
    for key in (
        "contract_annual_rate",
        "contract_period_rate",
        "irr_annual_rate",
        "irr_relation",
        "schedule",
        "schedule_total",
    ):
        assert from_payment[key] == from_interest[key]
    assert from_payment["payment"] == from_interest["payment"] == "8,637.50"


@pytest.mark.parametrize("mode", ["equal_installment", "flat_rate"])
def test_payment_input_formula_shows_the_derived_interest(mode: str) -> None:
    data = response(mode, ("100000", None, "12", "1", "month"), payment="8637.5")
    formula = str(data["formula"])

    assert "每期还款 A = 8,637.50（输入）" in formula
    assert "总利息 = 期数 × 每期还款 − 本金" in formula
    assert "= 12 × 8,637.50 − 100,000 = 3,650.00" in formula
    assert "≈ 6.6707%" in formula or "≈ 3.6500%" in formula


def test_payment_input_accepts_amounts_below_one_cent() -> None:
    data = response("flat_rate", ("100000", None, "12", "1", "month"), payment="8637.504")

    assert data["schedule_total"]["interest"] == "3,650.05"
    assert "3,650.048" in str(data["formula"])


def test_payment_input_allows_zero_total_interest() -> None:
    data = response("equal_installment", ("1200", None, "12", "1", "month"), payment="100")

    assert data["contract_annual_rate_percent"] == "0.0000"
    assert data["payment"] == "100.00"
    assert data["schedule_total"]["interest"] == "0.00"


@pytest.mark.parametrize("mode", ["equal_installment", "flat_rate"])
def test_both_amount_fields_are_rejected(mode: str) -> None:
    with pytest.raises(InputError) as exc_info:
        response(mode, payment="8637.5")

    assert exc_info.value.field == "payment"
    assert "只需填写一项" in exc_info.value.message


@pytest.mark.parametrize("mode", ["equal_installment", "flat_rate"])
def test_neither_amount_field_is_rejected(mode: str) -> None:
    with pytest.raises(InputError) as exc_info:
        response(mode, ("100000", "", "12", "1", "month"))

    assert exc_info.value.field == "interest"
    assert "总利息或每期还款" in exc_info.value.message


@pytest.mark.parametrize("mode", ["equal_installment", "flat_rate"])
def test_payment_below_average_principal_is_rejected(mode: str) -> None:
    with pytest.raises(InputError) as exc_info:
        response(mode, ("100000", None, "12", "1", "month"), payment="8000")

    assert exc_info.value.field == "payment"
    assert "非负总利息" in exc_info.value.message


def test_derived_interest_beyond_the_range_is_rejected() -> None:
    with pytest.raises(InputError) as exc_info:
        response("flat_rate", ("1", None, "12", "1", "month"), payment="1000000000000000")

    assert exc_info.value.field == "payment"
    assert "超出可计算范围" in exc_info.value.message


@pytest.mark.parametrize("mode", ["equal_principal", "interest_only", "simple_bullet"])
def test_payment_is_only_for_level_payment_modes(mode: str) -> None:
    with pytest.raises(InputError) as exc_info:
        response(mode, ("100000", None, "12", "1", "month"), payment="8637.5")

    assert exc_info.value.field == "payment"
    assert "只支持输入总利息" in exc_info.value.message


@pytest.mark.parametrize("mode", ["equal_principal", "interest_only", "simple_bullet"])
def test_non_level_modes_still_require_interest(mode: str) -> None:
    with pytest.raises(InputError) as exc_info:
        response(mode, ("100000", None, "12", "1", "month"))

    assert exc_info.value.field == "interest"
    assert exc_info.value.message == "请输入总利息"


def test_no_concession_matches_the_plain_response() -> None:
    plain = response("flat_rate")
    explicit = response("flat_rate", concession="none")

    assert explicit["concession"]["type"] == "none"
    for key in ("contract_annual_rate", "irr_annual_rate", "formula", "schedule"):
        assert explicit[key] == plain[key]


@pytest.mark.parametrize("mode", ALL_MODES)
def test_full_waiver_removes_all_interest(mode: str) -> None:
    base = response(mode)
    data = response(mode, concession="full_waiver")

    assert data["concession"]["type"] == "full_waiver"
    assert data["concession"]["net_interest"] == "0.00"
    assert data["concession"]["waived_interest"] == "3,650.00"
    assert data["contract_annual_rate_percent"] == base["contract_annual_rate_percent"]
    assert data["irr_annual_rate_percent"] == "0.0000"
    assert data["irr_relation"] == "lower"
    assert data["schedule_total"]["interest"] == "0.00"
    assert data["schedule_total"]["payment"] == "100,000.00"
    assert all(row["interest"] == "0.00" for row in data["schedule"])
    assert data["payment"] is None


def test_first_periods_waives_the_leading_interest() -> None:
    base = response("interest_only")
    data = response("interest_only", concession="first_periods", concession_value="3")

    assert data["concession"]["label"] == "前 3 期免息"
    assert data["concession"]["waived_interest"] == "912.50"
    assert data["concession"]["net_interest"] == "2,737.50"
    assert data["contract_annual_rate_percent"] == base["contract_annual_rate_percent"]
    assert data["contract_annual_rate_percent"] == "3.6500"
    assert data["irr_relation"] == "lower"

    rows = data["schedule"]
    assert [row["interest"] for row in rows[:3]] == ["0.00"] * 3
    assert [row["payment"] for row in rows[:3]] == ["0.00"] * 3
    assert rows[3]["interest"] == "304.17"
    assert rows[-1]["principal"] == "100,000.00"
    assert data["schedule_total"]["interest"] == "2,737.50"


def test_first_periods_keeps_the_amortization_on_installment_modes() -> None:
    base = response("equal_installment")
    data = response("equal_installment", concession="first_periods", concession_value="3")

    waived = sum(amount(row["interest"]) for row in base["schedule"][:3])
    assert abs(amount(data["concession"]["waived_interest"]) - waived) <= Decimal("0.01")
    assert amount(data["concession"]["net_interest"]) == Decimal("3650") - amount(
        data["concession"]["waived_interest"]
    )
    assert [row["principal"] for row in data["schedule"]] == [
        row["principal"] for row in base["schedule"]
    ]
    assert [row["interest"] for row in data["schedule"][:3]] == ["0.00"] * 3
    assert data["payment"] is None
    assert data["irr_relation"] == "lower"


def test_first_periods_on_bullet_waives_by_accrual() -> None:
    data = response("simple_bullet", concession="first_periods", concession_value="3")

    assert data["concession"]["waived_interest"] == "912.50"
    assert data["concession"]["net_interest"] == "2,737.50"
    assert "按计息期数折算" in str(data["concession"]["detail"])
    assert data["schedule"][0]["interest"] == "0.00"
    assert data["schedule"][-1]["interest"] == "2,737.50"
    assert data["irr_annual_rate_percent"] == "2.7037"


@pytest.mark.parametrize("mode", ["interest_only", "flat_rate", "equal_installment"])
def test_concession_irr_matches_the_discounted_flows(mode: str) -> None:
    analysis = analyze(
        "100000",
        "3650",
        "12",
        "1",
        "month",
        mode,
        concession="first_periods",
        concession_value_raw="4",
    )
    rate = analysis.irr_period_rate
    data = to_response(analysis)

    with localcontext() as ctx:
        ctx.prec = 50
        pv = sum(amount(row["payment"]) / (1 + rate) ** row["period"] for row in data["schedule"])

    assert abs(pv - Decimal("100000")) < Decimal("0.5")


def test_first_periods_must_stay_within_the_term() -> None:
    for raw in ("0", "13", "1.5", "-1"):
        with pytest.raises(InputError) as exc_info:
            response("flat_rate", concession="first_periods", concession_value=raw)
        assert exc_info.value.field == "concession_value"

    with pytest.raises(InputError) as exc_info:
        response("flat_rate", concession="first_periods")
    assert exc_info.value.message == "请输入免息期数"


def test_fixed_amount_reduces_interest_proportionally() -> None:
    base = response("flat_rate")
    data = response("flat_rate", concession="amount", concession_value="500")

    assert data["concession"]["waived_interest"] == "500.00"
    assert data["concession"]["net_interest"] == "3,150.00"
    assert data["contract_annual_rate_percent"] == base["contract_annual_rate_percent"]
    assert data["contract_annual_rate_percent"] == "3.6500"
    assert data["irr_relation"] == "higher"
    assert data["schedule_total"]["interest"] == "3,150.00"
    assert data["schedule"][0]["interest"] == "262.50"
    assert "摊薄" in str(data["concession"]["detail"])


def test_fixed_amount_above_interest_falls_back_to_full_waiver() -> None:
    data = response("flat_rate", concession="amount", concession_value="9999")

    assert data["concession"]["net_interest"] == "0.00"
    assert data["concession"]["waived_interest"] == "3,650.00"
    assert "按全额免息处理" in str(data["concession"]["detail"])


def test_fixed_amount_must_be_positive() -> None:
    for raw in ("0", "-5", "abc"):
        with pytest.raises(InputError) as exc_info:
            response("flat_rate", concession="amount", concession_value=raw)
        assert exc_info.value.field == "concession_value"


def test_rate_discount_reprices_the_interest_only_mode() -> None:
    data = response("interest_only", concession="rate_discount", concession_value="7")

    assert data["concession"]["label"] == "利率 7 折"
    assert data["contract_annual_rate_percent"] == "2.5550"
    assert data["irr_annual_rate_percent"] == "2.5550"
    assert data["concession"]["net_interest"] == "2,555.00"
    assert data["concession"]["base_annual_rate_percent"] == "3.6500"


@pytest.mark.parametrize("mode", ALL_MODES)
def test_rate_discount_round_trips_through_a_plain_request(mode: str) -> None:
    discounted = analyze(
        "100000",
        "3650",
        "12",
        "1",
        "month",
        mode,
        concession="rate_discount",
        concession_value_raw="8",
    )
    plain = analyze(
        str(discounted.principal),
        f"{discounted.net_interest:.20f}",
        "12",
        "1",
        "month",
        mode,
    )
    data = to_response(discounted)
    reparsed = to_response(plain)

    for key in (
        "contract_annual_rate_percent",
        "irr_annual_rate_percent",
        "contract_period_rate_percent",
        "irr_relation",
        "payment",
        "schedule",
        "schedule_total",
    ):
        assert data[key] == reparsed[key]


@pytest.mark.parametrize("mode", ALL_MODES)
def test_ten_percent_discount_changes_no_numbers(mode: str) -> None:
    base = response(mode)
    data = response(mode, concession="rate_discount", concession_value="10")

    for key in ("contract_annual_rate", "irr_annual_rate", "schedule_total", "schedule"):
        assert data[key] == base[key]
    assert data["concession"]["waived_interest"] == "0.00"


def test_rate_discount_out_of_range_is_rejected() -> None:
    for raw in ("0", "10.5", "11", "-1"):
        with pytest.raises(InputError) as exc_info:
            response("flat_rate", concession="rate_discount", concession_value=raw)
        assert exc_info.value.field == "concession_value"


def test_unknown_concession_is_rejected() -> None:
    with pytest.raises(InputError) as exc_info:
        response("flat_rate", concession="coupon")

    assert exc_info.value.field == "concession"


def test_concession_works_with_payment_input() -> None:
    from_payment = response(
        "flat_rate",
        ("100000", None, "12", "1", "month"),
        payment="8637.5",
        concession="first_periods",
        concession_value="3",
    )
    from_interest = response("flat_rate", concession="first_periods", concession_value="3")

    assert from_payment["concession"] == from_interest["concession"]
    assert from_payment["irr_annual_rate"] == from_interest["irr_annual_rate"]
    assert from_payment["schedule"] == from_interest["schedule"]


def test_subsidy_note_explains_the_contract_rate() -> None:
    data = response("interest_only", concession="first_periods", concession_value="3")
    note = str(data["note"])

    assert "合同利率不变" in note
    assert "实际 IRR 低于合同口径" in note


def test_concession_is_appended_to_the_formula() -> None:
    data = response("flat_rate", concession="first_periods", concession_value="3")
    formula = str(data["formula"])

    assert "优惠：前 3 期免息" in formula
    assert "实际总利息 2,737.50 元" in formula


@pytest.mark.parametrize(
    ("mode", "concession", "value"),
    [
        ("equal_installment", "first_periods", "3"),
        ("flat_rate", "amount", "500"),
        ("interest_only", "full_waiver", None),
        ("simple_bullet", "rate_discount", "8"),
        ("equal_principal", "first_periods", "12"),
    ],
)
def test_concession_schedule_reconciles(
    mode: str,
    concession: str,
    value: str | None,
) -> None:
    data = response(mode, concession=concession, concession_value=value)
    rows = data["schedule"]
    totals = data["schedule_total"]

    assert sum(amount(row["principal"]) for row in rows) == amount(totals["principal"])
    assert sum(amount(row["interest"]) for row in rows) == amount(totals["interest"])
    assert sum(amount(row["payment"]) for row in rows) == amount(totals["payment"])
    assert amount(totals["interest"]) == amount(data["concession"]["net_interest"])
    assert rows[-1]["balance"] == "0.00"
