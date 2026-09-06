"""Exact conversion between user-entered decimal amounts and integer minor units."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from .errors import ValidationError

_MINOR_UNIT = Decimal("0.01")


def parse_minor_units(value: str | int | Decimal, *, allow_zero: bool = False) -> int:
    """Parse a decimal amount without ever passing through binary floating point."""
    if isinstance(value, bool) or isinstance(value, float):
        raise ValidationError("amount must be provided as a decimal string, not a float")
    try:
        amount = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise ValidationError(f"invalid monetary amount: {value!r}") from None
    if not amount.is_finite():
        raise ValidationError("amount must be finite")
    if amount != amount.quantize(_MINOR_UNIT):
        raise ValidationError("V0.1 supports at most two decimal places")
    minor = int(amount * 100)
    if minor < 0 or (minor == 0 and not allow_zero):
        qualifier = "non-negative" if allow_zero else "greater than zero"
        raise ValidationError(f"amount must be {qualifier}")
    return minor


def format_minor_units(minor: int, currency: str | None = None) -> str:
    sign = "-" if minor < 0 else ""
    absolute = abs(minor)
    number = f"{sign}{absolute // 100}.{absolute % 100:02d}"
    return f"{currency} {number}" if currency else number


def normalize_currency(value: str) -> str:
    currency = value.strip().upper()
    if len(currency) != 3 or not currency.isascii() or not currency.isalpha():
        raise ValidationError("currency must be a three-letter code such as CNY or USD")
    return currency
