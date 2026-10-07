"""Check-up pages (CONTROLLER layer): start a check-up, show progress, show the result."""

from uuid import UUID

from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from . import services
from .forms import CheckupForm
from .models import Checkup
from .progress import steps_for


@require_POST
def start(request: HttpRequest) -> HttpResponse:
    form = CheckupForm(request.POST)
    if not form.is_valid():
        return render(request, "core/home.html", {"form": form}, status=400)
    checkup = services.create_checkup(form.cleaned_data["url"])
    return redirect("checkups:detail", checkup_id=checkup.pk)


@require_GET
def detail(request: HttpRequest, checkup_id: UUID) -> HttpResponse:
    """One address for everything: progress while running, then the report."""
    checkup = get_object_or_404(Checkup, pk=checkup_id)
    if checkup.status == Checkup.Status.FAILED:
        return render(request, "checkups/failed.html", {"checkup": checkup})
    if checkup.status == Checkup.Status.DONE:
        return render(request, "checkups/report.html", {"checkup": checkup})
    return render(request, "checkups/progress.html", progress_context(checkup))


@require_GET
def progress(request: HttpRequest, checkup_id: UUID) -> HttpResponse:
    """The progress box only. HTMX asks for it every 2 seconds."""
    checkup = get_object_or_404(Checkup, pk=checkup_id)
    if checkup.is_finished:
        # Tell HTMX to reload the whole page, which now shows the report (or the error).
        response = HttpResponse(status=204)
        response["HX-Refresh"] = "true"
        return response
    return render(request, "checkups/_progress.html", progress_context(checkup))


@require_GET
def screenshot(request: HttpRequest, checkup_id: UUID) -> HttpResponse:
    checkup = get_object_or_404(Checkup.objects.only("screenshot"), pk=checkup_id)
    if not checkup.screenshot:
        raise Http404
    response = HttpResponse(bytes(checkup.screenshot), content_type="image/jpeg")
    response["Cache-Control"] = "public, max-age=86400, immutable"  # it never changes
    return response


def progress_context(checkup: Checkup) -> dict[str, object]:
    return {"checkup": checkup, "steps": steps_for(checkup.progress)}
