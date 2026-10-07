import pytest

from bizzcheckup.engine.scoring import (
    band_for,
    health_score,
    round_half_up,
    score_categories,
    score_category,
    severity_score,
)
from bizzcheckup.engine.types import Band, Category, CategoryScore, CheckStatus, Level, Severity

from .factories import make_finding, make_result


@pytest.mark.parametrize(
    ("severities", "expected"),
    [
        ([], 1.0),
        ([Severity.PASS], 1.0),
        ([Severity.INFO], 1.0),
        ([Severity.PASS, Severity.WARN], 0.5),
        ([Severity.WARN, Severity.FAIL, Severity.PASS], 0.0),
    ],
)
def test_severity_score_uses_worst_finding(severities: list[Severity], expected: float) -> None:
    assert severity_score([make_finding(s) for s in severities]) == expected


@pytest.mark.parametrize(
    ("score", "band"),
    [
        (0, Band.URGENT),
        (49, Band.URGENT),
        (50, Band.ATTENTION),
        (89, Band.ATTENTION),
        (90, Band.HEALTHY),
        (100, Band.HEALTHY),
        (None, None),
    ],
)
def test_band_boundaries(score: int | None, band: Band | None) -> None:
    assert band_for(score) is band


def test_round_half_up() -> None:
    assert round_half_up(72.5) == 73
    assert round_half_up(72.49) == 72


def test_category_score_is_weighted_average() -> None:
    results = [make_result(1.0, weight=8), make_result(0.5, weight=2)]
    # (8 * 1.0 + 2 * 0.5) / 10 = 0.9 -> 90
    category = score_category(Category.SEO, results)
    assert category.score == 90
    assert category.band is Band.HEALTHY
    assert category.checks_run == 2


def test_skipped_and_errored_checks_are_left_out() -> None:
    results = [
        make_result(1.0, weight=5),
        make_result(None, weight=5, status=CheckStatus.SKIPPED),
        make_result(None, weight=5, status=CheckStatus.ERROR),
    ]
    category = score_category(Category.SEO, results)
    assert category.score == 100
    assert category.checks_skipped == 2


def test_category_with_nothing_run_is_not_checked() -> None:
    results = [
        make_result(
            None,
            category=Category.PERFORMANCE,
            status=CheckStatus.SKIPPED,
            note="No PageSpeed API key configured.",
        )
    ]
    category = score_category(Category.PERFORMANCE, results)
    assert category.score is None
    assert category.band is None
    assert category.note == "No PageSpeed API key configured."


def test_high_impact_fail_caps_category_at_89() -> None:
    serious = make_finding(Severity.FAIL, impact=Level.HIGH)
    results = [make_result(1.0, weight=10) for _ in range(9)] + [
        make_result(0.0, weight=1, findings=[serious])
    ]
    # Without the cap: (90 * 1 + 1 * 0) / 91 = 98.9 -> 99
    assert score_category(Category.SEO, results).score == 89


def test_score_categories_returns_all_five_in_order() -> None:
    categories = score_categories([make_result(1.0)])
    assert [c.category for c in categories] == list(Category)


def scored(category: Category, score: int | None) -> CategoryScore:
    return CategoryScore(
        category=category, score=score, band=band_for(score), checks_run=1, checks_skipped=0
    )


def test_health_score_uses_category_weights() -> None:
    categories = [
        scored(Category.PERFORMANCE, 40),  # weight 25
        scored(Category.SEO, 80),  # weight 25
        scored(Category.BEST_PRACTICES, 100),  # weight 20
        scored(Category.ACCESSIBILITY, 60),  # weight 15
        scored(Category.AGENTIC, 20),  # weight 15
    ]
    # (25*40 + 25*80 + 20*100 + 15*60 + 15*20) / 100 = 62
    assert health_score(categories) == 62


def test_health_score_rebalances_when_a_category_is_missing() -> None:
    categories = [
        scored(Category.PERFORMANCE, None),  # e.g. no PageSpeed key
        scored(Category.SEO, 80),
        scored(Category.BEST_PRACTICES, 100),
        scored(Category.ACCESSIBILITY, 60),
        scored(Category.AGENTIC, 20),
    ]
    # (25*80 + 20*100 + 15*60 + 15*20) / 75 = 69.33 -> 69
    assert health_score(categories) == 69


def test_health_score_none_when_nothing_scored() -> None:
    assert health_score([scored(Category.SEO, None)]) is None
