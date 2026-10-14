"""Compare with a competitor: start their check-up, then show both side by side."""

from unittest.mock import patch

import pytest
from django.test import Client
from django.urls import reverse
from pytest_django.fixtures import Settings

from bizzcheckup.checkups import services, tasks
from bizzcheckup.checkups.models import Checkup
from bizzcheckup.engine.types import AuditReport, Severity
from bizzcheckup.reports.comparison import ScorePair, compare_with_competitor

pytestmark = pytest.mark.django_db


def finished(report: AuditReport, url: str = "https://shop.test/", score: int = 66) -> Checkup:
    domain = url.split("/")[2]
    checkup = Checkup.objects.create(url=url, domain=domain)
    services.save_report(checkup, report.model_copy(update={"url": url, "health_score": score}))
    services.mark_done(checkup)
    return checkup


def compare(client: Client, checkup: Checkup, url: str) -> str:
    with patch.object(tasks.run_checkup, "delay"):
        response = client.post(
            reverse("checkups:compare", args=[checkup.pk]), {"url": url}, follow=True
        )
    return response.content.decode()


def test_compare_starts_the_competitors_checkup(client: Client, report: AuditReport) -> None:
    ours = finished(report)
    html = compare(client, ours, "rival.test/some/page")

    ours.refresh_from_db()
    assert ours.competitor is not None
    assert ours.competitor.url == "https://rival.test/"  # main address only, like any check
    assert "checking rival.test now" in html


def test_a_recent_report_of_the_competitor_is_reused(client: Client, report: AuditReport) -> None:
    ours = finished(report)
    theirs = finished(report, "https://rival.test/", score=80)
    compare(client, ours, "rival.test")

    ours.refresh_from_db()
    assert ours.competitor == theirs
    assert Checkup.objects.count() == 2  # nothing new was started


def test_comparing_with_yourself_is_refused(client: Client, report: AuditReport) -> None:
    ours = finished(report)
    html = compare(client, ours, "https://shop.test/about")
    assert "That&#x27;s your own website" in html
    ours.refresh_from_db()
    assert ours.competitor is None


def test_the_hourly_limit_applies(client: Client, report: AuditReport, settings: Settings) -> None:
    settings.CHECKUP_RATE_LIMIT_PER_HOUR = 0
    ours = finished(report)
    html = compare(client, ours, "rival.test")
    assert "several check-ups in the last hour" in html


def test_side_by_side_once_both_are_done(client: Client, report: AuditReport) -> None:
    ours = finished(report)
    theirs = finished(report, "https://rival.test/", score=80)
    Checkup.objects.filter(pk=ours.pk).update(competitor=theirs)
    ours.refresh_from_db()

    rival = compare_with_competitor(ours)
    assert rival is not None
    assert rival.health == ScorePair("Health score", 66, 80)
    assert rival.health.leader == "theirs"

    html = client.get(reverse("checkups:detail", args=[ours.pk])).content.decode()
    assert "You vs" in html
    assert "rival.test" in html


def test_solved_problems_are_counted_both_ways(report: AuditReport) -> None:
    ours = finished(report)  # has the seo.title problem
    clean = report.model_copy(
        update={
            "results": [
                r.model_copy(
                    update={
                        "findings": [
                            f.model_copy(update={"severity": Severity.PASS}) for f in r.findings
                        ]
                    }
                )
                for r in report.results
            ]
        }
    )
    theirs = finished(clean, "https://rival.test/", score=90)
    Checkup.objects.filter(pk=ours.pk).update(competitor=theirs)
    ours.refresh_from_db()

    rival = compare_with_competitor(ours)
    assert rival is not None
    assert [f.check_id for f in rival.they_solved] == ["seo.title"]
    assert rival.we_solved == []


def test_no_comparison_while_the_competitor_is_still_running(report: AuditReport) -> None:
    ours = finished(report)
    running = Checkup.objects.create(
        url="https://rival.test/", domain="rival.test", status="running"
    )
    Checkup.objects.filter(pk=ours.pk).update(competitor=running)
    ours.refresh_from_db()
    assert compare_with_competitor(ours) is None
