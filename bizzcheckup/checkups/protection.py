"""Abuse protection for starting check-ups: reuse, rate limit, global capacity.

Strangers can start check-ups, and each one costs real resources (a browser,
dozens of requests, a PageSpeed call), so these rules keep BizzCheckup fair
and available. All counts come from the database, so they work the same with
one web server or many.
"""

from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from .models import Checkup

ACTIVE = (Checkup.Status.QUEUED, Checkup.Status.RUNNING)


def recent_report(url: str) -> Checkup | None:
    """A finished check-up of the same URL from the last CHECKUP_REUSE_HOURS hours."""
    since = timezone.now() - timedelta(hours=settings.CHECKUP_REUSE_HOURS)
    return (
        Checkup.objects.filter(url=url, status=Checkup.Status.DONE, created_at__gte=since)
        .order_by("-created_at")
        .first()
    )


def in_progress(url: str) -> Checkup | None:
    """A check-up of the same URL that is still waiting or running."""
    return Checkup.objects.filter(url=url, status__in=ACTIVE).order_by("-created_at").first()


def over_rate_limit(ip_hash: str) -> bool:
    """Has this visitor started CHECKUP_RATE_LIMIT_PER_HOUR check-ups in the last hour?"""
    if not ip_hash:
        return False
    since = timezone.now() - timedelta(hours=1)
    started = (
        Checkup.objects.filter(ip_hash=ip_hash, created_at__gte=since)
        # Check-ups that never started because OUR job queue was down aren't the
        # visitor's fault, so they don't count.
        .exclude(status=Checkup.Status.FAILED, started_at__isnull=True)
        .count()
    )
    return started >= int(settings.CHECKUP_RATE_LIMIT_PER_HOUR)


def too_busy() -> bool:
    """Are CHECKUP_QUEUE_CAP check-ups already waiting or running (for everyone)?"""
    return Checkup.objects.filter(status__in=ACTIVE).count() >= int(settings.CHECKUP_QUEUE_CAP)
