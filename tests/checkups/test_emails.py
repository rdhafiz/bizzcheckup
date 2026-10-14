"""Emails: the report to the visitor ("Email me this report") and lead alerts."""

from unittest.mock import patch

import pytest
from django.core import mail
from django.core.cache import cache
from django.test import Client
from django.urls import reverse
from pytest_django.fixtures import Settings

from bizzcheckup.checkups import emails, services, tasks
from bizzcheckup.checkups.models import Checkup, Lead, ReportEmail
from bizzcheckup.engine.types import AuditReport
from bizzcheckup.reports.branding import load_branding

from .test_checkups import fake_engine

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def email_settings(settings: Settings) -> None:
    settings.SITE_URL = "https://check.example"
    settings.LEAD_ALERT_EMAIL = "owner@example.com"
    settings.LEAD_ALERT_LOW_SCORE = 0
    cache.clear()


def finished(report: AuditReport, lead: Lead | None = None) -> Checkup:
    checkup = Checkup.objects.create(url="https://shop.test/", domain="shop.test", lead=lead)
    services.save_report(checkup, report)
    services.mark_done(checkup)
    return checkup


def by_recipient(address: str) -> list[mail.EmailMessage]:
    return [message for message in mail.outbox if address in message.to]


# --- The report email --------------------------------------------------------------------


def test_report_email_has_the_score_problems_link_and_pdf(report: AuditReport) -> None:
    checkup = finished(report)

    assert emails.send_report(checkup, "amy@shop.test")

    (message,) = mail.outbox
    assert message.subject == "Your BizzCheckup report for shop.test: 66/100"
    assert message.to == ["amy@shop.test"]
    assert message.reply_to == [load_branding().email]  # replies reach the consultant
    link = f"https://check.example/checkups/{checkup.pk}/"
    assert link in message.body
    assert "1. Your homepage has no title." in message.body
    html = message.alternatives[0][0]  # type: ignore[attr-defined]
    assert link in str(html)
    assert f"https://check.example/checkups/{checkup.pk}/report.pdf" in message.body
    assert message.attachments == []  # linked, not attached: small emails send fast


def test_a_failing_mail_server_never_raises(report: AuditReport) -> None:
    checkup = finished(report)
    with patch.object(mail.EmailMultiAlternatives, "send", side_effect=OSError("down")):
        assert emails.send_report(checkup, "amy@shop.test") is False


def test_email_me_this_report_sends_it_and_saves_a_lead(
    client: Client, report: AuditReport
) -> None:
    checkup = finished(report)
    response = client.post(
        reverse("checkups:email_report", args=[checkup.pk]),
        {"email": "Amy@Shop.test", "consent": "on"},
        follow=True,
    )

    assert "sent the report to amy@shop.test" in response.content.decode()
    assert len(by_recipient("amy@shop.test")) == 1
    assert ReportEmail.objects.filter(checkup=checkup, email="amy@shop.test").exists()
    checkup.refresh_from_db()
    assert checkup.lead is not None
    assert checkup.lead.consent is True
    (alert,) = by_recipient("owner@example.com")
    assert "asked for the report by email" in alert.subject
    assert alert.reply_to == ["amy@shop.test"]


def test_email_me_this_report_is_limited_per_day(
    client: Client, report: AuditReport, settings: Settings
) -> None:
    settings.REPORT_EMAILS_PER_DAY = 1
    checkup = finished(report)
    url = reverse("checkups:email_report", args=[checkup.pk])
    client.post(url, {"email": "amy@shop.test"})
    response = client.post(url, {"email": "bob@shop.test"}, follow=True)

    assert "emailed several times today" in response.content.decode()
    assert by_recipient("bob@shop.test") == []


def test_email_me_this_report_ignores_bots_and_bad_addresses(
    client: Client, report: AuditReport
) -> None:
    checkup = finished(report)
    url = reverse("checkups:email_report", args=[checkup.pk])
    client.post(url, {"email": "bot@spam.test", "website": "http://spam.test"})
    response = client.post(url, {"email": "not-an-email"}, follow=True)

    assert mail.outbox == []
    assert "Please enter a valid email address." in response.content.decode()


def test_report_page_has_the_email_form(client: Client, report: AuditReport) -> None:
    checkup = finished(report)
    html = client.get(reverse("checkups:detail", args=[checkup.pk])).content.decode()
    assert reverse("checkups:email_report", args=[checkup.pk]) in html
    assert "Email me the report" in html


# --- After a check-up --------------------------------------------------------------------


def test_finished_checkup_emails_the_visitor_and_alerts_the_owner(report: AuditReport) -> None:
    lead = Lead.objects.create(name="Amy", email="amy@shop.test", consent=True)
    checkup = Checkup.objects.create(url="https://shop.test/", domain="shop.test", lead=lead)

    with patch.object(tasks, "run_audit", fake_engine(report)):
        tasks.run_checkup(str(checkup.pk))

    assert len(by_recipient("amy@shop.test")) == 1
    (alert,) = by_recipient("owner@example.com")
    assert alert.subject == "New lead: shop.test (66/100) left their email"
    assert "Amy" in alert.body
    assert "agreed to be contacted" in alert.body
    assert "Your homepage has no title." in alert.body


def test_anonymous_checkups_send_nothing_unless_the_score_is_low(
    report: AuditReport, settings: Settings
) -> None:
    emails.after_checkup(finished(report))
    assert mail.outbox == []

    settings.LEAD_ALERT_LOW_SCORE = 70  # 66 is below it
    emails.after_checkup(finished(report))
    (alert,) = mail.outbox
    assert "low score" in alert.subject


def test_reused_report_is_emailed_to_a_new_visitor(client: Client, report: AuditReport) -> None:
    finished(report)
    client.post(
        reverse("checkups:start"),
        {"url": "shop.test", "email": "amy@shop.test", "consent": "on"},
    )
    assert len(by_recipient("amy@shop.test")) == 1


# --- "Get a full check-up" -----------------------------------------------------------


def test_full_checkup_link_alerts_once_then_goes_to_the_offer(
    client: Client, report: AuditReport
) -> None:
    checkup = finished(report)
    url = reverse("checkups:full_checkup", args=[checkup.pk])

    first = client.get(url)
    client.get(url)

    assert first.status_code == 302
    assert first["Location"] == load_branding().full_audit_url
    (alert,) = mail.outbox  # one alert, not two
    assert "clicked 'Get a full check-up'" in alert.subject


def test_report_links_to_the_tracked_offer_but_the_pdf_keeps_the_real_one(
    client: Client, report: AuditReport
) -> None:
    from django.template.loader import render_to_string

    from bizzcheckup.reports.builder import build_report

    report = report.model_copy(update={"discovered_pages": [*report.pages, "https://shop.test/a"]})
    checkup = finished(report)
    tracked = reverse("checkups:full_checkup", args=[checkup.pk])

    html = client.get(reverse("checkups:detail", args=[checkup.pk])).content.decode()
    assert tracked in html

    pdf_html = render_to_string("reports/report_pdf.html", {"view": build_report(checkup)})
    assert tracked not in pdf_html
