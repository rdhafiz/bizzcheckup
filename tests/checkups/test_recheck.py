"""The "Check again now" button: a fresh check-up that skips report reuse."""

from collections.abc import Iterator
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from bizzcheckup.checkups import services, tasks
from bizzcheckup.checkups.models import Checkup

from .conftest import make_report

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def no_real_queue() -> Iterator[None]:
    with patch.object(tasks.run_checkup, "delay"):
        yield


def finished(url: str = "https://shop.test/", minutes_ago: int = 10) -> Checkup:
    checkup = Checkup.objects.create(url=url, domain="shop.test")
    services.save_report(checkup, make_report(url))
    services.mark_done(checkup)
    when = timezone.now() - timedelta(minutes=minutes_ago)
    Checkup.objects.filter(pk=checkup.pk).update(created_at=when, finished_at=when)
    return Checkup.objects.get(pk=checkup.pk)


def recheck(client: Client, checkup: Checkup, ip: str = "203.0.113.5"):  # type: ignore[no-untyped-def]
    return client.post(reverse("checkups:recheck", args=[checkup.pk]), REMOTE_ADDR=ip)


def test_report_has_the_button_and_shows_how_old_it_is(client: Client) -> None:
    html = client.get(reverse("checkups:detail", args=[finished().pk])).content.decode()
    assert "Check again now" in html
    assert "Checked 10" in html  # "Checked 10 minutes ago"


def test_check_again_starts_a_fresh_checkup_even_within_the_reuse_window(client: Client) -> None:
    old = finished(minutes_ago=5)  # would normally be reused for 24 hours

    response = recheck(client, old)

    fresh = Checkup.objects.exclude(pk=old.pk).get()
    assert response["Location"] == reverse("checkups:detail", args=[fresh.pk])
    assert fresh.url == old.url
    assert fresh.status == Checkup.Status.QUEUED
    assert fresh.ip_hash  # counted for the rate limit


def test_check_again_goes_to_a_checkup_that_is_already_running(client: Client) -> None:
    old = finished()
    running = Checkup.objects.create(url=old.url, domain="shop.test", status="running")

    response = recheck(client, old)

    assert response["Location"] == reverse("checkups:detail", args=[running.pk])
    assert Checkup.objects.count() == 2  # nothing new started


def test_check_again_counts_towards_the_hourly_limit(client: Client) -> None:
    old = finished()
    for _ in range(5):
        Checkup.objects.filter(status="queued").update(status="done", started_at=timezone.now())
        assert recheck(client, old).status_code == 302

    Checkup.objects.filter(status="queued").update(status="done", started_at=timezone.now())
    response = recheck(client, old, ip="203.0.113.5")  # the 6th within the hour
    follow = client.get(response["Location"]).content.decode()

    assert response["Location"] == reverse("checkups:detail", args=[old.pk])  # back to report
    assert "several check-ups in the last hour" in follow


def test_check_again_rechecks_the_address_for_ssrf(client: Client) -> None:
    old = finished(url="http://internal.test/")  # resolves to 10.0.0.7 in tests
    response = recheck(client, old)
    assert response["Location"] == reverse("checkups:detail", args=[old.pk])
    assert Checkup.objects.count() == 1


def test_failed_checkup_can_be_checked_again(client: Client) -> None:
    failed = Checkup.objects.create(
        url="https://shop.test/", domain="shop.test", status="failed", error_message="Timeout"
    )
    html = client.get(reverse("checkups:detail", args=[failed.pk])).content.decode()
    assert "Check again now" in html
    assert recheck(client, failed).status_code == 302
    assert Checkup.objects.count() == 2


def test_check_again_only_accepts_post_with_csrf(client: Client) -> None:
    old = finished()
    assert client.get(reverse("checkups:recheck", args=[old.pk])).status_code == 405
    strict = Client(enforce_csrf_checks=True)
    assert strict.post(reverse("checkups:recheck", args=[old.pk])).status_code == 403
