from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

SAMPLE_REQUEST = {
    "principal": "100000",
    "interest": "3650",
    "periods": "12",
    "period_value": "1",
    "period_unit": "month",
}

MODE_EXPECTATIONS = [
    ("equal_installment", "6.6707", "6.6707", "equal"),
    ("equal_principal", "6.7385", "6.7385", "equal"),
    ("interest_only", "3.6500", "3.6500", "equal"),
    ("flat_rate", "3.6500", "6.6707", "higher"),
    ("simple_bullet", "3.6500", "3.5903", "lower"),
]


def test_home_lists_every_tool() -> None:
    response = client.get("/")

    assert response.status_code == 200
    text = response.text
    for name in (
        "单利年化",
        "存款利息",
        "税后工资",
        "房贷计算",
        "公积金贷款",
        "提前还款",
        "二手房税费",
        "个税计算",
        "契税计算",
        "房产税",
        "养老金计算",
        "退休年龄",
        "产假计算",
        "育儿补贴",
        "出生时长",
    ):
        assert name in text
    for slug in (
        "interest",
        "deposit",
        "salary",
        "mortgage",
        "fund-loan",
        "prepayment",
        "tax",
        "deed-tax",
        "property-tax",
        "resale",
        "pension",
        "retirement",
        "maternity",
        "childcare",
        "age",
    ):
        assert f'href="{slug}/"' in text


def test_interest_page_is_served_under_its_own_path() -> None:
    response = client.get("/interest/")

    assert response.status_code == 200
    assert "单利年化" in response.text
    assert "app.js" in response.text
    assert "../styles.css" in response.text


@pytest.mark.parametrize(
    "marker",
    [
        'id="basis-switch"',
        'data-basis="interest"',
        'data-basis="payment"',
        'id="interest-label"',
        'id="interest-unit"',
        'class="mini-switch"',
        'id="concession-type"',
        'value="first_periods"',
        'id="concession-value"',
        'id="concession-value-label"',
        'id="concession-value-unit"',
        'id="concession-hint"',
        'id="concession-line"',
        'id="concession-text"',
    ],
)
def test_ui_markup_the_script_relies_on_is_present(marker: str) -> None:
    assert marker in client.get("/interest/").text


def test_static_assets_are_served() -> None:
    assert client.get("/styles.css").status_code == 200
    assert client.get("/home.css").status_code == 200
    assert client.get("/interest/app.js").status_code == 200
    assert client.get("/favicon.svg").status_code == 200


TOOL_SLUGS = (
    "interest",
    "deposit",
    "salary",
    "mortgage",
    "fund-loan",
    "prepayment",
    "tax",
    "deed-tax",
    "property-tax",
    "resale",
    "pension",
    "retirement",
    "maternity",
    "childcare",
)

TOOL_DEFAULT_PAYLOADS = {
    "deposit": {
        "principal": "100000",
        "rate": "2",
        "term": "1",
        "unit": "year",
        "method": "simple",
    },
    "mortgage": {"amount": "1000000", "years": "30", "rate": "3.1", "method": "equal_installment"},
    "fund-loan": {
        "total": "1000000",
        "fund": "600000",
        "years": "30",
        "fund_rate": "2.6",
        "commercial_rate": "3.1",
        "method": "equal_installment",
    },
    "prepayment": {
        "principal": "800000",
        "rate": "3.1",
        "months": "300",
        "extra": "200000",
        "penalty": "0",
        "method": "equal_installment",
    },
    "resale": {
        "price": "2000000",
        "area": "90",
        "homes": "first",
        "paid_two": "yes",
        "only_home": "no",
        "original": "1000000",
        "tax_mode": "deemed",
        "statutory": "3",
        "surcharge": "12",
    },
    "salary": {
        "salary": "15000",
        "base": "15000",
        "social_rate": "10.5",
        "fund_rate": "7",
        "deduction": "0",
    },
    "retirement": {"birth_year": "1985", "birth_month": "6", "type": "male"},
    "maternity": {"due": "2026-12-01", "type": "normal", "children": "1", "reward": "30"},
    "childcare": {"birth_year": "2025", "birth_month": "1", "standard": "3600"},
    "deed-tax": {
        "type": "housing",
        "price": "2000000",
        "area": "90",
        "homes": "first",
        "statutory_rate": "3",
    },
    "property-tax": {"mode": "value", "original_value": "1000000", "deduction": "30"},
    "age": {"birth": "1995-06-15"},
}


