"""Report pages (CONTROLLER layer): the web report and its PDF."""

import logging
from uuid import UUID

from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_GET

from bizzcheckup.checkups.models import Checkup
from bizzcheckup.core.seo import NO_INDEX, PageMeta, absolute

from . import pdf as pdf_module
from .builder import ReportView, build_report

logger = logging.getLogger(__name__)


def report_page(request: HttpRequest, checkup: Checkup) -> HttpResponse:
    """The full report. Called by checkups.views.detail for finished check-ups."""
    share_url = request.build_absolute_uri(reverse("checkups:detail", args=[checkup.pk]))
    view = build_report(checkup)
    return render(
        request,
        "reports/report.html",
        {"view": view, "share_url": share_url, "meta": report_meta(view)},
    )


def report_meta(view: ReportView) -> PageMeta:
    """What a shared report link shows (WhatsApp, LinkedIn...): the score and its picture.

    Reports stay private: `noindex`, so search engines never list them, even when someone
    posts the link. The preview is only what people see in a chat when it's shared.
    """
    checkup = view.checkup
    score = view.report.health_score
    return PageMeta(
        title=f"{checkup.domain}: health score {score}/100 | {view.branding.product_name}",
        description=f"{view.verdict} A free website health check-up of {checkup.domain}.",
        path=reverse("checkups:detail", args=[checkup.pk]),
        robots=NO_INDEX,
        image=absolute(reverse("checkups:share_card", args=[checkup.pk])),
        image_alt=f"{checkup.domain}'s health score: {score} out of 100",
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
