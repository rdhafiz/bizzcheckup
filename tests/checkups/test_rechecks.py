"""Monthly re-checks: opting in, the scheduler, the "what changed" email, unsubscribing."""

from datetime import timedelta
from unittest.mock import patch

import pytest
from django.core import mail
from django.core.management import call_command
from django.test import Client
from django.urls import reverse
from django.utils import timezone
from pytest_django.fixtures import Settings

from bizzcheckup.checkups import services, tasks
from bizzcheckup.checkups.models import Checkup, Lead, Subscription
from bizzcheckup.engine.types import AuditReport

from .test_checkups import fake_engine

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def email_settings(settings: Settings) -> None:
    settings.SITE_URL = "https://check.example"
    settings.LEAD_ALERT_EMAIL = "owner@example.com"
    settings.RECHECK_EVERY_DAYS = 30


def due_subscription(**fields: object) -> Subscription:
    lead = Lead.objects.create(email="amy@shop.test", consent=True)
    values = {
        "email": "amy@shop.test",
        "url": "https://shop.test/",
        "domain": "shop.test",
        "lead": lead,
        "next_check_at": timezone.now() - timedelta(minutes=1),
        **fields,
    }
    return Subscription.objects.create(**values)


def finished(report: AuditReport, days_ago: int = 0) -> Checkup:
    checkup = Checkup.objects.create(url="https://shop.test/", domain="shop.test")
    services.save_report(checkup, report)
    services.mark_done(checkup)
    when = timezone.now() - timedelta(days=days_ago)
    Checkup.objects.filter(pk=checkup.pk).update(created_at=when, finished_at=when)
    return checkup


# --- Opting in -------------------------------------------------------------------------


def test_homepage_opt_in_needs_an_email(client: Client) -> None:
    with patch.object(tasks.run_checkup, "delay"):
        client.post(
            reverse("checkups:start"), {"url": "shop.test", "consent": "on", "monthly": "on"}
        )
        assert not Subscription.objects.exists()  # no email: nothing to send to
        client.post(
            reverse("checkups:start"),
            {"url": "other.test", "email": "Amy@Shop.test", "consent": "on", "monthly": "on"},
        )

    subscription = Subscription.objects.get()
    assert subscription.email == "amy@shop.test"
    assert subscription.url == "https://other.test/"
    assert subscription.next_check_at > timezone.now() + timedelta(days=29)


def test_subscribing_again_restarts_a_stopped_subscription() -> None:
    first = services.subscribe("amy@shop.test", "https://shop.test/products")
    services.unsubscribe(first)
    again = services.subscribe("AMY@shop.test", "shop.test")

    assert again.pk == first.pk  # one per person and site
    assert again.active
    assert again.url == "https://shop.test/"


def test_email_me_the_report_can_opt_in(client: Client, report: AuditReport) -> None:
    checkup = finished(report)
    client.post(
        reverse("checkups:email_report", args=[checkup.pk]),
        {"email": "amy@shop.test", "monthly": "on"},
    )
    assert Subscription.objects.filter(email="amy@shop.test", url="https://shop.test/").exists()


# --- The scheduler ---------------------------------------------------------------------


def test_due_rechecks_start_and_move_to_next_month() -> None:
    due = due_subscription()
    due_subscription(email="later@shop.test", next_check_at=timezone.now() + timedelta(days=3))
    due_subscription(email="stopped@shop.test", active=False)

    with patch.object(tasks.run_checkup, "delay"):
        started = services.start_due_rechecks(10)

    (checkup,) = started
    assert checkup.subscription == due
    assert checkup.lead == due.lead
    due.refresh_from_db()
    assert due.next_check_at > timezone.now() + timedelta(days=29)


def test_a_site_being_checked_now_waits_a_day() -> None:
    subscription = due_subscription()
    Checkup.objects.create(url="https://shop.test/", domain="shop.test", status="running")

    assert services.start_due_rechecks(10) == []
    subscription.refresh_from_db()
    assert timezone.now() < subscription.next_check_at < timezone.now() + timedelta(days=2)


def test_rechecks_respect_the_queue_cap(settings: Settings) -> None:
    settings.CHECKUP_QUEUE_CAP = 1
    due_subscription()
    Checkup.objects.create(url="https://busy.test/", domain="busy.test", status="running")
    assert services.start_due_rechecks(10) == []


# --- The monthly email -----------------------------------------------------------------


def test_monthly_email_shows_what_changed(report: AuditReport) -> None:
    finished(report.model_copy(update={"health_score": 80}), days_ago=30)
    subscription = due_subscription()

    (checkup,) = services.start_due_rechecks(10, start=False)

    async def run_audit(url: str, config: object, **kwargs: object) -> AuditReport:
        return report  # (fake_engine looks the check-up up by URL; here there are two)

    with patch.object(tasks, "run_audit", run_audit):
        tasks.run_checkup(str(checkup.pk))

    to_visitor = [m for m in mail.outbox if m.to == ["amy@shop.test"]]
    (message,) = to_visitor  # only the monthly email, not the usual report email
    assert message.subject == "shop.test this month: health score 80 → 66 (▼14)"
    unsubscribe = f"https://check.example/checkups/unsubscribe/{subscription.token}/"
    assert message.extra_headers["List-Unsubscribe"] == f"<{unsubscribe}>"
    assert unsubscribe in message.body
    # The score dropped by 14: the consultant hears about it.
    alerts = [m for m in mail.outbox if m.to == ["owner@example.com"]]
    assert "dropped 14 points this month" in alerts[0].subject


def test_management_command_runs_due_rechecks(report: AuditReport) -> None:
    due_subscription()
    with patch.object(tasks, "run_audit", fake_engine(report)):
        call_command("run_rechecks")
    checkup = Checkup.objects.get(subscription__isnull=False)
    assert checkup.status == Checkup.Status.DONE


# --- Unsubscribing ---------------------------------------------------------------------


def test_unsubscribe_asks_first_then_stops() -> None:
    subscription = due_subscription()
    client = Client(enforce_csrf_checks=True)  # like a mail app: no CSRF cookie
    url = reverse("checkups:unsubscribe", args=[subscription.token])

    page = client.get(url).content.decode()
    subscription.refresh_from_db()
    assert subscription.active  # opening the link alone changes nothing
    assert "Stop the monthly check-ups of shop.test?" in page

    done = client.post(url).content.decode()  # one-click (RFC 8058) works without CSRF
    subscription.refresh_from_db()
    assert not subscription.active
    assert "stopped" in done


def test_stopped_subscription_sends_no_email(report: AuditReport) -> None:
    subscription = due_subscription(active=False)
    checkup = finished(report)
    Checkup.objects.filter(pk=checkup.pk).update(subscription=subscription)
    checkup.refresh_from_db()

    from bizzcheckup.checkups import emails

    emails.after_checkup(checkup)
    assert mail.outbox == []