def test_every_tool_page_links_back_to_the_hub() -> None:
    for slug in TOOL_SLUGS:
        text = client.get(f"/{slug}/").text
        assert 'href="../"' in text
        assert text.count('class="tool-nav"') == 1


@pytest.mark.parametrize("slug", TOOL_DEFAULT_PAYLOADS)
def test_template_tool_page_is_served(slug: str) -> None:
    response = client.get(f"/{slug}/")

    assert response.status_code == 200
    assert "计算工具集" in response.text
    assert f'data-tool="{slug}"' in response.text


@pytest.mark.parametrize(("slug", "payload"), TOOL_DEFAULT_PAYLOADS.items())
def test_tool_api_returns_a_standard_response(slug: str, payload: dict[str, str]) -> None:
    response = client.post(f"/api/{slug}/calculate", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert isinstance(body["primary"], str)
    assert body["primary"].strip()
    assert isinstance(body["facts"], list)
    assert body["metrics"]
    assert body["formula"]
    assert body["note"]


def test_tool_api_reports_the_field() -> None:
    response = client.post(
        "/api/mortgage/calculate",
        json={"amount": "1000000", "years": "41", "rate": "3.1"},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["field"] == "years"
    assert "贷款年限" in body["detail"]


def test_unknown_tool_is_not_found() -> None:
    assert client.get("/nope/").status_code == 404
    assert client.post("/api/nope/calculate", json={}).status_code == 404


def test_calculate_default_values() -> None:
    response = client.post("/api/calculate", json={**SAMPLE_REQUEST, "mode": "interest_only"})

    assert response.status_code == 200
    body = response.json()
    assert body["contract_annual_rate"] == "0.0365000000"
    assert body["contract_annual_rate_percent"] == "3.6500"
    assert body["contract_period_rate_percent"] == "0.3042"
    assert body["irr_annual_rate"] == "0.0365000000"
    assert body["irr_annual_rate_percent"] == "3.6500"
    assert body["irr_relation"] == "equal"
    assert body["mode"] == "interest_only"
    assert body["period_label"] == "1 月"
    assert "≈ 3.6500%" in body["formula"]
    assert len(body["schedule"]) == 12
    assert body["schedule"][0]["principal"] == "0.00"
    assert body["schedule"][-1]["principal"] == "100,000.00"
    assert body["schedule"][-1]["balance"] == "0.00"
    assert body["schedule_total"] == {
        "payment": "103,650.00",
        "principal": "100,000.00",
        "interest": "3,650.00",
    }


@pytest.mark.parametrize(
    ("mode", "contract", "irr", "relation"),
    MODE_EXPECTATIONS,
)
def test_every_mode_is_accepted(
    mode: str,
    contract: str,
    irr: str,
    relation: str,
) -> None:
    response = client.post("/api/calculate", json={**SAMPLE_REQUEST, "mode": mode})

    assert response.status_code == 200
    body = response.json()
    assert body["contract_annual_rate_percent"] == contract
    assert body["irr_annual_rate_percent"] == irr
    assert body["irr_relation"] == relation
    assert body["total_years"] == "1"
    assert body["period_label"] == "1 月"
    assert body["formula"]
    assert body["note"]
    assert len(body["schedule"]) == 12
    assert body["schedule"][-1]["balance"] == "0.00"


def test_calculate_equal_principal_with_fraction_and_commas() -> None:
    response = client.post(
        "/api/calculate",
        json={
            "principal": "100,000",
            "interest": "3,650",
            "periods": "12",
            "period_value": "1",
            "period_unit": "month",
            "mode": "equal_principal",
        },
    )

    assert response.status_code == 200
    assert response.json()["contract_annual_rate_percent"] == "6.7385"


def test_period_defaults_to_one_month() -> None:
    request = {**SAMPLE_REQUEST, "mode": "interest_only"}
    request.pop("period_value")
    request.pop("period_unit")

    response = client.post("/api/calculate", json=request)

    assert response.status_code == 200
    body = response.json()
    assert body["period_label"] == "1 月"
    assert body["contract_annual_rate_percent"] == "3.6500"


def test_period_units_are_equivalent_for_the_same_total_duration() -> None:
    month = client.post(
        "/api/calculate",
        json={**SAMPLE_REQUEST, "mode": "interest_only"},
    ).json()
    year = client.post(
        "/api/calculate",
        json={
            **SAMPLE_REQUEST,
            "periods": "1",
            "period_value": "1",
            "period_unit": "year",
            "mode": "interest_only",
        },
    ).json()

    assert month["contract_annual_rate_percent"] == year["contract_annual_rate_percent"]
    assert month["total_years"] == year["total_years"] == "1"
    assert year["period_label"] == "1 年"


def test_business_validation_returns_the_field() -> None:
    response = client.post(
        "/api/calculate",
        json={**SAMPLE_REQUEST, "principal": "0", "mode": "interest_only"},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["field"] == "principal"
    assert "总本金" in body["detail"]


def test_period_validation_returns_the_field() -> None:
    response = client.post(
        "/api/calculate",
        json={**SAMPLE_REQUEST, "period_value": "0", "mode": "interest_only"},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["field"] == "period_value"


def test_malformed_request_shape_is_rejected() -> None:
    response = client.post("/api/calculate", json={"mode": "interest_only"})

    assert response.status_code == 422
    assert response.json()["detail"] == "请求参数格式不正确"


@pytest.mark.parametrize("mode", ["equal_installment", "flat_rate"])
def test_payment_basis_request_matches_interest_basis(mode: str) -> None:
    request = {**SAMPLE_REQUEST, "mode": mode}
    interest_basis = client.post("/api/calculate", json=request).json()
    payment_basis = client.post(
        "/api/calculate",
        json={**request, "interest": None, "payment": "8637.5"},
    ).json()

    assert payment_basis["input_basis"] == "payment"
    assert payment_basis["payment"] == interest_basis["payment"] == "8,637.50"
    assert payment_basis["contract_annual_rate"] == interest_basis["contract_annual_rate"]
    assert payment_basis["irr_annual_rate"] == interest_basis["irr_annual_rate"]
    assert payment_basis["schedule_total"] == interest_basis["schedule_total"]


def test_non_level_mode_reports_no_payment_field() -> None:
    response = client.post(
        "/api/calculate",
        json={**SAMPLE_REQUEST, "mode": "interest_only"},
    ).json()

    assert response["input_basis"] == "interest"
    assert response["payment"] is None


def test_both_amount_fields_rejected_via_api() -> None:
    response = client.post(
        "/api/calculate",
        json={**SAMPLE_REQUEST, "mode": "flat_rate", "payment": "8637.5"},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["field"] == "payment"
    assert "只需填写一项" in body["detail"]


def test_payment_on_non_level_mode_returns_the_field() -> None:
    response = client.post(
        "/api/calculate",
        json={**SAMPLE_REQUEST, "interest": None, "mode": "interest_only", "payment": "8637.5"},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["field"] == "payment"
    assert body["detail"] == "该还款方式只支持输入总利息"


def test_absent_interest_returns_the_field() -> None:
    response = client.post(
        "/api/calculate",
        json={**SAMPLE_REQUEST, "interest": None, "mode": "interest_only"},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["field"] == "interest"
    assert body["detail"] == "请输入总利息"


def test_unknown_mode_is_rejected() -> None:
    response = client.post(
        "/api/calculate",
        json={**SAMPLE_REQUEST, "mode": "annuity"},
    )

    assert response.status_code == 422


def test_unknown_period_unit_is_rejected() -> None:
    response = client.post(
        "/api/calculate",
        json={**SAMPLE_REQUEST, "period_unit": "week", "mode": "interest_only"},
    )

    assert response.status_code == 422


def test_concession_is_echoed_in_the_response() -> None:
    response = client.post(
        "/api/calculate",
        json={
            **SAMPLE_REQUEST,
            "mode": "flat_rate",
            "concession": "first_periods",
            "concession_value": "3",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["concession"]["type"] == "first_periods"
    assert body["concession"]["label"] == "前 3 期免息"
    assert body["concession"]["net_interest"] == "2,737.50"
    assert body["concession"]["waived_interest"] == "912.50"
    assert body["concession"]["base_annual_rate_percent"] is None
    assert body["contract_annual_rate_percent"] == "3.6500"
    assert body["irr_relation"] == "higher"
    assert body["payment"] is None
    assert body["schedule"][0]["interest"] == "0.00"
    assert body["schedule_total"]["interest"] == "2,737.50"


def test_concession_defaults_to_none() -> None:
    body = client.post(
        "/api/calculate",
        json={**SAMPLE_REQUEST, "mode": "interest_only"},
    ).json()

    assert body["concession"] == {
        "type": "none",
        "label": "",
        "detail": "",
        "waived_interest": "0.00",
        "net_interest": "3,650.00",
        "base_annual_rate_percent": None,
    }


def test_rate_discount_reports_the_base_rate() -> None:
    body = client.post(
        "/api/calculate",
        json={
            **SAMPLE_REQUEST,
            "mode": "interest_only",
            "concession": "rate_discount",
            "concession_value": "7",
        },
    ).json()

    assert body["concession"]["base_annual_rate_percent"] == "3.6500"
    assert body["contract_annual_rate_percent"] == "2.5550"
    assert body["irr_annual_rate_percent"] == "2.5550"
    assert body["concession"]["net_interest"] == "2,555.00"


def test_invalid_concession_value_returns_the_field() -> None:
    response = client.post(
        "/api/calculate",
        json={
            **SAMPLE_REQUEST,
            "mode": "flat_rate",
            "concession": "first_periods",
            "concession_value": "13",
        },
    )

    assert response.status_code == 400
    body = response.json()
    assert body["field"] == "concession_value"
    assert "免息期数" in body["detail"]


def test_unknown_concession_is_rejected() -> None:
    response = client.post(
        "/api/calculate",
        json={**SAMPLE_REQUEST, "mode": "flat_rate", "concession": "coupon"},
    )

    assert response.status_code == 422


TAX_REQUEST = {
    "income": "20000",
    "income_basis": "month",
    "bonus": "60000",
    "bonus_mode": "separate",
    "social": "3000",
    "special": {"child_education": "2000"},
    "serious_illness": "0",
    "pension": "0",
}


def test_tax_page_is_served() -> None:
    response = client.get("/tax/")

    assert response.status_code == 200
    assert "个税计算" in response.text
    assert "tax.js" in response.text


def test_tax_assets_are_served() -> None:
    assert client.get("/tax/tax.js").status_code == 200
    assert client.get("/tax/tax.css").status_code == 200


def test_tax_calculate_full_example() -> None:
    response = client.post("/api/tax/calculate", json=TAX_REQUEST)

    assert response.status_code == 200
    body = response.json()
    assert body["annual_income"] == "240,000.00"
    assert body["taxable_income"] == "120,000.00"
    assert body["total_tax"] == "15,270.00"
    assert body["net_income"] == "248,730.00"
    assert body["effective_rate_percent"] == "5.0900"
    assert body["marginal_rate_percent"] == "10.0000"
    assert body["bonus_comparison"]["better"] == "separate"
    assert len(body["schedule"]) == 12
    assert body["schedule"][0]["tax"] == "300.00"
    assert body["schedule_total"]["tax"] == "9,480.00"
    assert "综合所得应纳税所得额" in body["formula"]
    assert body["note"]


def test_tax_request_accepts_only_income() -> None:
    body = client.post("/api/tax/calculate", json={"income": "10000"}).json()

    assert body["income_basis"] == "month"
    assert body["bonus_mode"] == "separate"
    assert body["annual_income"] == "120,000.00"
    assert body["taxable_income"] == "60,000.00"
    assert body["total_tax"] == "3,480.00"
    assert body["deductions"]["special"] == "0.00"


def test_tax_cap_error_returns_the_field() -> None:
    response = client.post(
        "/api/tax/calculate",
        json={**TAX_REQUEST, "special": {"mortgage_interest": "1001"}},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["field"] == "mortgage_interest"
    assert "每月最多" in body["detail"]


def test_tax_mutual_exclusion_returns_the_field() -> None:
    response = client.post(
        "/api/tax/calculate",
        json={**TAX_REQUEST, "special": {"mortgage_interest": "1000", "housing_rent": "1500"}},
    )

    assert response.status_code == 400
    assert response.json()["field"] == "housing_rent"


def test_tax_missing_income_is_rejected() -> None:
    response = client.post("/api/tax/calculate", json={"bonus": "0"})

    assert response.status_code == 422


def test_tax_unknown_income_basis_is_rejected() -> None:
    response = client.post(
        "/api/tax/calculate",
        json={**TAX_REQUEST, "income_basis": "week"},
    )

    assert response.status_code == 422


PENSION_EMPLOYEE = {
    "track": "employee",
    "paid_years": "5",
    "remaining_years": "30",
    "retirement_age": "60",
    "base": "10000",
    "social": "8000",
    "growth": "3",
    "rate": "3",
    "balance": "50000",
}


def test_pension_page_is_served() -> None:
    response = client.get("/pension/")

    assert response.status_code == 200
    assert "养老金计算" in response.text
    assert "pension.js" in response.text


def test_pension_assets_are_served() -> None:
    assert client.get("/pension/pension.js").status_code == 200
    assert client.get("/pension/pension.css").status_code == 200


def test_pension_employee_example() -> None:
    response = client.post("/api/pension/calculate", json=PENSION_EMPLOYEE)

    assert response.status_code == 200
    body = response.json()
    assert body["track"] == "employee"
    assert body["eligible"] is True
    assert body["years"] == 35
    assert body["annuity_months"] == 139
    assert body["social_at_retirement"] == "19,418.10"
    assert body["index"] == "1.25"
    assert body["account_balance"] == "800,053.99"
    assert body["basic_pension"] == "7,645.88"
    assert body["account_pension"] == "5,755.78"
    assert body["monthly_total"] == "13,401.66"
    assert body["replacement_rate_percent"] == "55.2131"
    assert len(body["schedule"]) == 30
    assert body["schedule"][0] == {
        "year": 1,
        "base": "10,000.00",
        "contribution": "9,600.00",
        "subsidy": None,
        "balance": "61,100.00",
    }
    assert body["schedule_total"] == {
        "paid": "456,723.99",
        "balance": "800,053.99",
        "years": "30",
    }


def test_pension_resident_defaults() -> None:
    body = client.post("/api/pension/calculate", json={"track": "resident"}).json()

    assert body["track"] == "resident"
    assert body["years"] == 15
    assert body["annuity_months"] == 139
    assert body["basic_pension"] == "143.00"
    assert body["account_balance"] == "19,714.85"
    assert body["monthly_total"] == "284.83"
    assert body["replacement_rate_percent"] is None
    assert body["social_at_retirement"] is None
    assert len(body["schedule"]) == 15
    assert body["schedule"][0]["subsidy"] == "60.00"


def test_pension_index_outside_the_bounds_returns_the_field() -> None:
    response = client.post(
        "/api/pension/calculate",
        json={**PENSION_EMPLOYEE, "base": "30000"},
    )

    assert response.status_code == 400
    body = response.json()
    assert body["field"] == "base"
    assert "60%–300%" in body["detail"]


def test_pension_retirement_age_is_validated() -> None:
    response = client.post(
        "/api/pension/calculate",
        json={**PENSION_EMPLOYEE, "retirement_age": "80"},
    )

    assert response.status_code == 400
    assert response.json()["field"] == "retirement_age"


def test_pension_unknown_track_is_rejected() -> None:
    response = client.post("/api/pension/calculate", json={"track": "flexible"})

    assert response.status_code == 422


def test_pension_region_presets_are_available() -> None:
    response = client.get("/api/pension/regions")

    assert response.status_code == 200
    body = response.json()
    regions = body["regions"]
    assert len(regions) >= 36
    codes = {region["code"] for region in regions}
    assert {"beijing", "shanghai", "shenzhen", "dalian", "shenyang", "wuhan"} <= codes
    assert all(float(region["base"]) > 0 for region in regions)
    assert all(region["year"] in (2024, 2025) for region in regions)
    assert "计发基数" in body["note"]


def test_pension_page_has_the_region_selector() -> None:
    text = client.get("/pension/").text

    assert 'id="region"' in text
    assert 'id="region-hint"' in text
    assert "当地社平 / 计发基数" in text


def test_city_params_endpoint() -> None:
    response = client.get("/api/city-params")

    assert response.status_code == 200
    body = response.json()
    regions = body["regions"]
    assert len(regions) >= 34
    assert body["year"] == 2025
    codes = {region["code"] for region in regions}
    assert {"beijing", "hubei1", "guangdong_gz", "xinjiang"} <= codes
    for region in regions:
        average = float(region["average"])
        lower = float(region["lower"])
        upper = float(region["upper"])
        assert 0.5 * average <= lower <= 0.65 * average
        assert 2.9 * average <= upper <= 3.1 * average
    assert "缴费基数" in body["note"]


def test_shutdown_endpoint_is_only_available_in_the_packaged_app() -> None:
    response = client.post("/api/shutdown", headers={"X-Requested-With": "calculator-toolkit"})

    assert response.status_code == 404
    assert "打包版" in response.json()["detail"]
