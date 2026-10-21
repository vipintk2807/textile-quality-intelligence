"""Disposition reconciliation (project-defined rule, not an industry formula).

For one inspection, in one unit, with mutually exclusive outcomes:

    inspected = accepted + rework + rejected + pending

All quantities are integers so there is no rounding that could hide a discrepancy.
"""

from __future__ import annotations


def disposition_total(accepted: int, rework: int, rejected: int, pending: int) -> int:
    return accepted + rework + rejected + pending


def check_disposition(
    *,
    inspected_quantity: int,
    inspected_unit: str,
    accepted: int,
    rework: int,
    rejected: int,
    pending: int,
    unit: str,
) -> list[str]:
    """Return a list of human-readable problems. An empty list means the record reconciles."""
    problems: list[str] = []
    if unit != inspected_unit:
        problems.append(
            f"The disposition unit '{unit}' does not match the inspection unit "
            f"'{inspected_unit}'. Quantities in different units cannot be reconciled."
        )
        return problems

    total = disposition_total(accepted, rework, rejected, pending)
    if total > inspected_quantity:
        problems.append(
            f"Accepted + rework + rejected + pending = {total:,} {unit}, which exceeds the "
            f"inspected quantity of {inspected_quantity:,} {unit} by "
            f"{total - inspected_quantity:,}. Reduce the entered quantities."
        )
    elif total < inspected_quantity:
        problems.append(
            f"Accepted + rework + rejected + pending = {total:,} {unit}, which is "
            f"{inspected_quantity - total:,} {unit} short of the inspected quantity of "
            f"{inspected_quantity:,} {unit}. If the outcome for the remainder is not yet "
            f"known, record it as pending."
        )
    return problems


# Derived disposition status shown in lists and filters.
DISP_NOT_RECORDED = "not_recorded"
DISP_PENDING = "pending"
DISP_RESOLVED = "resolved"
DISPOSITION_STATUS_LABELS = {
    DISP_NOT_RECORDED: "No disposition recorded",
    DISP_PENDING: "Pending quantity remains",
    DISP_RESOLVED: "Fully dispositioned",
}
