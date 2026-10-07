"""Check-up pages: start, live progress (HTMX), result, failure, screenshot."""

import uuid
from unittest.mock import patch

import pytest
from django.test import Client
from django.urls import reverse

from bizzcheckup.checkups import services, tasks
from bizzcheckup.checkups.models import Checkup
from bizzcheckup.engine.types import AuditReport

pytestmark = pytest.mark.django_db


def make_checkup(**fields: object) -> Checkup:
    return Checkup.objects.create(url="https://shop.test/", domain="shop.test", **fields)


def test_home_has_the_checkup_form(client: Client) -> None:
    html = client.get(reverse("core:home")).content.decode()
    assert 'action="/checkups/new/"' in html
    assert "Start my free check-up" in html


def test_start_redirects_instantly_to_the_checkup_page(client: Client) -> None:
    with patch.object(tasks.run_checkup, "delay"):
        response = client.post(reverse("checkups:start"), {"url": "shop.test", "consent": "on"})

    checkup = Checkup.objects.get()
    assert response.status_code == 302
    assert response["Location"] == reverse("checkups:detail", args=[checkup.pk])


def test_start_shows_friendly_error_for_bad_url(client: Client) -> None:
    response = client.post(reverse("checkups:start"), {"url": "ftp://shop.test", "consent": "on"})
    assert response.status_code == 400
    assert "Only http:// and https:// addresses can be checked." in response.content.decode()
    assert Checkup.objects.count() == 0


def test_start_only_accepts_post(client: Client) -> None:
    assert client.get(reverse("checkups:start")).status_code == 405


def test_running_checkup_shows_progress_with_htmx_polling(client: Client) -> None:
    checkup = make_checkup(status=Checkup.Status.RUNNING, progress=60, current_step="Checking SEO")
    html = client.get(reverse("checkups:detail", args=[checkup.pk])).content.decode()

    assert "We're examining shop.test" in html
    assert 'hx-trigger="every 1s"' in html
    assert "js/progress.js" in html  # the smooth animation
    assert 'data-start="70" data-end="74"' in html  # step ranges for the animation
    assert f'hx-get="/checkups/{checkup.pk}/progress/"' in html
    assert 'value="60"' in html
    assert "Checking SEO" in html


def test_progress_partial_while_running(client: Client) -> None:
    checkup = make_checkup(status=Checkup.Status.RUNNING, progress=25)
    response = client.get(reverse("checkups:progress", args=[checkup.pk]))
    assert response.status_code == 200
    assert "<html" not in response.content.decode()  # just the box, not a whole page


def test_progress_partial_is_just_the_latest_data(client: Client) -> None:
    checkup = make_checkup(status=Checkup.Status.RUNNING, progress=42, current_step="Opening")
    html = client.get(reverse("checkups:progress", args=[checkup.pk])).content.decode()
    assert 'data-progress="42"' in html
    assert 'data-status="running"' in html
    assert 'data-step="Opening"' in html


@pytest.mark.parametrize("status", [Checkup.Status.DONE, Checkup.Status.FAILED])
def test_progress_partial_stops_htmx_polling_when_finished(client: Client, status: str) -> None:
    checkup = make_checkup(status=status)
    response = client.get(reverse("checkups:progress", args=[checkup.pk]))
    assert response.status_code == 286  # htmx's "stop polling" status
    assert f'data-status="{status}"' in response.content.decode()


def test_finished_checkup_shows_the_report_at_the_same_url(
    client: Client, report: AuditReport
) -> None:
    checkup = make_checkup()
    services.save_report(checkup, report)
    services.mark_done(checkup)
    html = client.get(reverse("checkups:detail", args=[checkup.pk])).content.decode()
    assert "BizzCheckup Health Report" in html
    assert "Needs attention" in html  # health score 66


def test_failed_checkup_shows_friendly_error(client: Client) -> None:
    checkup = make_checkup(status=Checkup.Status.FAILED, error_message="The site did not answer.")
    html = client.get(reverse("checkups:detail", args=[checkup.pk])).content.decode()
    assert "The site did not answer." in html
    assert "Try again" in html


def test_unknown_checkup_is_404(client: Client) -> None:
    assert client.get(reverse("checkups:detail", args=[uuid.uuid4()])).status_code == 404


def test_screenshot(client: Client) -> None:
    checkup = make_checkup(screenshot=b"\xff\xd8jpeg")
    response = client.get(reverse("checkups:screenshot", args=[checkup.pk]))
    assert response["Content-Type"] == "image/jpeg"
    assert response.content == b"\xff\xd8jpeg"

    empty = make_checkup()
    assert client.get(reverse("checkups:screenshot", args=[empty.pk])).status_code == 404
