"""DIS-01..05, DIS-09: disposition reconciliation using the documented synthetic dataset."""

from app.domain.disposition import check_disposition, disposition_total


def check(inspected=100, accepted=80, rework=10, rejected=5, pending=5, unit="pieces"):
    return check_disposition(
        inspected_quantity=inspected,
        inspected_unit="pieces",
        accepted=accepted,
        rework=rework,
        rejected=rejected,
        pending=pending,
        unit=unit,
    )


def test_exact_reconciliation_is_accepted():
    assert disposition_total(80, 10, 5, 5) == 100
    assert check() == []


def test_total_above_inspected_is_rejected_with_explanation():
    problems = check(rejected=15)  # 80 + 10 + 15 + 5 = 110
    assert len(problems) == 1
    assert "110 pieces" in problems[0]
    assert "exceeds" in problems[0]
    assert "by 10" in problems[0]


def test_total_below_inspected_is_rejected_and_suggests_pending():
    problems = check(accepted=70)  # total 90
    assert len(problems) == 1
    assert "10 pieces short" in problems[0]
    assert "pending" in problems[0]


def test_unit_mismatch_blocks_reconciliation():
    problems = check(unit="meters")
    assert len(problems) == 1
    assert "different units" in problems[0]


def test_all_pending_is_a_valid_unresolved_disposition():
    assert check(accepted=0, rework=0, rejected=0, pending=100) == []


def test_reconciliation_never_adjusts_quantities():
    # The function only reports; it has no way to change the inputs.
    problems = check(accepted=1, rework=1, rejected=1, pending=1)
    assert problems and disposition_total(1, 1, 1, 1) == 4
