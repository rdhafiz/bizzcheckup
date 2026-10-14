"""Before and after: what changed since the website's previous check-up.

Used by the report ("Since your last check-up") and by the monthly re-check email.
A problem is identified by its check (`check_id`): if the check that found it no longer
finds a problem, it's fixed. Checks that didn't exist yet last time (BizzCheckup learns
new ones) are listed apart, so a new check never looks like a new problem on the site.
"""

from dataclasses import dataclass, field

from bizzcheckup.checkups.models import Checkup
from bizzcheckup.engine.types import AuditReport, Category, Finding, Severity

PROBLEM = (Severity.FAIL, Severity.WARN)
SEVERITY_RANK = {Severity.FAIL: 0, Severity.WARN: 1}


@dataclass
class ScoreChange:
    label: str
    before: int | None
    after: int | None

    @property
    def delta(self) -> int | None:
        if self.before is None or self.after is None:
            return None
        return self.after - self.before

    @property
    def direction(self) -> str:
        """ "up", "down" or "same" (also "same" when one of the two wasn't measured)."""
        delta = self.delta or 0
        return "up" if delta > 0 else "down" if delta < 0 else "same"

    @property
    def size(self) -> int:
        return abs(self.delta or 0)


@dataclass
class Comparison:
    previous: Checkup
    health: ScoreChange
    signs: list[ScoreChange]
    fixed: list[Finding] = field(default_factory=list)  # problems that are gone
    new: list[Finding] = field(default_factory=list)  # problems that weren't there before
    still: list[Finding] = field(default_factory=list)  # problems still there
    newly_checked: list[Finding] = field(default_factory=list)  # found by checks added since

    @property
    def improved(self) -> bool:
        return self.health.direction == "up"


def previous_checkup(checkup: Checkup) -> Checkup | None:
    """The same website's most recent finished check-up before this one."""
    return (
        Checkup.objects.filter(
            url=checkup.url, status=Checkup.Status.DONE, created_at__lt=checkup.created_at
        )
        .exclude(pk=checkup.pk)
        .order_by("-created_at")
        .first()
    )


def problems_by_check(report: AuditReport) -> dict[str, Finding]:
    """Each check's most serious problem (a check can report several, e.g. one per page)."""
    worst: dict[str, Finding] = {}
    for finding in report.findings:
        if finding.severity not in PROBLEM:
            continue
        current = worst.get(finding.check_id)
        if current is None or SEVERITY_RANK[finding.severity] < SEVERITY_RANK[current.severity]:
            worst[finding.check_id] = finding
    return worst


def compare(checkup: Checkup, report: AuditReport | None = None) -> Comparison | None:
    """What changed since the previous check-up of the same site (None if it's the first)."""
    previous = previous_checkup(checkup)
    if previous is None:
        return None
    try:
        before = AuditReport.model_validate(previous.raw_results)
    except ValueError:  # a very old report that no longer reads: skip the comparison
        return None
    after = report or AuditReport.model_validate(checkup.raw_results)

    old = problems_by_check(before)
    now = problems_by_check(after)
    checked_before = {result.check_id for result in before.results}
    return Comparison(
        previous=previous,
        health=ScoreChange("Health score", before.health_score, after.health_score),
        signs=[
            ScoreChange(
                category.label,
                before.category(category).score,
                after.category(category).score,
            )
            for category in Category
        ],
        fixed=[finding for check, finding in old.items() if check not in now],
        new=[f for check, f in now.items() if check not in old and check in checked_before],
        still=[finding for check, finding in now.items() if check in old],
        newly_checked=[f for check, f in now.items() if check not in checked_before],
    )
