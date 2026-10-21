"""Unit tests for input parsing (INS-02..05, DEF-04/05, section 8 of the testing document)."""

from datetime import date

import pytest

from app.domain import validation as v


@pytest.mark.parametrize("raw", ["1", "100", " 25 ", "1000000000"])
def test_whole_number_accepts_positive_integers(raw):
    value, error = v.parse_whole_number(raw, label="Quantity")
    assert error is None
    assert value == int(raw.strip())


@pytest.mark.parametrize(
    ("raw", "fragment"),
    [
        ("", "required"),
        ("   ", "required"),
        ("0", "greater than zero"),
        ("-5", "greater than zero"),
        ("-3.5", "greater than zero"),
        ("abc", "whole number"),
        ("3.5", "whole number"),
        ("1e3", "whole number"),
        ("١٢٣", "whole number"),  # non-ASCII digits are rejected
        ("1000000001", "must not exceed"),
    ],
)
def test_whole_number_rejects_invalid_input(raw, fragment):
    value, error = v.parse_whole_number(raw, label="Quantity")
    assert value is None
    assert fragment in error


def test_zero_is_allowed_when_minimum_is_zero():
    assert v.parse_whole_number("0", label="Accepted quantity", minimum=0) == (0, None)


def test_negative_rejected_when_minimum_is_zero():
    value, error = v.parse_whole_number("-1", label="Accepted quantity", minimum=0)
    assert value is None
    assert "must not be negative" in error


def test_optional_blank_number_is_none_without_error():
    assert v.parse_whole_number("", label="X", required=False) == (None, None)


def test_date_parsing_valid_and_invalid():
    assert v.parse_date_value("2026-03-15", label="Date") == (date(2026, 3, 15), None)
    for bad in ["15/03/2026", "2026-13-01", "2026-02-30", "not a date", "1800-01-01"]:
        value, error = v.parse_date_value(bad, label="Date")
        assert value is None
        assert error and "Date" in error


def test_invalid_date_is_never_replaced_with_today():
    value, error = v.parse_date_value("garbage", label="Date")
    assert value is None and error is not None


def test_required_and_optional_dates():
    assert v.parse_date_value("", label="Date")[1] == "Date is required."
    assert v.parse_date_value("", label="Date", required=False) == (None, None)


def test_clean_text_trims_and_uses_none_for_blank():
    assert v.clean_text("  hello  ", label="Notes", max_length=10) == ("hello", None)
    assert v.clean_text("   ", label="Notes", max_length=10) == (None, None)


def test_clean_text_required_and_length():
    assert v.clean_text("  ", label="Product", max_length=10, required=True)[1] == (
        "Product is required."
    )
    value, error = v.clean_text("x" * 11, label="Product", max_length=10)
    assert value is None and "at most 10" in error


def test_unit_is_normalised_to_lower_case():
    assert v.normalise_unit("  Pieces ") == ("pieces", None)
    assert v.normalise_unit("")[1] == "Unit is required."


def test_escape_like_escapes_wildcards():
    assert v.escape_like("50%_off\\") == "50\\%\\_off\\\\"


def test_parse_page_and_optional_id_handle_malformed_input():
    assert v.parse_page("3") == 3
    assert v.parse_page("0") == 1
    assert v.parse_page("-2") == 1
    assert v.parse_page("abc") == 1
    assert v.parse_page(None) == 1
    assert v.parse_optional_id("12") == 12
    assert v.parse_optional_id("12; DROP TABLE") is None
    assert v.parse_optional_id("") is None
