"""Business logic for check-ups, shared by views and the Celery task.

Views stay thin: they call these functions instead of doing the work themselves.
"""

import logging
import threading
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from bizzcheckup.engine.config import EngineConfig
from bizzcheckup.engine.netguard import NetGuard
from bizzcheckup.engine.types import AuditReport, Category
from bizzcheckup.engine.urls import domain, normalize_url

from .models import Checkup, Finding, Lead

logger = logging.getLogger(__name__)

STUCK_ERROR = "Your check-up was interrupted before it could finish. Please try again."
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
    """Start the check-up: immediately in this web app, or through the Celery queue."""
    if settings.CHECKUP_RUNNER == "celery":
        from .tasks import run_checkup  # imported here to avoid a circular import

        try:
            run_checkup.delay(str(checkup.pk))
        except Exception:  # e.g. Redis unreachable
            logger.exception("Could not queue check-up %s", checkup.pk)
            mark_failed(checkup, QUEUE_DOWN_ERROR)
        return
    run_in_background_thread(str(checkup.pk))


_slots_lock = threading.Lock()
_slots: threading.BoundedSemaphore | None = None


def _concurrency_slots() -> threading.BoundedSemaphore:
    """At most CHECKUP_MAX_CONCURRENT check-ups run at once in this process."""
    global _slots
    with _slots_lock:
        if _slots is None:
            _slots = threading.BoundedSemaphore(settings.CHECKUP_MAX_CONCURRENT)
        return _slots


def run_in_background_thread(checkup_id: str) -> None:
    """Run the check-up right away in a background thread of this web app.

    The visitor's request returns at once (the redirect to the progress page), and
    the check-up continues in the thread. Extra check-ups wait for a free slot, so at
    most CHECKUP_MAX_CONCURRENT run at the same time.
    """
    from django.db import connection

    from .tasks import run_checkup

    def work() -> None:
        try:
            with _concurrency_slots():
                run_checkup(checkup_id)  # the same code the Celery worker runs
        except Exception:
            logger.exception("Check-up %s crashed in its thread", checkup_id)
        finally:
            connection.close()  # each thread has its own database connection

    threading.Thread(target=work, name=f"checkup-{checkup_id}", daemon=True).start()


def expire_if_stuck(checkup: Checkup) -> None:
    """Fail a check-up that can no longer finish (e.g. the server restarted mid-way).

    Anything still waiting or running long after the time limit is marked failed, so
    the progress page never spins forever.
    """
    if checkup.is_finished:
        return
    limit = timedelta(seconds=settings.CHECKUP_TIMEOUT_SECONDS + 120)
    if timezone.now() - checkup.created_at > limit:
        mark_failed(checkup, STUCK_ERROR)


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
