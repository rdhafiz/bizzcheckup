"""How long a fix takes, and who usually does it, in words a business owner can plan with.

Every finding has an effort level (low / medium / high, set by the check). These are
typical times for that level, not a quote: they help owners see what they can do
themselves this afternoon and what needs a developer.
"""

from dataclasses import dataclass

from bizzcheckup.engine.types import Finding, Level

WORKDAY_MINUTES = 8 * 60


@dataclass(frozen=True)
class FixTime:
    minutes: int  # a typical time, used to add up the total
    label: str  # e.g. "about 20 minutes"
    short: str  # for the issue's chip, e.g. "~20 min"
    who: str  # who usually does it

    @property
    def do_it_yourself(self) -> bool:
        return self.minutes < 60


FIX_TIMES = {
    Level.LOW: FixTime(20, "about 20 minutes", "~20 min", "You can usually do this yourself"),
    Level.MEDIUM: FixTime(150, "2 to 3 hours", "2-3 h", "Usually a job for a web developer"),
    Level.HIGH: FixTime(
        2 * WORKDAY_MINUTES, "1 to 3 days", "1-3 days", "A job for a web developer"
    ),
}


def fix_time(finding: Finding) -> FixTime:
    return FIX_TIMES[finding.effort]


def duration(minutes: int) -> str:
    """A total in plain words: "about 40 minutes", "about 5 hours", "about 3 days"."""
    if minutes < 60:
        return f"about {minutes} minutes"
    hours = round(minutes / 60)
    if minutes < WORKDAY_MINUTES * 1.5:
        return "about 1 hour" if hours == 1 else f"about {hours} hours"
    days = round(minutes / WORKDAY_MINUTES)
    return "about 1 day" if days == 1 else f"about {days} days"


@dataclass(frozen=True)
class FixSummary:
    total_minutes: int
    diy_count: int  # problems the owner can usually fix themselves
    developer_minutes: int  # the part that's usually a developer's work

    @property
    def total(self) -> str:
        return duration(self.total_minutes)

    @property
    def developer(self) -> str:
        return duration(self.developer_minutes)


def summarise(findings: list[Finding]) -> FixSummary:
    times = [fix_time(finding) for finding in findings]
    return FixSummary(
        total_minutes=sum(t.minutes for t in times),
        diy_count=sum(1 for t in times if t.do_it_yourself),
        developer_minutes=sum(t.minutes for t in times if not t.do_it_yourself),
    )
