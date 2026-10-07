"""The background job that runs a check-up. Only the Celery worker runs this."""

import logging

from asgiref.sync import async_to_sync, sync_to_async
from celery import shared_task
from celery.exceptions import SoftTimeLimitExceeded
from django.utils import timezone

from bizzcheckup.engine.runner import AuditError, run_audit

from . import services
from .models import Checkup

logger = logging.getLogger(__name__)

GENERIC_ERROR = (
    "Something went wrong on our side while checking your website. "
    "Please try again in a few minutes."
)
TIMEOUT_ERROR = "Your website took too long to check. Please try again in a few minutes."


@shared_task(acks_late=True)
def run_checkup(checkup_id: str) -> None:
    checkup = Checkup.objects.filter(pk=checkup_id, status=Checkup.Status.QUEUED).first()
    if checkup is None:
        return  # unknown, or already picked up by another worker

    checkup.status = Checkup.Status.RUNNING
    checkup.started_at = timezone.now()
    checkup.current_step = "Starting your check-up"
    checkup.save(update_fields=["status", "started_at", "current_step"])

    async def on_progress(percent: int, step: str) -> None:
        # The engine is async but Django's database calls are not. sync_to_async hands the
        # call back to this task's own thread (and its database connection).
        await sync_to_async(Checkup.objects.filter(pk=checkup.pk).update, thread_sensitive=True)(
            progress=percent, current_step=step
        )

    try:
        # async_to_sync runs the async engine to completion from this normal function.
        report = async_to_sync(run_audit)(
            checkup.url,
            services.engine_config(),
            on_progress=on_progress,
            guard=services.make_guard(),
        )
    except AuditError as error:
        services.mark_failed(checkup, str(error))  # already a friendly message
        return
    except SoftTimeLimitExceeded:
        services.mark_failed(checkup, TIMEOUT_ERROR)
        return
    except Exception:
        logger.exception("Check-up %s crashed", checkup.pk)
        services.mark_failed(checkup, GENERIC_ERROR)
        return

    checkup.refresh_from_db()
    services.save_report(checkup, report)

    # Make the PDF now, so "Download PDF" is instant when the report appears. If it
    # fails, the report still opens and the download view tries again later.
    try:
        from bizzcheckup.reports.pdf import ensure_pdf

        ensure_pdf(checkup)
    except Exception:
        logger.exception("PDF for check-up %s failed", checkup.pk)
    services.mark_done(checkup)
