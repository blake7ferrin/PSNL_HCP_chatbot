"""Tests for centralized money formatting (src.utils.formatting)."""
import pytest
from decimal import Decimal

from src.utils.formatting import format_money, coerce_money_to_dollars, safe_float_or_decimal


def test_int_cents_to_dollars():
    assert format_money(1188700) == "$11,887.00"
    assert coerce_money_to_dollars(1188700) == Decimal("11887.00")


def test_float_dollars():
    assert format_money(11887.0) == "$11,887.00"
    assert format_money(11887.5) == "$11,887.50"


def test_float_cents_when_large_whole():
    # API may send cents as float 1188700.0
    assert format_money(1188700.0) == "$11,887.00"


def test_str_dollars():
    assert format_money("11887.00") == "$11,887.00"
    # String with no decimal and >= 1000 treated as cents (API convention)
    assert format_money("11887") == "$118.87"
    assert format_money("100") == "$1.00"  # 100 cents


def test_zero_and_none():
    assert format_money(0) == "$0.00"
    assert format_money(None) == "$0.00"
    assert coerce_money_to_dollars(0) == Decimal("0")
    assert coerce_money_to_dollars(None) == Decimal("0")


def test_decimal():
    assert format_money(Decimal("11887.00")) == "$11,887.00"
    assert format_money(Decimal("1188700")) == "$11,887.00"  # integral >= 1000 -> cents


def test_safe_float_or_decimal():
    assert safe_float_or_decimal("1.5") == Decimal("1.5")
    assert safe_float_or_decimal(1.5) == 1.5
    assert safe_float_or_decimal(None) is None
    assert safe_float_or_decimal("") is None
