"""CA-04..CA-10: corrective-action transition rules."""

from datetime import date

import pytest

from app.domain import workflow as w

TODAY = date(2026, 10, 18)


def check(current, target, *, desc="Replace needles", completed_on=None, followup=None):
    return w.check_transition(
        current,
        target,
        action_description=desc,
        completed_on=completed_on,
        today=TODAY,
        latest_followup=followup,
    )


def test_open_to_in_progress_is_allowed():
    assert check(w.OPEN, w.IN_PROGRESS) == []


@pytest.mark.parametrize(
    ("current", "target"),
    [
        (w.OPEN, w.EFFECTIVE),
        (w.OPEN, w.CLOSED),
        (w.IN_PROGRESS, w.EFFECTIVE),
        (w.COMPLETED, w.CLOSED),
        (w.NOT_EFFECTIVE, w.EFFECTIVE),
        (w.CLOSED, w.OPEN),
        (w.CLOSED, w.IN_PROGRESS),
    ],
)
def test_prohibited_transitions_are_rejected(current, target):
    problems = check(current, target, completed_on=date(2026, 10, 1))
    assert len(problems) == 1
    assert "cannot move to" in problems[0]


def test_closed_status_is_final():
    assert w.permitted_next(w.CLOSED) == []
    assert "none (this status is final)" in check(w.CLOSED, w.OPEN)[0]


def test_every_status_in_graph_is_known():
    for status, targets in w.TRANSITIONS.items():
        assert status in w.STATUSES
        assert targets <= set(w.STATUSES)


def test_completing_requires_description_and_date():
    problems = check(w.IN_PROGRESS, w.COMPLETED, desc="", completed_on=None)
    assert len(problems) == 2
    assert check(w.IN_PROGRESS, w.COMPLETED, completed_on=date(2026, 10, 1)) == []


def test_completion_date_cannot_be_in_future():
    problems = check(w.IN_PROGRESS, w.COMPLETED, completed_on=date(2026, 10, 19))
    assert problems == ["The completion date cannot be in the future."]


def test_completion_must_postdate_previous_followup():
    problems = check(
        w.IN_PROGRESS,
        w.COMPLETED,
        completed_on=date(2026, 9, 1),
        followup=(date(2026, 9, 1), w.FOLLOWUP_EFFECTIVE),
    )
    assert len(problems) == 1 and "previous follow-up" in problems[0]


def test_effective_requires_a_followup_assessment():
    problems = check(w.COMPLETED, w.EFFECTIVE, completed_on=date(2026, 10, 1))
    assert len(problems) == 1
    assert "Completion alone does not show effectiveness" in problems[0]


def test_effective_requires_matching_effective_result():
    done = date(2026, 10, 1)
    bad = check(w.COMPLETED, w.EFFECTIVE, completed_on=done, followup=(date(2026, 10, 5), "not_effective"))
    assert len(bad) == 1 and "does not support" in bad[0]
    inconclusive = check(w.COMPLETED, w.EFFECTIVE, completed_on=done, followup=(date(2026, 10, 5), "inconclusive"))
    assert len(inconclusive) == 1
    good = check(w.COMPLETED, w.EFFECTIVE, completed_on=done, followup=(date(2026, 10, 5), "effective"))
    assert good == []


def test_not_effective_requires_matching_result():
    done = date(2026, 10, 1)
    assert check(w.COMPLETED, w.NOT_EFFECTIVE, completed_on=done, followup=(date(2026, 10, 5), "not_effective")) == []
    assert check(w.COMPLETED, w.NOT_EFFECTIVE, completed_on=done, followup=(date(2026, 10, 5), "effective"))


def test_followup_before_completion_date_is_not_accepted():
    problems = check(
        w.COMPLETED, w.EFFECTIVE, completed_on=date(2026, 10, 10), followup=(date(2026, 10, 5), "effective")
    )
    assert len(problems) == 1 and "before the completion date" in problems[0]


def test_close_allowed_only_from_effective():
    assert check(w.EFFECTIVE, w.CLOSED) == []


def test_overdue_rules():
    past = date(2026, 10, 1)
    assert w.is_overdue(past, w.OPEN, TODAY) is True
    assert w.is_overdue(past, w.IN_PROGRESS, TODAY) is True
    assert w.is_overdue(None, w.OPEN, TODAY) is False  # missing target date is never overdue
    assert w.is_overdue(past, w.COMPLETED, TODAY) is False  # already completed
    assert w.is_overdue(past, w.EFFECTIVE, TODAY) is False
    assert w.is_overdue(date(2026, 10, 18), w.OPEN, TODAY) is False  # due today is not overdue
    assert w.is_overdue(date(2026, 11, 1), w.OPEN, TODAY) is False
