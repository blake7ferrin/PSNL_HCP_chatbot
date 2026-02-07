"""Centralized money formatting. All amounts must go through format_money; no inline $ formatting."""
import logging
import os
from decimal import Decimal
from typing import Any, Union

logger = logging.getLogger(__name__)
DEBUG = os.environ.get("DEBUG", "").strip().lower() in ("1", "true", "yes")

# Suspicious: int >= 100_000_00 cents = $1,000,000 — might be dollars passed as int
SUSPICIOUS_CENTS_THRESHOLD = 100_000_00


def safe_float_or_decimal(value: Any) -> Union[float, Decimal, None]:
    """Parse value to float or Decimal if possible; otherwise None."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, Decimal):
        return value
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return None
        try:
            return Decimal(s)
        except Exception:
            try:
                return float(s)
            except ValueError:
                return None
    return None


def coerce_money_to_dollars(value: Any) -> Decimal:
    """
    Convert API value to dollars as Decimal.
    - int: assume cents (e.g. 1188700 -> 11887.00)
    - float: assume dollars (e.g. 11887.0)
    - str / Decimal: parse as decimal (assume dollars if looks like "11887.00")
    """
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        # Explicit decimal places (e.g. 11887.00 from JSON) -> dollars
        if value.as_tuple().exponent < 0:
            return value
        if value == value.to_integral_value() and value >= 100:
            return value / 100
        return value
    if isinstance(value, int):
        # HCP typically sends amounts in cents
        if value >= SUSPICIOUS_CENTS_THRESHOLD:
            logger.warning(
                "formatting: large int value %s might be dollars not cents; treating as cents",
                value,
            )
        if DEBUG:
            logger.debug("formatting: int value %s (type int) -> cents -> %s dollars", value, Decimal(value) / 100)
        return Decimal(value) / 100
    if isinstance(value, float):
        # API may serialize cents as float (e.g. 1188700.0); treat as cents only if whole and large (>= 100000 = $1000)
        if value >= 100_000 and value == int(value):
            if DEBUG:
                logger.debug("formatting: float value %s (whole number >= 100000) -> cents -> %s dollars", value, Decimal(value) / 100)
            return Decimal(value) / 100
        return Decimal(str(value))
    if isinstance(value, str):
        s = value.strip()
        if not s:
            return Decimal("0")
        parsed = safe_float_or_decimal(s)
        if parsed is None:
            return Decimal("0")
        if isinstance(parsed, Decimal):
            # String with decimal point -> dollars; without -> cents (e.g. "100" = $1.00)
            if "." not in s:
                return parsed / 100
            return parsed
        return Decimal(str(parsed))
    return Decimal("0")


def format_money(value: Any) -> str:
    """
    Format any money value as "${dollars:,.2f}".
    Accepts int (cents), float (dollars or cents if whole >= 1000), str, Decimal.
    None or invalid -> "$0.00".
    """
    if DEBUG and value is not None:
        logger.debug("format_money: raw value=%s type=%s", value, type(value).__name__)
    dollars = coerce_money_to_dollars(value)
    return f"${dollars:,.2f}"
