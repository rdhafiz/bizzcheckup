from bizzcheckup.engine.treatment import build_treatment_plan, is_quick_win
from bizzcheckup.engine.types import Level, Severity

from .factories import make_finding


def test_passes_and_info_are_not_in_the_plan() -> None:
    plan = build_treatment_plan([make_finding(Severity.PASS), make_finding(Severity.INFO)])
    assert plan.all == []


def test_quick_wins_first_then_sorted_by_impact_then_effort() -> None:
    hard_high = make_finding(impact=Level.HIGH, effort=Level.HIGH, message="hard high")
    easy_high = make_finding(impact=Level.HIGH, effort=Level.LOW, message="easy high")
    easy_medium = make_finding(impact=Level.MEDIUM, effort=Level.LOW, message="easy medium")
    medium_high = make_finding(impact=Level.HIGH, effort=Level.MEDIUM, message="medium high")
    easy_low = make_finding(impact=Level.LOW, effort=Level.LOW, message="easy low")

    plan = build_treatment_plan([easy_low, hard_high, easy_medium, medium_high, easy_high])

    assert [f.message for f in plan.quick_wins] == ["easy high", "easy medium"]
    assert [f.message for f in plan.others] == ["medium high", "hard high", "easy low"]


def test_fail_before_warn_when_impact_and_effort_equal() -> None:
    warn = make_finding(Severity.WARN, message="warn")
    fail = make_finding(Severity.FAIL, message="fail")
    assert [f.message for f in build_treatment_plan([warn, fail]).all] == ["fail", "warn"]


def test_is_quick_win() -> None:
    assert is_quick_win(make_finding(impact=Level.HIGH, effort=Level.LOW))
    assert not is_quick_win(make_finding(impact=Level.LOW, effort=Level.LOW))
    assert not is_quick_win(make_finding(impact=Level.HIGH, effort=Level.MEDIUM))
