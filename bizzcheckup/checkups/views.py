"""Check-up pages (CONTROLLER layer): start a check-up, show progress, show the result."""

from uuid import UUID

from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from bizzcheckup.core import security

from . import protection, services
from .forms import CheckupForm
from .models import Checkup
from .progress import steps_for

BOT_ERROR = "We couldn't start your check-up. Please reload the page and try again."
RATE_LIMIT_ERROR = (
    "You've started several check-ups in the last hour. Please wait a little before "
    "starting another one."
)
BUSY_ERROR = "We're checking a lot of websites right now. Please try again in a few minutes."


@require_POST
def start(request: HttpRequest) -> HttpResponse:
    """Start a check-up, applying every abuse rule in turn (docs/17-security.md)."""
    form = CheckupForm(request.POST)
    if not form.is_valid():
        return _form_error(request, form, status=400)
    if form.is_bot:  # honeypot filled in
        return _form_error(request, form, BOT_ERROR, status=400)

    ip = security.client_ip(request)
    if security.turnstile_enabled():
        token = request.POST.get("cf-turnstile-response", "")
        if not security.verify_turnstile(token, ip):
            return _form_error(request, form, BOT_ERROR, status=400)

    url = form.cleaned_data["url"]
    # Same site checked recently (or right now)? Show that instead of starting again.
    existing = protection.recent_report(url) or protection.in_progress(url)
    if existing is not None:
        return redirect("checkups:detail", checkup_id=existing.pk)

    ip_hash = security.hash_ip(ip)
    if protection.over_rate_limit(ip_hash):
        return _form_error(request, form, RATE_LIMIT_ERROR, status=429)
    if protection.too_busy():
        return _form_error(request, form, BUSY_ERROR, status=503)

    checkup = services.create_checkup(url, ip_hash=ip_hash)
    return redirect("checkups:detail", checkup_id=checkup.pk)


def _form_error(
    request: HttpRequest, form: CheckupForm, message: str = "", *, status: int
) -> HttpResponse:
    if message:
        form.add_error(None, message)
    return render(request, "core/home.html", {"form": form}, status=status)


@require_GET
def detail(request: HttpRequest, checkup_id: UUID) -> HttpResponse:
    """One address for everything: progress while running, then the report."""
    checkup = get_object_or_404(Checkup, pk=checkup_id)
    if checkup.status == Checkup.Status.FAILED:
        return render(request, "checkups/failed.html", {"checkup": checkup})
    if checkup.status == Checkup.Status.DONE:
        from bizzcheckup.reports.views import report_page

        return report_page(request, checkup)
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
