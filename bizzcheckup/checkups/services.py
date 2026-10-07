"""Business logic for check-ups, shared by views and the Celery task.

Views stay thin: they call these functions instead of doing the work themselves.
"""

import logging
import threading

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from bizzcheckup.engine.config import EngineConfig
from bizzcheckup.engine.netguard import NetGuard
from bizzcheckup.engine.types import AuditReport, Category
from bizzcheckup.engine.urls import domain, normalize_url

from .models import Checkup, Finding, Lead

logger = logging.getLogger(__name__)

QUEUE_DOWN_ERROR = (
    "Our check-up service is busy or temporarily unavailable. Please try again in a few minutes."
)


def engine_config() -> EngineConfig:
    """Engine limits and keys taken from Django settings / environment variables."""
    return EngineConfig(
        max_pages=settings.CHECKUP_MAX_PAGES,
        total_timeout=settings.CHECKUP_TIMEOUT_SECONDS,
        max_page_bytes=settings.CHECKUP_MAX_PAGE_BYTES,
        psi_api_key=settings.PSI_API_KEY,
    )


def make_guard() -> NetGuard:
    """The SSRF guard the worker uses. (Tests replace this to allow a local test site.)"""
    return NetGuard()


def save_lead(*, name: str, email: str, consent: bool) -> Lead | None:
    """Save the visitor's contact details, but only if they left an email."""
    if not email:
        return None
    return Lead.objects.create(name=name, email=email.lower(), consent=consent)


def create_checkup(raw_url: str, *, ip_hash: str = "", lead: Lead | None = None) -> Checkup:
    """Save a new queued check-up and send it to the worker.

    Raises engine.urls.InvalidURLError for addresses that can't be checked.
    """
    url = normalize_url(raw_url)
    checkup = Checkup.objects.create(url=url, domain=domain(url), ip_hash=ip_hash, lead=lead)

    # Only queue the job once the row is really saved, or the worker might not find it.
    transaction.on_commit(lambda: enqueue(checkup))
    return checkup


def enqueue(checkup: Checkup) -> None:
    """Send the check-up to the worker. If the job queue is down, fail it politely."""
    from .tasks import run_checkup  # imported here to avoid a circular import

    if settings.CHECKUP_RUN_WITHOUT_QUEUE and settings.DEBUG:
        run_in_background_thread(str(checkup.pk))
        return
    try:
        run_checkup.delay(str(checkup.pk))
    except Exception:  # e.g. Redis unreachable
        logger.exception("Could not queue check-up %s", checkup.pk)
        mark_failed(checkup, QUEUE_DOWN_ERROR)


def run_in_background_thread(checkup_id: str) -> None:
    """DEVELOPMENT ONLY: run the worker's task in a thread of the dev server.

    The visitor's request still returns at once (the redirect to the progress page);
    the check-up continues in the thread. Only used when CHECKUP_RUN_WITHOUT_QUEUE and
    DEBUG are both on, so it can never happen in production.
    """
    from django.db import connection

    from .tasks import run_checkup

    def work() -> None:
        try:
            run_checkup(checkup_id)  # the exact same code the Celery worker runs
        finally:
            connection.close()  # each thread has its own database connection

    threading.Thread(target=work, name=f"checkup-{checkup_id}", daemon=True).start()


def save_report(checkup: Checkup, report: AuditReport) -> None:
    """Copy a finished engine report onto the check-up and its findings."""
    with transaction.atomic():
        for category in Category:
            setattr(checkup, f"score_{category.value}", report.category(category).score)
        checkup.health_score = report.health_score
        checkup.raw_results = report.model_dump(mode="json")
        checkup.screenshot = report.screenshot_jpeg
        checkup.status = Checkup.Status.DONE
        checkup.progress = 100
        checkup.current_step = "Your report is ready"
        checkup.finished_at = timezone.now()
        checkup.save()

        checkup.findings.all().delete()
        Finding.objects.bulk_create(
            Finding(
                checkup=checkup,
                check_id=f.check_id,
                category=f.category.value,
                severity=f.severity.value,
                message=f.message,
                why_it_matters=f.why_it_matters,
                how_to_fix=f.how_to_fix,
                effort=f.effort.value,
                impact=f.impact.value,
                affected_urls=f.affected_urls,
            )
            for f in report.findings
        )


def mark_failed(checkup: Checkup, message: str) -> None:
    checkup.status = Checkup.Status.FAILED
    checkup.error_message = message
    checkup.current_step = "The check-up couldn't be completed"
    checkup.finished_at = timezone.now()
    checkup.save(update_fields=["status", "error_message", "current_step", "finished_at"])
