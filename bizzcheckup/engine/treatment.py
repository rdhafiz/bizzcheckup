"""The treatment plan: which problems to fix first.

Order: biggest impact first; for equal impact, least effort first.
"Quick wins" (high or medium impact, low effort) are shown before the rest.
"""

from collections.abc import Iterable

from pydantic import BaseModel

from .types import Finding, Level, Severity

IMPACT_ORDER = {Level.HIGH: 0, Level.MEDIUM: 1, Level.LOW: 2}
EFFORT_ORDER = {Level.LOW: 0, Level.MEDIUM: 1, Level.HIGH: 2}
SEVERITY_ORDER = {Severity.FAIL: 0, Severity.WARN: 1}
PROBLEMS = {Severity.FAIL, Severity.WARN}


class TreatmentPlan(BaseModel):
    quick_wins: list[Finding]
    others: list[Finding]

    @property
    def all(self) -> list[Finding]:
        return self.quick_wins + self.others


def is_quick_win(finding: Finding) -> bool:
    return finding.impact in (Level.HIGH, Level.MEDIUM) and finding.effort is Level.LOW


def priority(finding: Finding) -> tuple[int, int, int]:
    """Sort key: impact (high first), then effort (low first), then fail before warn."""
    return (
        IMPACT_ORDER[finding.impact],
        EFFORT_ORDER[finding.effort],
        SEVERITY_ORDER[finding.severity],
    )


def build_treatment_plan(findings: Iterable[Finding]) -> TreatmentPlan:
    problems = sorted((f for f in findings if f.severity in PROBLEMS), key=priority)
    return TreatmentPlan(
        quick_wins=[f for f in problems if is_quick_win(f)],
        others=[f for f in problems if not is_quick_win(f)],
    )
