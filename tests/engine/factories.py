"""Tiny helpers that build engine objects for tests with sensible defaults."""

from bizzcheckup.engine.types import (
    Category,
    CheckResult,
    CheckStatus,
    Finding,
    Level,
    Severity,
)


def make_finding(
    severity: Severity = Severity.FAIL,
    *,
    category: Category = Category.SEO,
    impact: Level = Level.MEDIUM,
    effort: Level = Level.LOW,
    check_id: str = "seo.example",
    message: str = "Something is wrong.",
) -> Finding:
    return Finding(
        check_id=check_id,
        category=category,
        severity=severity,
        message=message,
        why_it_matters="It costs you customers.",
        how_to_fix="Fix it.",
        effort=effort,
        impact=impact,
    )


def make_result(
    score: float | None,
    *,
    category: Category = Category.SEO,
    weight: int = 5,
    status: CheckStatus = CheckStatus.RAN,
    findings: list[Finding] | None = None,
    note: str = "",
) -> CheckResult:
    return CheckResult(
        check_id=f"{category}.check{weight}",
        category=category,
        title="Example",
        weight=weight,
        status=status,
        score=score,
        findings=findings or [],
        note=note,
    )
