"""Server-side input parsing helpers.

Every helper returns ``(value, error)``. ``error`` is ``None`` when the input is
valid. Helpers never silently repair bad input (for example they never replace an
invalid date with today's date).
"""

from __future__ import annotations

import re
from datetime import date, datetime

MAX_QUANTITY = 1_000_000_000
MIN_YEAR = 1900
MAX_YEAR = 2100

_DIGITS = re.compile(r"^[0-9]+$")
_NEGATIVE_NUMBER = re.compile(r"^-\s*[0-9]+([.,][0-9]+)?$")

# Field length limits (also used by the HTML maxlength attributes).
LIMITS = {
    "code": 40,
    "reference": 120,
    "label": 80,
    "unit": 30,
    "person": 120,
    "name": 100,
    "short_text": 500,
    "long_text": 2000,
}


def clean_text(
    raw: str | None, *, label: str, max_length: int, required: bool = False
) -> tuple[str | None, str | None]:
    """Trim text. Empty optional text becomes ``None`` (NULL), never an empty string."""
    value = (raw or "").strip()
    if not value:
        return (None, f"{label} is required.") if required else (None, None)
    if len(value) > max_length:
        return None, f"{label} must be at most {max_length} characters."
    return value, None


def parse_whole_number(
    raw: str | None,
    *,
    label: str,
    minimum: int = 1,
    required: bool = True,
    maximum: int = MAX_QUANTITY,
) -> tuple[int | None, str | None]:
    """Parse a whole-number quantity (discrete count)."""
    text = (raw or "").strip()
    if not text:
        if required:
            return None, f"{label} is required."
        return None, None
    if _NEGATIVE_NUMBER.match(text):
        if minimum <= 0:
            return None, f"{label} must not be negative."
        return None, f"{label} must be greater than zero."
    if not _DIGITS.match(text):
        return None, f"{label} must be a whole number using digits only (no decimals or text)."
    number = int(text)
    if number < minimum:
        if minimum <= 0:
            return None, f"{label} must not be negative."
        return None, f"{label} must be greater than zero."
    if number > maximum:
        return None, f"{label} must not exceed {maximum:,}."
    return number, None


def parse_date_value(
    raw: str | None, *, label: str, required: bool = True
) -> tuple[date | None, str | None]:
    """Parse an ISO date (YYYY-MM-DD), as submitted by <input type="date">."""
    text = (raw or "").strip()
    if not text:
        return (None, f"{label} is required.") if required else (None, None)
    try:
        parsed = datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None, f"{label} must be a valid date in YYYY-MM-DD format."
    if not MIN_YEAR <= parsed.year <= MAX_YEAR:
        return None, f"{label} must be between the years {MIN_YEAR} and {MAX_YEAR}."
    return parsed, None


def normalise_unit(raw: str | None, *, label: str = "Unit") -> tuple[str | None, str | None]:
    """Units are trimmed and lower-cased so that 'Pieces' and 'pieces' group together."""
    value, error = clean_text(raw, label=label, max_length=LIMITS["unit"], required=True)
    if error:
        return None, error
    return value.lower(), None


def escape_like(value: str) -> str:
    """Escape LIKE wildcards so user text is matched literally (use with escape='\\')."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def parse_page(raw: str | None) -> int:
    """Parse a page number from the query string; invalid input means page 1."""
    try:
        page = int((raw or "1").strip())
    except ValueError:
        return 1
    return page if page >= 1 else 1


def parse_optional_id(raw: str | None) -> int | None:
    """Parse an optional numeric identifier; blank or invalid returns ``None``."""
    text = (raw or "").strip()
    if text.isascii() and text.isdigit():
        return int(text)
    return None
