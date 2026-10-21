"""Reporting helpers: rates, display text and trend period grouping."""

from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal

NOT_APPLICABLE = "Not applicable"
INTERVALS = ("day", "week", "month")
INTERVAL_LABELS = {"day": "Day", "week": "Week (Monday start)", "month": "Month"}
PERCENT_PLACES = 1


def rate_percent(numerator: int | None, denominator: int | None) -> Decimal | None:
    """Return ``numerator / denominator * 100`` rounded half-up to one decimal place.

    Returns ``None`` (displayed as "Not applicable") when either value is missing or the
    denominator is zero. Exact decimal arithmetic is used instead of floating point.
    """
    if numerator is None or denominator is None or denominator <= 0:
        return None
    value = Decimal(numerator) * Decimal(100) / Decimal(denominator)
    return value.quantize(Decimal(1).scaleb(-PERCENT_PLACES), rounding=ROUND_HALF_UP)


def format_rate(value: Decimal | None) -> str:
    return NOT_APPLICABLE if value is None else f"{value}%"


def period_key(day: date, interval: str) -> str:
    """Sortable grouping key for a date. Weeks start on Monday."""
    if interval == "day":
        return day.isoformat()
    if interval == "month":
        return f"{day.year:04d}-{day.month:02d}"
    if interval == "week":
        return (day - timedelta(days=day.weekday())).isoformat()
    raise ValueError(f"Unsupported interval: {interval}")


def period_label(key: str, interval: str) -> str:
    if interval == "week":
        return f"Week starting {key}"
    return key
