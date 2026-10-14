"""The score badge: an SVG a healthy website can show on its own pages."""

from datetime import timedelta

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from bizzcheckup.checkups import services
from bizzcheckup.checkups.badges import badge_size
from bizzcheckup.checkups.models import Checkup
from bizzcheckup.engine.types import AuditReport

pytestmark = pytest.mark.django_db


def finished(report: AuditReport, score: int, days_ago: int = 0) -> Checkup:
    checkup = Checkup.objects.create(url="https://shop.test/", domain="shop.test")
    services.save_report(checkup, report.model_copy(update={"health_score": score}))
    services.mark_done(checkup)
    when = timezone.now() - timedelta(days=days_ago)
    Checkup.objects.filter(pk=checkup.pk).update(created_at=when)
    checkup.refresh_from_db()
    return checkup


def test_badge_is_an_svg_other_sites_may_show(client: Client, report: AuditReport) -> None:
    checkup = finished(report, 93)
    response = client.get(reverse("checkups:badge", args=[checkup.pk]))

    assert response.status_code == 200
    assert response["Content-Type"] == "image/svg+xml; charset=utf-8"
    assert response["Cross-Origin-Resource-Policy"] == "cross-origin"
    assert response["Content-Security-Policy"].startswith("default-src 'none'")
    svg = response.content.decode()
    assert ">93</text>" in svg
    assert "HEALTHY" in svg
    assert "<script" not in svg


def test_badge_always_shows_the_latest_score(client: Client, report: AuditReport) -> None:
    first = finished(report, 92, days_ago=30)
    finished(report, 95)  # this month's re-check
    svg = client.get(reverse("checkups:badge", args=[first.pk])).content.decode()
    assert ">95</text>" in svg


def test_no_badge_for_unfinished_checkups(client: Client) -> None:
    checkup = Checkup.objects.create(url="https://shop.test/", domain="shop.test")
    assert client.get(reverse("checkups:badge", args=[checkup.pk])).status_code == 404


def test_report_offers_the_badge_only_to_healthy_sites(client: Client, report: AuditReport) -> None:
    healthy = finished(report, 93)
    html = client.get(reverse("checkups:detail", args=[healthy.pk])).content.decode()
    assert "Your website is healthy: tell your visitors" in html
    assert reverse("checkups:badge", args=[healthy.pk]) in html

    Checkup.objects.all().delete()
    sick = finished(report, 66)
    html = client.get(reverse("checkups:detail", args=[sick.pk])).content.decode()
    assert "tell your visitors" not in html


def test_long_product_names_make_a_wider_badge() -> None:
    assert badge_size("A much longer product name").width > badge_size("BizzCheckup").width
