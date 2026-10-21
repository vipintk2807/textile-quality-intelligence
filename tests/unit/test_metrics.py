"""Rate and period helpers (testing document, section 7)."""

from datetime import date
from decimal import Decimal

import pytest

from app.domain.metrics import NOT_APPLICABLE, format_rate, period_key, period_label, rate_percent


def test_rate_uses_exact_decimal_arithmetic():
    assert rate_percent(10, 100) == Decimal("10.0")
    assert rate_percent(5, 100) == Decimal("5.0")
    assert rate_percent(1, 3) == Decimal("33.3")
    assert rate_percent(2, 3) == Decimal("66.7")


def test_rate_rounds_half_up():
    assert rate_percent(1, 8) == Decimal("12.5")
    assert rate_percent(1, 16) == Decimal("6.3")  # 6.25 -> 6.3 (half up)


@pytest.mark.parametrize(("num", "den"), [(5, 0), (5, None), (None, 10), (0, 0)])
def test_rate_is_not_applicable_without_valid_denominator(num, den):
    assert rate_percent(num, den) is None
    assert format_rate(rate_percent(num, den)) == NOT_APPLICABLE


def test_zero_numerator_with_valid_denominator_is_a_real_zero():
    assert rate_percent(0, 50) == Decimal("0.0")
    assert format_rate(Decimal("0.0")) == "0.0%"


def test_period_keys():
    d = date(2026, 10, 18)  # Sunday
    assert period_key(d, "day") == "2026-10-18"
    assert period_key(d, "month") == "2026-10"
    assert period_key(d, "week") == "2026-10-12"  # Monday of that week
    assert period_key(date(2026, 10, 12), "week") == "2026-10-12"
    assert period_label("2026-10-12", "week") == "Week starting 2026-10-12"
    with pytest.raises(ValueError):
        period_key(d, "year")
