"""Turn check results into category scores and the Business Health Score.

The formula (also explained for readers in docs/ARCHITECTURE.md):

1. Check score (0-1): from its worst finding. pass/info = 1, warn = 0.5,
   fail = 0. A check may override this (e.g. "18 of 20 images have alt text").
2. Category score (0-100): weighted average of the checks that ran:
       round(100 * sum(weight * score) / sum(weight))
   Skipped or crashed checks are left out. If nothing ran: None ("Not checked").
   A high-impact failure caps the category at 89, so it can't be "Healthy".
3. Business Health Score: weighted average of the categories that have a score.
4. Bands: 0-49 urgent, 50-89 attention, 90-100 healthy.
"""

import math
from collections.abc import Iterable

from .types import Band, Category, CategoryScore, CheckResult, CheckStatus, Finding, Level, Severity

SEVERITY_SCORES: dict[Severity, float] = {
    Severity.PASS: 1.0,
    Severity.INFO: 1.0,  # advice only, no penalty
    Severity.WARN: 0.5,
    Severity.FAIL: 0.0,
}

# How much each vital sign counts towards the Business Health Score.
CATEGORY_WEIGHTS: dict[Category, int] = {
    Category.PERFORMANCE: 25,
    Category.SEO: 25,
    Category.BEST_PRACTICES: 20,
    Category.ACCESSIBILITY: 15,
    Category.AGENTIC: 15,
}

HIGH_IMPACT_FAIL_CAP = 89  # highest possible score with a serious problem
URGENT_BELOW = 50
HEALTHY_FROM = 90


def round_half_up(value: float) -> int:
    """Normal school rounding: 72.5 -> 73. (Python's round() gives 72.)"""
    return math.floor(value + 0.5)


def severity_score(findings: Iterable[Finding]) -> float:
    """Score of the worst finding; 1.0 when there are no findings."""
    return min((SEVERITY_SCORES[f.severity] for f in findings), default=1.0)


def band_for(score: int | None) -> Band | None:
    if score is None:
        return None
    if score < URGENT_BELOW:
        return Band.URGENT
    if score < HEALTHY_FROM:
        return Band.ATTENTION
    return Band.HEALTHY


def has_high_impact_fail(results: Iterable[CheckResult]) -> bool:
    return any(
        f.severity is Severity.FAIL and f.impact is Level.HIGH for r in results for f in r.findings
    )


def score_category(category: Category, results: list[CheckResult]) -> CategoryScore:
    mine = [r for r in results if r.category is category]
    ran = [r for r in mine if r.status is CheckStatus.RAN and r.score is not None]
    skipped = [r for r in mine if r.status is not CheckStatus.RAN]

    if not ran:
        note = next((r.note for r in skipped if r.note), "Not checked.")
        return CategoryScore(
            category=category, score=None, band=None, checks_run=0,
            checks_skipped=len(skipped), note=note,
        )  # fmt: skip

    total_weight = sum(r.weight for r in ran)
    weighted = sum(r.weight * (r.score or 0.0) for r in ran)
    score = round_half_up(100 * weighted / total_weight)
    if has_high_impact_fail(ran):
        score = min(score, HIGH_IMPACT_FAIL_CAP)

    return CategoryScore(
        category=category,
        score=score,
        band=band_for(score),
        checks_run=len(ran),
        checks_skipped=len(skipped),
    )


def score_categories(results: list[CheckResult]) -> list[CategoryScore]:
    """One CategoryScore per category, in report order."""
    return [score_category(category, results) for category in Category]


def health_score(categories: list[CategoryScore]) -> int | None:
    """Weighted average of scored categories. Weights re-balance if one is missing."""
    scored = [c for c in categories if c.score is not None]
    if not scored:
        return None
    total_weight = sum(CATEGORY_WEIGHTS[c.category] for c in scored)
    weighted = sum(CATEGORY_WEIGHTS[c.category] * (c.score or 0) for c in scored)
    return round_half_up(weighted / total_weight)
