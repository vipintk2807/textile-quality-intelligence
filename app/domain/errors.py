"""Exceptions shared by the service layer and the routes."""

from __future__ import annotations


class ValidationError(Exception):
    """Input failed validation. ``errors`` maps a form field name to a message."""

    def __init__(self, errors: dict[str, str]):
        self.errors = dict(errors)
        super().__init__("; ".join(self.errors.values()) or "Validation failed.")


class NotFoundError(Exception):
    """A requested record does not exist."""


class BusinessRuleError(Exception):
    """An operation is not permitted by a business rule (the message is user-safe)."""
