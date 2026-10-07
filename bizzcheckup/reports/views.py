"""Report pages (CONTROLLER layer): the web report and its PDF."""

import logging
from uuid import UUID

from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_GET

from bizzcheckup.checkups.models import Checkup

from . import pdf as pdf_module
from .builder import build_report

logger = logging.getLogger(__name__)


def report_page(request: HttpRequest, checkup: Checkup) -> HttpResponse:
    """The full report. Called by checkups.views.detail for finished check-ups."""
    share_url = request.build_absolute_uri(reverse("checkups:detail", args=[checkup.pk]))
    return render(
        request, "reports/report.html", {"view": build_report(checkup), "share_url": share_url}
    )


@require_GET
def pdf(request: HttpRequest, checkup_id: UUID) -> HttpResponse:
    checkup = get_object_or_404(Checkup, pk=checkup_id)
    if checkup.status != Checkup.Status.DONE:
        raise Http404
    try:
        content = pdf_module.ensure_pdf(checkup)
    except Exception:  # e.g. Chromium missing or crashed: never show a raw error page
        logger.exception("PDF for check-up %s failed", checkup.pk)
        return render(request, "reports/pdf_unavailable.html", {"checkup": checkup}, status=503)
    response = HttpResponse(content, content_type="application/pdf")
    filename = f"bizzcheckup-{checkup.domain}-{checkup.finished_at:%Y-%m-%d}.pdf"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'
    return response
