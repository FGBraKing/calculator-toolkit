"""Shared amortization helpers for mortgage-style loans."""

from __future__ import annotations

from decimal import Decimal

METHODS = ("equal_installment", "equal_principal")


def level_payment(principal: Decimal, rate: Decimal, months: int) -> Decimal:
    """Monthly payment of a level-payment annuity."""
    if rate == 0:
        return principal / months
    factor = (1 + rate) ** months
    return principal * rate * factor / (factor - 1)


def level_rows(
    principal: Decimal,
    rate: Decimal,
    months: int,
    payment: Decimal,
) -> list[tuple[Decimal, Decimal]]:
    rows: list[tuple[Decimal, Decimal]] = []
    balance = principal
    for number in range(1, months + 1):
        interest = balance * rate
        principal_part = balance if number == months else payment - interest
        rows.append((principal_part, interest))
        balance -= principal_part
    return rows


def principal_rows(
    principal: Decimal,
    rate: Decimal,
    months: int,
) -> list[tuple[Decimal, Decimal]]:
    per_principal = principal / months
    rows: list[tuple[Decimal, Decimal]] = []
    balance = principal
    for number in range(1, months + 1):
        interest = balance * rate
        principal_part = balance if number == months else per_principal
        rows.append((principal_part, interest))
        balance -= principal_part
    return rows


def rows_for(
    principal: Decimal,
    rate: Decimal,
    months: int,
    method: str,
) -> tuple[list[tuple[Decimal, Decimal]], Decimal]:
    """Return exact rows and the level payment (zero for 等额本金)."""
    if method == "equal_installment":
        payment = level_payment(principal, rate, months)
        return level_rows(principal, rate, months, payment), payment
    if method == "equal_principal":
        return principal_rows(principal, rate, months), Decimal(0)
    raise ValueError(method)
