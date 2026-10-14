"""Emails: the report to the visitor, and "new lead" alerts to the consultant.

Sent with Django's own email system (SMTP, Gmail by default: see docs/21-emails.md).
Sending must never break a check-up or a page, so every function here logs failures
and returns False instead of raising.
"""

import logging
from datetime import timedelta

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone

from bizzcheckup.reports.branding import load_branding

from .models import Checkup, Lead, ReportEmail, Subscription

logger = logging.getLogger(__name__)


def absolute(path: str) -> str:
    """A full address for a link in an email, e.g. https://bizzcheckup.example/checkups/..."""
    return str(settings.SITE_URL) + path


def report_link(checkup: Checkup) -> str:
    return absolute(reverse("checkups:detail", args=[checkup.pk]))


def top_problems(checkup: Checkup, limit: int = 3) -> list[str]:
    """The report's "Fix these first" messages, in the same order as on the page."""
    from bizzcheckup.reports.builder import build_report  # avoids a circular import

    try:
        return [row.finding.message for row in build_report(checkup).risk_rows[:limit]]
    except Exception:  # an alert without the list is better than no alert
        logger.exception("Couldn't list the problems of check-up %s", checkup.pk)
        return []


def _send(message: EmailMultiAlternatives, what: str) -> bool:
    try:
        message.send()
    except Exception:  # wrong password, mail server down, ...
        logger.exception("Couldn't send %s", what)
        return False
    return True


# --- The report, to the visitor --------------------------------------------------------


def send_report(checkup: Checkup, to: str) -> bool:
    """Email the report: score, top problems, and links to the report and its PDF."""
    brand = load_branding()
    context = {
        "checkup": checkup,
        "brand": brand,
        "link": report_link(checkup),
        "pdf_link": absolute(reverse("reports:pdf", args=[checkup.pk])),
        "problems": top_problems(checkup),
    }
    message = EmailMultiAlternatives(
        subject=(
            f"Your {brand.product_name} report for {checkup.domain}: {checkup.health_score}/100"
        ),
        body=render_to_string("emails/report.txt", context),
        to=[to],
        reply_to=[brand.email],  # replies go to the consultant, not the robot
    )
    message.attach_alternative(render_to_string("emails/report.html", context), "text/html")
    # The PDF is linked, not attached: a 3 MB attachment takes a slow home connection
    # longer to upload than the mail server waits, and small emails reach the inbox more
    # often than big ones.
    return _send(message, f"the report of {checkup.pk} to a visitor")


def emails_left_today(checkup: Checkup) -> int:
    """How many more times this report may be emailed today (REPORT_EMAILS_PER_DAY)."""
    since = timezone.now() - timedelta(days=1)
    sent = ReportEmail.objects.filter(checkup=checkup, created_at__gte=since).count()
    return max(0, int(settings.REPORT_EMAILS_PER_DAY) - sent)


# --- "New lead" alerts, to the consultant ---------------------------------------------


def alert_owner(checkup: Checkup, reason: str, lead: Lead | None = None) -> bool:
    """Tell the consultant about a possible client: who, which site, its score, its problems."""
    brand = load_branding()
    to = settings.LEAD_ALERT_EMAIL or brand.email
    context = {
        "checkup": checkup,
        "lead": lead,
        "reason": reason,
        "link": report_link(checkup),
        "problems": top_problems(checkup),
        "admin_link": absolute(reverse("admin:checkups_checkup_change", args=[checkup.pk])),
    }
    message = EmailMultiAlternatives(
        subject=f"New lead: {checkup.domain} ({checkup.health_score}/100) {reason}",
        body=render_to_string("emails/lead_alert.txt", context),
        to=[to],
        reply_to=[lead.email] if lead else None,  # "Reply" writes to the visitor
    )
    return _send(message, f"a lead alert for {checkup.pk}")


# --- The monthly re-check: what changed ----------------------------------------------

ALERT_ON_DROP = 5  # tell the consultant when a subscribed site's score falls this much


def unsubscribe_link(subscription: Subscription) -> str:
    return absolute(reverse("checkups:unsubscribe", args=[subscription.token]))


def send_monthly(checkup: Checkup, subscription: Subscription) -> bool:
    """The monthly email: the score before and after, what was fixed, what's new."""
    from bizzcheckup.reports.comparison import compare  # avoids a circular import

    brand = load_branding()
    change = compare(checkup)
    stop = unsubscribe_link(subscription)
    context = {
        "checkup": checkup,
        "brand": brand,
        "change": change,
        "link": report_link(checkup),
        "problems": top_problems(checkup),
        "unsubscribe": stop,
    }
    if change and change.health.delta:
        arrow = "▲" if change.health.delta > 0 else "▼"
        movement = f"{change.health.before} → {change.health.after} ({arrow}{change.health.size})"
    else:
        movement = f"{checkup.health_score}/100"
    message = EmailMultiAlternatives(
        subject=f"{checkup.domain} this month: health score {movement}",
        body=render_to_string("emails/monthly.txt", context),
        to=[subscription.email],
        reply_to=[brand.email],
        # One-click "Unsubscribe" in Gmail and Outlook (RFC 8058): they POST to this address.
        headers={
            "List-Unsubscribe": f"<{stop}>",
            "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
        },
    )
    message.attach_alternative(render_to_string("emails/monthly.html", context), "text/html")
    sent = _send(message, f"the monthly email of {checkup.pk}")
    if change and (change.health.delta or 0) <= -ALERT_ON_DROP:
        alert_owner(checkup, f"dropped {change.health.size} points this month", checkup.lead)
    return sent


def after_checkup(checkup: Checkup) -> None:
    """Called when a check-up has finished: send the report and the alert they need."""
    subscription = checkup.subscription
    if subscription is not None:  # a monthly re-check: only the "what changed" email
        if subscription.active:
            send_monthly(checkup, subscription)
        return
    lead = checkup.lead
    if lead is not None:
        if send_report(checkup, lead.email):
            ReportEmail.objects.create(checkup=checkup, email=lead.email)
        alert_owner(checkup, "left their email", lead)
    elif (
        settings.LEAD_ALERT_LOW_SCORE
        and checkup.health_score is not None
        and checkup.health_score < settings.LEAD_ALERT_LOW_SCORE
    ):
        alert_owner(checkup, "has a low score (no contact details)")
