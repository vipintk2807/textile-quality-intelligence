"""Corrective-action status model and transition rules.

Completion of an action is deliberately separate from an assessment that it was
effective: ``EFFECTIVE`` and ``NOT_EFFECTIVE`` need a recorded follow-up assessment.
"""

from __future__ import annotations

from datetime import date

OPEN = "open"
IN_PROGRESS = "in_progress"
COMPLETED = "completed_awaiting_followup"
EFFECTIVE = "effective"
NOT_EFFECTIVE = "not_effective"
CLOSED = "closed"

STATUSES = (OPEN, IN_PROGRESS, COMPLETED, EFFECTIVE, NOT_EFFECTIVE, CLOSED)

STATUS_LABELS = {
    OPEN: "Open",
    IN_PROGRESS: "In progress",
    COMPLETED: "Completed awaiting follow-up",
    EFFECTIVE: "Effective",
    NOT_EFFECTIVE: "Not effective",
    CLOSED: "Closed",
}

# Permitted next statuses (technical specification, section 8).
TRANSITIONS: dict[str, frozenset[str]] = {
    OPEN: frozenset({IN_PROGRESS, COMPLETED}),
    IN_PROGRESS: frozenset({OPEN, COMPLETED}),
    COMPLETED: frozenset({EFFECTIVE, NOT_EFFECTIVE, IN_PROGRESS}),
    EFFECTIVE: frozenset({CLOSED, IN_PROGRESS}),
    NOT_EFFECTIVE: frozenset({IN_PROGRESS, OPEN}),
    CLOSED: frozenset(),
}

FOLLOWUP_EFFECTIVE = "effective"
FOLLOWUP_NOT_EFFECTIVE = "not_effective"
FOLLOWUP_INCONCLUSIVE = "inconclusive"
FOLLOWUP_RESULTS = (FOLLOWUP_EFFECTIVE, FOLLOWUP_NOT_EFFECTIVE, FOLLOWUP_INCONCLUSIVE)
FOLLOWUP_LABELS = {
    FOLLOWUP_EFFECTIVE: "Effective",
    FOLLOWUP_NOT_EFFECTIVE: "Not effective",
    FOLLOWUP_INCONCLUSIVE: "Inconclusive",
}

# Statuses in which a deadline can still be missed.
OVERDUE_ELIGIBLE = frozenset({OPEN, IN_PROGRESS})
# Moving to these statuses clears a previously recorded completion date.
REOPEN_TARGETS = frozenset({OPEN, IN_PROGRESS})


def status_label(status: str) -> str:
    return STATUS_LABELS.get(status, status)


def permitted_next(status: str) -> list[str]:
    """Permitted next statuses in display order."""
    allowed = TRANSITIONS.get(status, frozenset())
    return [s for s in STATUSES if s in allowed]


def is_overdue(target_date: date | None, status: str, today: date) -> bool:
    """An action is overdue only if it has a target date in the past and is not completed.

    A missing target date is never treated as overdue.
    """
    if target_date is None:
        return False
    return status in OVERDUE_ELIGIBLE and target_date < today


def check_transition(
    current: str,
    target: str,
    *,
    action_description: str | None,
    completed_on: date | None,
    today: date,
    latest_followup: tuple[date, str] | None,
) -> list[str]:
    """Return the reasons a status change is not permitted (empty list = allowed).

    ``completed_on`` is the completion date the action would have after the change
    (the user-entered date when moving to *Completed*, the stored date otherwise).
    ``latest_followup`` is ``(follow_up_date, result)`` of the most recent assessment.
    """
    if current not in TRANSITIONS or target not in TRANSITIONS:
        return ["Unknown status."]

    if target not in TRANSITIONS[current]:
        allowed = permitted_next(current)
        options = ", ".join(f"'{status_label(s)}'" for s in allowed) or "none (this status is final)"
        return [
            f"An action that is '{status_label(current)}' cannot move to "
            f"'{status_label(target)}'. Permitted next statuses: {options}."
        ]

    problems: list[str] = []
    if target == COMPLETED:
        if not (action_description or "").strip():
            problems.append(
                "Describe the corrective action before marking it completed."
            )
        if completed_on is None:
            problems.append("Enter the actual completion date.")
        else:
            if completed_on > today:
                problems.append("The completion date cannot be in the future.")
            if latest_followup and completed_on <= latest_followup[0]:
                problems.append(
                    "The completion date must be later than the date of the previous "
                    "follow-up assessment, so an old assessment is not reused."
                )
    elif target in (EFFECTIVE, NOT_EFFECTIVE):
        wanted = FOLLOWUP_EFFECTIVE if target == EFFECTIVE else FOLLOWUP_NOT_EFFECTIVE
        label = status_label(target)
        if latest_followup is None:
            problems.append(
                f"Record a follow-up assessment before marking the action '{label}'. "
                "Completion alone does not show effectiveness."
            )
        elif latest_followup[1] != wanted:
            problems.append(
                f"The latest follow-up assessment is "
                f"'{FOLLOWUP_LABELS.get(latest_followup[1], latest_followup[1])}', "
                f"which does not support the status '{label}'."
            )
        elif completed_on is not None and latest_followup[0] < completed_on:
            problems.append(
                "The latest follow-up assessment was recorded before the completion date; "
                "record a new assessment for the completed action."
            )
    return problems
