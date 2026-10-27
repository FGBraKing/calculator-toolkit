"""Decimal-based annualization for common repayment structures.

Two rates are produced:

* contract: the nominal annualized rate implied by the mode's own interest
  rule (flat fee, simple bullet, or rate on the outstanding balance).
* IRR: the nominal annualized internal rate of return of the payment
  schedule.

They coincide for equal-installment, equal-principal and interest-only
modes. Flat-rate instalments charge interest on the original principal and
therefore have a higher IRR; a bullet payment at maturity (with simple
interest) has a lower nominal IRR because interest arrives later.

Both rates are nominal: period rate / period years, with no in-period
compounding convention applied. The schedule returned alongside the rates
uses the contract rule for each row.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, replace
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation, localcontext

MODES = (
    "equal_installment",
    "equal_principal",
    "interest_only",
    "flat_rate",
    "simple_bullet",
)
# Modes whose cash flow is level, so total interest and per-period payment are
# interchangeable inputs.
LEVEL_PAYMENT_MODES = ("equal_installment", "flat_rate")
CONCESSIONS = ("none", "full_waiver", "first_periods", "amount", "rate_discount")
# Waivers trim the interest actually charged; the contract rate stays as written.
SUBSIDY_CONCESSIONS = ("full_waiver", "first_periods", "amount")
MAX_DISCOUNT = Decimal(10)
PERIOD_UNITS = ("year", "quarter", "month", "day")
PERIOD_UNIT_LABELS = {"year": "年", "quarter": "季", "month": "月", "day": "日"}
_PERIOD_DENOMINATORS = {"quarter": 4, "month": 12, "day": 365}
MAX_AMOUNT = Decimal("1000000000000000")
MAX_PERIODS = 1200
MAX_PERIOD_YEARS = Decimal("100")
MAX_RAW_LENGTH = 40
PRECISION = 50

_MONEY_QUANTUM = Decimal("0.01")
_PERCENT_QUANTUM = Decimal("0.0001")
_RATE_QUANTUM = Decimal("0.0000000001")
_YEARS_QUANTUM = Decimal("0.000001")


class InputError(ValueError):
    """A user-correctable input problem, tied to one form field."""

    def __init__(self, field: str, message: str) -> None:
        super().__init__(message)
        self.field = field
        self.message = message


@dataclass(frozen=True, slots=True)
class Analysis:
    principal: Decimal
    interest: Decimal
    periods: int
    period_years: Decimal
    period_years_text: str
    period_unit: str
    period_label: str
    mode: str
    contract_period_rate: Decimal
    irr_period_rate: Decimal
    contract_annual_rate: Decimal
    irr_annual_rate: Decimal
    total_years: Decimal
    payment: Decimal | None = None
    input_basis: str = "interest"
    concession: str = "none"
    concession_value: Decimal | None = None
    net_interest: Decimal | None = None
    waived_interest: Decimal = Decimal(0)
    base_contract_annual_rate: Decimal | None = None


def analyze(
    principal_raw: str,
    interest_raw: str | None,
    periods_raw: str,
    period_value_raw: str,
    period_unit: str,
    mode: str,
    *,
    payment_raw: str | None = None,
    concession: str = "none",
    concession_value_raw: str | None = None,
) -> Analysis:
    """Parse form strings, validate them, and compute both annualized rates."""
    if mode not in MODES:
        raise InputError("mode", "还款方式无效")
    if period_unit not in PERIOD_UNITS:
        raise InputError("period_unit", "每期时长单位无效")

    with localcontext() as ctx:
        ctx.prec = PRECISION
        principal = _parse_amount(principal_raw, "principal", "总本金")
        periods = _parse_periods(periods_raw)
        interest, payment, input_basis = _parse_amount_basis(
            mode,
            principal,
            periods,
            interest_raw,
            payment_raw,
        )
        period = _parse_period(period_value_raw, period_unit)
        concession, concession_value = _parse_concession(
            concession,
            concession_value_raw,
            periods,
        )

        original_interest = interest
        base_annual: Decimal | None = None
        if concession == "rate_discount":
            base_period = _contract_period_rate(mode, principal, interest, periods)
            discounted = base_period * concession_value / MAX_DISCOUNT
            interest = _interest_from_rate(mode, principal, discounted, periods)
            if mode in LEVEL_PAYMENT_MODES:
                payment = (principal + interest) / periods
            base_annual = base_period / period.years

        contract_period = _contract_period_rate(mode, principal, interest, periods)
        irr_period = _irr_period_rate(mode, principal, interest, periods, contract_period)

        contract_annual = contract_period / period.years
        irr_annual = irr_period / period.years
        total_years = period.years * periods

        analysis = Analysis(
            principal=principal,
            interest=interest,
            periods=periods,
            period_years=period.years,
            period_years_text=period.years_text,
            period_unit=period_unit,
            period_label=period.label,
            mode=mode,
            contract_period_rate=contract_period,
            irr_period_rate=irr_period,
            contract_annual_rate=contract_annual,
            irr_annual_rate=irr_annual,
            total_years=total_years,
            payment=payment,
            input_basis=input_basis,
            concession=concession,
            concession_value=concession_value,
            net_interest=interest,
            waived_interest=original_interest - interest,
            base_contract_annual_rate=base_annual,
        )

        if concession in SUBSIDY_CONCESSIONS:
            rows, waived = _subsidy_rows(analysis, _base_schedule_rows(analysis))
            net_interest = interest - waived
            flows = [principal_part + interest_part for principal_part, interest_part in rows]
            discounted_period = _irr_period_from_flows(principal, flows)
            analysis = replace(
                analysis,
                net_interest=net_interest,
                waived_interest=waived,
                irr_period_rate=discounted_period,
                irr_annual_rate=discounted_period / period.years,
            )

    return analysis


def _parse_amount_basis(
    mode: str,
    principal: Decimal,
    periods: int,
    interest_raw: str | None,
    payment_raw: str | None,
) -> tuple[Decimal, Decimal | None, str]:
    """Resolve the (总利息, 每期还款) pair for the mode's input convention.

    Level-payment modes accept either quantity; the other is derived. Remaining
    modes have no single per-period payment, so only 总利息 is meaningful.
    """
    has_interest = _has_value(interest_raw)
    has_payment = _has_value(payment_raw)

    if mode not in LEVEL_PAYMENT_MODES:
        if has_payment:
            raise InputError("payment", "该还款方式只支持输入总利息")
        return _parse_amount(interest_raw, "interest", "总利息", allow_zero=True), None, "interest"

    if has_interest and has_payment:
        raise InputError("payment", "总利息与每期还款只需填写一项")
    if not has_interest and not has_payment:
        raise InputError("interest", "请输入总利息或每期还款额")

    if has_payment:
        payment = _parse_amount(payment_raw, "payment", "每期还款")
        interest = payment * periods - principal
        if interest < 0:
            raise InputError("payment", "每期还款低于平均本金，无法得到非负总利息")
        if interest > MAX_AMOUNT:
            raise InputError("payment", "折算总利息超出可计算范围")
        return interest, payment, "payment"

    interest = _parse_amount(interest_raw, "interest", "总利息", allow_zero=True)
    return interest, (principal + interest) / periods, "interest"


def _has_value(raw: str | None) -> bool:
    return raw is not None and _clean_text(raw) != ""


def _parse_concession(
    concession: str,
    raw: str | None,
    periods: int,
) -> tuple[str, Decimal | None]:
    """Validate the concession type and its single parameter."""
    if concession not in CONCESSIONS:
        raise InputError("concession", "利息优惠方式无效")
    if concession in ("none", "full_waiver"):
        return concession, None

    if concession == "first_periods":
        value = _parse_decimal(
            raw,
            "concession_value",
            "免息期数",
            allow_fraction=False,
            allow_zero=False,
        )
        if value != value.to_integral_value() or value > periods:
            raise InputError("concession_value", f"免息期数需在 1–{periods} 之间")
        return concession, value

    if concession == "amount":
        return concession, _parse_amount(raw, "concession_value", "减免金额")

    value = _parse_decimal(
        raw,
        "concession_value",
        "折扣",
        allow_fraction=False,
        allow_zero=False,
    )
    if value > MAX_DISCOUNT:
        raise InputError("concession_value", f"折扣需在 0–{MAX_DISCOUNT} 折之间")
    return concession, value


def to_response(analysis: Analysis) -> dict[str, object]:
    """Render an analysis as JSON-safe strings for the web UI."""
    with localcontext() as ctx:
        ctx.prec = PRECISION
        contract_annual_value = _percent_value(analysis.contract_annual_rate)
        contract_period_value = _percent_value(analysis.contract_period_rate)
        irr_annual_value = _percent_value(analysis.irr_annual_rate)
        contract_annual = _format_percent(contract_annual_value)
        contract_period = _format_percent(contract_period_value)
        irr_annual = _format_percent(irr_annual_value)
        relation = _relation(contract_annual_value, irr_annual_value)
        schedule, schedule_total = _build_schedule(analysis)
        concession = _concession_info(analysis, contract_annual)
        # A waiver breaks the level payment a subsidy trims, so it is no longer
        # a single per-period amount.
        level_payment = analysis.payment
        if analysis.concession in SUBSIDY_CONCESSIONS:
            level_payment = None

        return {
            "mode": analysis.mode,
            "input_basis": analysis.input_basis,
            "payment": _money(level_payment) if level_payment is not None else None,
            "contract_annual_rate": _rate(analysis.contract_annual_rate),
            "contract_annual_rate_percent": contract_annual,
            "contract_period_rate": _rate(analysis.contract_period_rate),
            "contract_period_rate_percent": contract_period,
            "irr_annual_rate": _rate(analysis.irr_annual_rate),
            "irr_annual_rate_percent": irr_annual,
            "irr_relation": relation,
            "total_years": _compact(analysis.total_years),
            "period_label": analysis.period_label,
            "formula": _build_formula(analysis, contract_annual, contract_period),
            "note": _build_note(analysis.mode, relation, analysis.concession),
            "concession": concession,
            "schedule": schedule,
            "schedule_total": schedule_total,
        }


@dataclass(frozen=True, slots=True)
class _Period:
    years: Decimal
    years_text: str
    label: str


def _parse_period(raw: str, unit: str) -> _Period:
    value = _parse_decimal(
        raw,
        "period_value",
        "每期时长",
        allow_fraction=True,
        allow_zero=False,
    )
    years = value if unit == "year" else value / _PERIOD_DENOMINATORS[unit]
    if years > MAX_PERIOD_YEARS:
        raise InputError(
            "period_value",
            f"每期时长折合不能超过 {MAX_PERIOD_YEARS} 年",
        )

    raw_text = _clean_text(raw)
    value_text = raw_text if len(raw_text) <= 16 else _compact(value)
    label = f"{value_text} {PERIOD_UNIT_LABELS[unit]}"

    if unit == "year":
        years_text = _compact(years)
    elif value == value.to_integral_value():
        whole = int(value)
        denominator = _PERIOD_DENOMINATORS[unit]
        if whole % denominator == 0:
            years_text = str(whole // denominator)
        else:
            years_text = f"{whole}/{denominator}"
    else:
        years_text = _compact(years)

    return _Period(years=years, years_text=years_text, label=label)


def _build_schedule(
    analysis: Analysis,
) -> tuple[list[dict[str, str | int]], dict[str, str]]:
    """Build a cent-reconciled per-period contract cash-flow table.

    Rows are rounded to cents, with the last period absorbing the residual.
    If that residual is negative (possible with very small amounts and many
    periods), cumulative rounding is used instead. Principal and interest
    columns therefore sum exactly to the contract totals.
    """
    exact_rows = _exact_schedule_rows(analysis)
    total_principal_cents = _to_cents(analysis.principal)
    total_interest_cents = _to_cents(_net_interest(analysis))
    count = len(exact_rows)

    principal_parts = [principal for principal, _ in exact_rows]
    interest_parts = [interest for _, interest in exact_rows]

    if count == 1:
        principal_cents = [total_principal_cents]
        interest_cents = [total_interest_cents]
    else:
        principal_first = [_to_cents(value) for value in principal_parts[:-1]]
        interest_first = [_to_cents(value) for value in interest_parts[:-1]]
        last_principal = total_principal_cents - sum(principal_first)
        last_interest = total_interest_cents - sum(interest_first)

        if last_principal < 0 or last_interest < 0:
            principal_cents = _allocate_cumulative(principal_parts, total_principal_cents)
            interest_cents = _allocate_cumulative(interest_parts, total_interest_cents)
        else:
            principal_cents = [*principal_first, last_principal]
            interest_cents = [*interest_first, last_interest]

    rows: list[dict[str, str | int]] = []
    allocated_principal = 0
    for index in range(count):
        row_principal_cents = principal_cents[index]
        row_interest_cents = interest_cents[index]
        allocated_principal += row_principal_cents
        rows.append(
            {
                "period": index + 1,
                "payment": _cents_money(row_principal_cents + row_interest_cents),
                "principal": _cents_money(row_principal_cents),
                "interest": _cents_money(row_interest_cents),
                "balance": _cents_money(total_principal_cents - allocated_principal),
            }
        )

    totals = {
        "payment": _cents_money(total_principal_cents + total_interest_cents),
        "principal": _cents_money(total_principal_cents),
        "interest": _cents_money(total_interest_cents),
    }
    return rows, totals


def _allocate_cumulative(values: list[Decimal], total_cents: int) -> list[int]:
    out: list[int] = []
    cumulative = Decimal(0)
    allocated = 0
    for index, value in enumerate(values):
        cumulative += value
        if index < len(values) - 1:
            cents = _to_cents(cumulative) - allocated
        else:
            cents = total_cents - allocated
        out.append(cents)
        allocated += cents
    return out


def _exact_schedule_rows(analysis: Analysis) -> list[tuple[Decimal, Decimal]]:
    """Return exact (principal, interest) pairs after any interest concession."""
    rows = _base_schedule_rows(analysis)
    if analysis.concession in SUBSIDY_CONCESSIONS:
        rows, _ = _subsidy_rows(analysis, rows)
    return rows


def _base_schedule_rows(analysis: Analysis) -> list[tuple[Decimal, Decimal]]:
    """Return exact (principal, interest) pairs under the contract as written."""
    principal = analysis.principal
    interest = analysis.interest
    periods = analysis.periods
    rate = analysis.contract_period_rate
    rows: list[tuple[Decimal, Decimal]] = []

    if analysis.mode == "simple_bullet":
        rows.extend((Decimal(0), Decimal(0)) for _ in range(periods - 1))
        rows.append((principal, interest))
        return rows

    if analysis.mode == "interest_only":
        per_interest = principal * rate
        rows.extend((Decimal(0), per_interest) for _ in range(periods - 1))
        rows.append((principal, per_interest))
        return rows

    if analysis.mode == "equal_installment":
        payment = (principal + interest) / periods
        balance = principal
        for number in range(1, periods + 1):
            row_interest = balance * rate
            row_principal = balance if number == periods else payment - row_interest
            rows.append((row_principal, row_interest))
            balance -= row_principal
        return rows

    if analysis.mode == "flat_rate":
        per_interest = principal * rate
        per_principal = principal / periods
        for _ in range(periods):
            rows.append((per_principal, per_interest))
        return rows

    per_principal = principal / periods
    balance = principal
    for number in range(1, periods + 1):
        row_interest = balance * rate
        row_principal = balance if number == periods else per_principal
        rows.append((row_principal, row_interest))
        balance -= row_principal
    return rows


def _subsidy_rows(
    analysis: Analysis,
    rows: list[tuple[Decimal, Decimal]],
) -> tuple[list[tuple[Decimal, Decimal]], Decimal]:
    """Trim interest from the contract rows and report the waived total."""
    interest = analysis.interest
    periods = analysis.periods

    if analysis.concession == "full_waiver":
        return [(principal, Decimal(0)) for principal, _ in rows], interest

    if analysis.concession == "first_periods":
        count = int(analysis.concession_value)
        if analysis.mode == "simple_bullet":
            # Bullet interest accrues across the term and is settled at maturity.
            net = interest * (periods - count) / periods
            return [
                (principal, net if index == periods - 1 else Decimal(0))
                for index, (principal, _) in enumerate(rows)
            ], interest - net
        waived = sum((row_interest for _, row_interest in rows[:count]), Decimal(0))
        waived = min(waived, interest)
        return [
            (principal, Decimal(0) if index < count else row_interest)
            for index, (principal, row_interest) in enumerate(rows)
        ], waived

    amount = analysis.concession_value
    if interest == 0 or amount >= interest:
        return [(principal, Decimal(0)) for principal, _ in rows], interest
    factor = (interest - amount) / interest
    trimmed = [(principal, row_interest * factor) for principal, row_interest in rows]
    return trimmed, amount


def _net_interest(analysis: Analysis) -> Decimal:
    return analysis.interest if analysis.net_interest is None else analysis.net_interest


def _to_cents(value: Decimal) -> int:
    return int((value * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def _cents_money(cents: int) -> str:
    return f"{Decimal(cents) / 100:,.2f}"


def _contract_period_rate(
    mode: str,
    principal: Decimal,
    interest: Decimal,
    periods: int,
) -> Decimal:
    if mode == "equal_installment":
        return _solve_level_payment_rate(principal, interest, periods)
    if mode == "equal_principal":
        return (2 * interest) / (principal * (periods + 1))
    return interest / (principal * periods)


def _irr_period_rate(
    mode: str,
    principal: Decimal,
    interest: Decimal,
    periods: int,
    contract_period: Decimal,
) -> Decimal:
    if mode == "flat_rate":
        return _solve_level_payment_rate(principal, interest, periods)
    if mode == "simple_bullet":
        return _compound_period_rate(principal, interest, periods)
    return contract_period


def _interest_from_rate(
    mode: str,
    principal: Decimal,
    rate: Decimal,
    periods: int,
) -> Decimal:
    """Total interest a mode would charge at the given period rate."""
    if mode == "equal_installment":
        if rate == 0:
            return Decimal(0)
        payment = principal * rate / (1 - (1 + rate) ** (-periods))
        return payment * periods - principal
    if mode == "equal_principal":
        return principal * rate * (periods + 1) / 2
    return principal * rate * periods


def _solve_level_payment_rate(
    principal: Decimal,
    interest: Decimal,
    periods: int,
) -> Decimal:
    """Solve the level-payment annuity equation for the period IRR."""
    if interest == 0:
        return Decimal(0)

    payment = (principal + interest) / periods

    def pv_minus_principal(rate: Decimal) -> Decimal:
        if rate == 0:
            return payment * periods - principal
        return payment * (1 - (1 + rate) ** (-periods)) / rate - principal

    low = Decimal(0)
    high = Decimal(1)
    guard = 0
    while pv_minus_principal(high) > 0:
        high *= 2
        guard += 1
        if guard > 200:
            raise InputError("interest", "本金与利息的比例过大，无法计算可靠年化")

    for _ in range(200):
        mid = (low + high) / 2
        if mid <= low or mid >= high:
            break
        if pv_minus_principal(mid) > 0:
            low = mid
        else:
            high = mid

    return (low + high) / 2


def _irr_period_from_flows(principal: Decimal, flows: list[Decimal]) -> Decimal:
    """Solve the period IRR of an arbitrary payment vector."""
    total = sum(flows, Decimal(0))
    if total <= principal:
        return Decimal(0)

    def pv_minus_principal(rate: Decimal) -> Decimal:
        if rate == 0:
            return total - principal
        factor = 1 / (1 + rate)
        power = Decimal(1)
        present = Decimal(0)
        for flow in flows:
            power *= factor
            present += flow * power
        return present - principal

    low = Decimal(0)
    high = Decimal(1)
    guard = 0
    while pv_minus_principal(high) > 0:
        high *= 2
        guard += 1
        if guard > 200:
            raise InputError("concession", "本金与利息的比例过大，无法计算可靠年化")

    for _ in range(200):
        mid = (low + high) / 2
        if mid <= low or mid >= high:
            break
        if pv_minus_principal(mid) > 0:
            low = mid
        else:
            high = mid

    return (low + high) / 2


def _compound_period_rate(
    principal: Decimal,
    interest: Decimal,
    periods: int,
) -> Decimal:
    """Periodic compound rate of a single bullet repayment at maturity."""
    if interest == 0:
        return Decimal(0)
    growth = 1 + interest / principal
    return growth ** (Decimal(1) / periods) - 1


def _concession_info(analysis: Analysis, contract_annual: str) -> dict[str, object]:
    net = _net_interest(analysis)
    label, detail = _concession_text(analysis, net, analysis.waived_interest, contract_annual)
    base = analysis.base_contract_annual_rate
    return {
        "type": analysis.concession,
        "label": label,
        "detail": detail,
        "waived_interest": _money(analysis.waived_interest),
        "net_interest": _money(net),
        "base_annual_rate_percent": (
            _format_percent(_percent_value(base)) if base is not None else None
        ),
    }


def _concession_text(
    analysis: Analysis,
    net: Decimal,
    waived: Decimal,
    contract_annual: str,
) -> tuple[str, str]:
    kind = analysis.concession
    if kind == "none":
        return "", ""

    waived_text = _money(waived)
    net_text = _money(net)

    if kind == "full_waiver":
        return "全额免息", f"减免全部利息 {waived_text} 元，只归还本金"

    if kind == "first_periods":
        count = _compact(analysis.concession_value)
        detail = f"减免利息 {waived_text} 元，实际总利息 {net_text} 元"
        if analysis.mode == "simple_bullet":
            detail += "（该方式利息到期一次结清，按计息期数折算）"
        return f"前 {count} 期免息", detail

    if kind == "amount":
        requested = _money(analysis.concession_value)
        if analysis.concession_value >= analysis.interest:
            return f"减免 {requested} 元", f"超过总利息，按全额免息处理（减免 {waived_text} 元）"
        return f"减免 {requested} 元", f"按各期利息占比摊薄，实际总利息 {net_text} 元"

    base = analysis.base_contract_annual_rate
    base_text = _format_percent(_percent_value(base)) if base is not None else "—"
    return (
        f"利率 {_compact(analysis.concession_value)} 折",
        f"合同年化 {base_text}% → {contract_annual}%，减免利息 {waived_text} 元",
    )


def _build_formula(
    analysis: Analysis,
    contract_annual: str,
    contract_period: str,
) -> str:
    formula = _rate_formula(analysis, contract_annual, contract_period)
    if analysis.concession == "none":
        return formula
    net = _net_interest(analysis)
    label, _ = _concession_text(analysis, net, analysis.waived_interest, contract_annual)
    return (
        f"{formula}\n优惠：{label}"
        f"（减免利息 {_money(analysis.waived_interest)} 元，实际总利息 {_money(net)} 元）"
    )


def _rate_formula(
    analysis: Analysis,
    contract_annual: str,
    contract_period: str,
) -> str:
    principal = _amount_text(analysis.principal)
    from_payment = analysis.input_basis == "payment"
    as_text = _money_exact if from_payment else _amount_text
    interest = as_text(analysis.interest)
    years = analysis.period_years_text

    if analysis.mode == "equal_installment":
        if from_payment:
            payment_text = as_text(analysis.payment)
            head = (
                f"每期还款 A = {payment_text}（输入）\n"
                "总利息 = 期数 × 每期还款 − 本金\n"
                f"  = {analysis.periods} × {payment_text} − {principal} = {interest}\n"
            )
        else:
            payment_text = _money((analysis.principal + analysis.interest) / analysis.periods)
            head = (
                "每期还款 A = (本金 + 总利息) ÷ 期数\n"
                f"  = ({principal} + {interest}) ÷ {analysis.periods} = {payment_text}\n"
            )
        return head + (
            "解 P = A × [1 − (1 + r)^-n] ÷ r\n"
            f"  （P = {principal}，n = {analysis.periods}）\n"
            f"解得期利率 r ≈ {contract_period}%\n"
            f"年化单利 = r ÷ {years} ≈ {contract_annual}%"
        )

    if analysis.mode == "equal_principal":
        return (
            "年化单利 = 2 × 总利息 ÷ (本金 × (期数 + 1) × 每期年数)\n"
            f"  = 2 × {interest} ÷ "
            f"({principal} × {analysis.periods + 1} × {years})\n"
            f"  ≈ {contract_annual}%"
        )

    if analysis.mode == "interest_only":
        return (
            "年化单利 = 总利息 ÷ (本金 × 期数 × 每期年数)\n"
            f"  = {interest} ÷ ({principal} × {analysis.periods} × {years})\n"
            f"  ≈ {contract_annual}%"
        )

    if analysis.mode == "flat_rate":
        lines = []
        if from_payment:
            payment = as_text(analysis.payment)
            lines.append(f"每期还款 A = {payment}（输入）")
            lines.append("总利息 = 期数 × 每期还款 − 本金")
            lines.append(f"  = {analysis.periods} × {payment} − {principal} = {interest}")
        lines.extend(
            [
                "期费率 = 总利息 ÷ (本金 × 期数)",
                f"  = {interest} ÷ ({principal} × {analysis.periods}) = {contract_period}%",
                f"合同年化单利 = 期费率 ÷ {years} ≈ {contract_annual}%",
            ]
        )
        if not from_payment:
            payment = _money((analysis.principal + analysis.interest) / analysis.periods)
            lines.append(f"每期还款 = 本金 ÷ 期数 + 每期利息 = {payment}")
        return "\n".join(lines)

    total_due = _money(analysis.principal + analysis.interest)
    return (
        "期利率 = 总利息 ÷ (本金 × 期数)\n"
        f"  = {interest} ÷ ({principal} × {analysis.periods}) = {contract_period}%\n"
        f"合同年化单利 = 期利率 ÷ {years} ≈ {contract_annual}%\n"
        f"到期本息合计 = 本金 + 总利息 = {total_due}"
    )


def _build_note(mode: str, relation: str, concession: str = "none") -> str:
    if concession in SUBSIDY_CONCESSIONS and relation == "lower":
        return (
            "合同利率不变，利息优惠只减少实际收取的利息；"
            "按优惠后现金流反解，实际 IRR 低于合同口径。"
        )
    if mode == "equal_installment":
        return "每期还款额固定，期利率由年金方程数值解出；现金流 IRR 与合同年化一致。"
    if mode == "equal_principal":
        return "本金逐期等额摊还，利息按剩余本金计；现金流 IRR 与合同年化一致。"
    if mode == "interest_only":
        return "每期按全额本金付息、期末归还本金；现金流 IRR 与合同年化一致。"
    if mode == "flat_rate":
        if relation == "higher":
            return "本金逐期平摊，但利息始终按原始本金收取；实际 IRR 高于合同费率。"
        if relation == "lower":
            return "本金逐期平摊，但利息始终按原始本金收取；实际 IRR 低于合同费率。"
        return "本金逐期平摊，但利息始终按原始本金收取；当前期数下实际 IRR 与合同费率一致。"
    if relation == "lower":
        return "利息与本金到期一次结清；利息收取更晚，按现金流反解的 IRR 名义年化低于合同单利。"
    if relation == "higher":
        return "利息与本金到期一次结清；按现金流反解的 IRR 名义年化高于合同单利。"
    return "利息与本金到期一次结清；当前期数下实际 IRR 与合同单利一致。"


def _relation(contract: Decimal, irr: Decimal) -> str:
    if irr > contract:
        return "higher"
    if irr < contract:
        return "lower"
    return "equal"


def _clean_text(raw: str) -> str:
    return re.sub(r"[\s,，]", "", raw)


def _parse_decimal(
    raw: str | None,
    field: str,
    label: str,
    *,
    allow_fraction: bool,
    allow_zero: bool,
) -> Decimal:
    if raw is None:
        raise InputError(field, f"请输入{label}")
    if not isinstance(raw, str) or len(raw) > MAX_RAW_LENGTH:
        raise InputError(field, f"{label}格式不正确")
    text = _clean_text(raw)
    if not text:
        raise InputError(field, f"请输入{label}")

    if "/" in text:
        if not allow_fraction:
            raise InputError(field, f"{label}格式不正确")
        parts = text.split("/")
        if len(parts) != 2 or not all(parts):
            raise InputError(field, "请输入有效数字或分数，如 1/12")
        try:
            numerator = Decimal(parts[0])
            denominator = Decimal(parts[1])
        except InvalidOperation as exc:
            raise InputError(field, "请输入有效数字或分数，如 1/12") from exc
        if not numerator.is_finite() or not denominator.is_finite() or denominator == 0:
            raise InputError(field, "请输入有效数字或分数，如 1/12")
        value = numerator / denominator
    else:
        try:
            value = Decimal(text)
        except InvalidOperation as exc:
            message = "请输入有效数字或分数，如 1/12" if allow_fraction else f"{label}格式不正确"
            raise InputError(field, message) from exc
        if not value.is_finite():
            raise InputError(field, f"{label}格式不正确")

    if value < 0:
        message = f"{label}不能为负" if allow_zero else f"{label}必须大于 0"
        raise InputError(field, message)
    if value == 0 and not allow_zero:
        raise InputError(field, f"{label}必须大于 0")
    return value


def _parse_amount(
    raw: str | None,
    field: str,
    label: str,
    *,
    allow_zero: bool = False,
) -> Decimal:
    value = _parse_decimal(
        raw,
        field,
        label,
        allow_fraction=False,
        allow_zero=allow_zero,
    )
    if value > MAX_AMOUNT:
        raise InputError(field, f"{label}超出可计算范围")
    return value


def _parse_periods(raw: str) -> int:
    if not isinstance(raw, str) or len(raw) > MAX_RAW_LENGTH:
        raise InputError("periods", "总期数必须为正整数")
    text = _clean_text(raw)
    if not text:
        raise InputError("periods", "请输入总期数")
    if re.fullmatch(r"[0-9]+", text) is None:
        raise InputError("periods", "总期数必须为正整数")
    periods = int(text)
    if not 1 <= periods <= MAX_PERIODS:
        raise InputError("periods", f"总期数需在 1–{MAX_PERIODS} 之间")
    return periods


def _percent_value(value: Decimal) -> Decimal:
    return (value * 100).quantize(_PERCENT_QUANTUM, rounding=ROUND_HALF_UP)


def _format_percent(value: Decimal) -> str:
    return f"{value:,.4f}"


def _rate(value: Decimal) -> str:
    rounded = value.quantize(_RATE_QUANTUM, rounding=ROUND_HALF_UP)
    return f"{rounded:f}"


def _amount_text(value: Decimal) -> str:
    integer, dot, fraction = f"{value:f}".partition(".")
    grouped = f"{int(integer):,}"
    return f"{grouped}{dot}{fraction}"


def _money(value: Decimal) -> str:
    rounded = value.quantize(_MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    return f"{rounded:,.2f}"


def _money_exact(value: Decimal) -> str:
    """Group a derived amount as money without rounding away real precision."""
    text = f"{value:f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    integer, _, fraction = text.partition(".")
    return f"{int(integer):,}.{fraction.ljust(2, '0')}"


def _compact(value: Decimal) -> str:
    rounded = value.quantize(_YEARS_QUANTUM, rounding=ROUND_HALF_UP)
    text = f"{rounded:f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text or "0"
