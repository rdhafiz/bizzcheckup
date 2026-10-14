"""Before and after: what changed since the previous check-up of the same website."""

from datetime import timedelta

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from bizzcheckup.checkups import services
from bizzcheckup.checkups.models import Checkup
from bizzcheckup.engine.types import (
    AuditReport,
    Category,
    CheckResult,
    CheckStatus,
    Finding,
    Level,
    Severity,
)
from bizzcheckup.reports.comparison import ScoreChange, compare
from tests.checkups.conftest import make_report

pytestmark = pytest.mark.django_db


def problem(check_id: str, severity: Severity = Severity.WARN) -> Finding:
    return Finding(
        check_id=check_id,
        category=Category.SEO,
        severity=severity,
        message=f"Problem found by {check_id}.",
        why_it_matters="Why.",
        how_to_fix="How.",
        effort=Level.LOW,
        impact=Level.MEDIUM,
        affected_urls=["https://shop.test/"],
    )


def report_with(health: int, checks: dict[str, Severity]) -> AuditReport:
    """A report whose checks found these problems (PASS = checked, nothing wrong)."""
    results = [
        CheckResult(
            check_id=check_id,
            category=Category.SEO,
            title=check_id,
            weight=5,
            status=CheckStatus.RAN,
            score=1.0 if severity is Severity.PASS else 0.0,
            findings=[problem(check_id, severity)],
        )
        for check_id, severity in checks.items()
    ]
    return make_report().model_copy(update={"results": results, "health_score": health})


def finished(report: AuditReport, days_ago: int = 0) -> Checkup:
    checkup = Checkup.objects.create(url="https://shop.test/", domain="shop.test")
    services.save_report(checkup, report)
    services.mark_done(checkup)
    when = timezone.now() - timedelta(days=days_ago)
    Checkup.objects.filter(pk=checkup.pk).update(created_at=when, finished_at=when)
    checkup.refresh_from_db()
    return checkup


def test_first_checkup_has_nothing_to_compare() -> None:
    assert compare(finished(make_report())) is None


def test_fixed_new_still_and_newly_checked_problems() -> None:
    finished(
        report_with(
            60,
            {"seo.title": Severity.FAIL, "seo.meta": Severity.WARN, "seo.h1": Severity.PASS},
        ),
        days_ago=30,
    )
    now = finished(
        report_with(
            72,
            {
                "seo.title": Severity.PASS,  # fixed
                "seo.meta": Severity.WARN,  # still there
                "seo.h1": Severity.WARN,  # new problem
                "best_practices.email_spoofing": Severity.WARN,  # a check added since
            },
        )
    )

    change = compare(now)

    assert change is not None
    assert [f.check_id for f in change.fixed] == ["seo.title"]
    assert [f.check_id for f in change.still] == ["seo.meta"]
    assert [f.check_id for f in change.new] == ["seo.h1"]
    assert [f.check_id for f in change.newly_checked] == ["best_practices.email_spoofing"]
    assert change.health.delta == 12
    assert change.improved


def test_compares_with_the_most_recent_earlier_checkup_of_the_same_site() -> None:
    finished(report_with(40, {}), days_ago=60)
    middle = finished(report_with(50, {}), days_ago=30)
    Checkup.objects.create(url="https://other.test/", domain="other.test", status="done")
    now = finished(report_with(55, {}))

    change = compare(now)
    assert change is not None
    assert change.previous == middle
    assert compare(middle) is not None  # the oldest one is middle's "previous"


@pytest.mark.parametrize(
    ("before", "after", "direction", "delta"),
    [(60, 72, "up", 12), (72, 60, "down", -12), (60, 60, "same", 0), (None, 60, "same", None)],
)
def test_score_change(before: int | None, after: int, direction: str, delta: int | None) -> None:
    change = ScoreChange("Health score", before, after)
    assert change.direction == direction
    assert change.delta == delta


def test_report_shows_what_changed(client: Client) -> None:
    previous = finished(report_with(60, {"seo.title": Severity.FAIL}), days_ago=30)
    now = finished(report_with(72, {"seo.title": Severity.PASS}))

    html = client.get(reverse("checkups:detail", args=[now.pk])).content.decode()

    assert 'id="changes"' in html
    assert "getting healthier" in html
    assert "up 12" in html
    assert "Problem found by seo.title." in html  # under "Fixed"
    assert reverse("checkups:detail", args=[previous.pk]) in html  # "Open that report"


def test_first_report_has_no_changes_section(client: Client) -> None:
    now = finished(make_report())
    html = client.get(reverse("checkups:detail", args=[now.pk])).content.decode()
    assert 'id="changes"' not in html
