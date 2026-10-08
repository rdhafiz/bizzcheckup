"""Check-up pages (CONTROLLER layer): start a check-up, show progress, show the result."""

from uuid import UUID

from asgiref.sync import async_to_sync
from django.contrib import messages
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST

from bizzcheckup.core import security
from bizzcheckup.engine.netguard import BlockedURLError

from . import protection, services
from .forms import CheckupForm
from .models import Checkup, CheckupImage, Lead
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
        lead = _save_lead(form)
        if lead is not None and existing.lead_id is None:
            Checkup.objects.filter(pk=existing.pk).update(lead=lead)
        return redirect("checkups:detail", checkup_id=existing.pk)

    ip_hash = security.hash_ip(ip)
    if protection.over_rate_limit(ip_hash):
        return _form_error(request, form, RATE_LIMIT_ERROR, status=429)
    if protection.too_busy():
        return _form_error(request, form, BUSY_ERROR, status=503)

    checkup = services.create_checkup(url, ip_hash=ip_hash, lead=_save_lead(form))
    return redirect("checkups:detail", checkup_id=checkup.pk)


@require_POST
def recheck(request: HttpRequest, checkup_id: UUID) -> HttpResponse:
    """ "Check again now": a fresh check-up of the same site, skipping report reuse.

    Everything else still applies: a check-up of the site that is already running is
    shown instead, the address passes the SSRF guard again, Turnstile (if on) must
    pass, and it counts towards the visitor's hourly limit.
    """
    previous = get_object_or_404(Checkup, pk=checkup_id)
    back = redirect("checkups:detail", checkup_id=previous.pk)

    running = protection.in_progress(previous.url)
    if running is not None:
        return redirect("checkups:detail", checkup_id=running.pk)

    ip = security.client_ip(request)
    if security.turnstile_enabled():
        token = request.POST.get("cf-turnstile-response", "")
        if not security.verify_turnstile(token, ip):
            messages.error(request, BOT_ERROR)
            return back
    try:
        # The site's address may point somewhere else by now, so check it again.
        async_to_sync(services.make_guard().check_url)(previous.url)
    except BlockedURLError as error:
        messages.error(request, str(error))
        return back

    ip_hash = security.hash_ip(ip)
    if protection.over_rate_limit(ip_hash):
        messages.error(request, RATE_LIMIT_ERROR)
        return back
    if protection.too_busy():
        messages.error(request, BUSY_ERROR)
        return back

    checkup = services.create_checkup(previous.url, ip_hash=ip_hash)
    return redirect("checkups:detail", checkup_id=checkup.pk)


def _save_lead(form: CheckupForm) -> Lead | None:
    return services.save_lead(
        name=form.cleaned_data["name"],
        email=form.cleaned_data["email"],
        consent=form.cleaned_data["consent"],
    )


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
    services.expire_if_stuck(checkup)
    if checkup.status == Checkup.Status.FAILED:
        return render(request, "checkups/failed.html", {"checkup": checkup})
    if checkup.status == Checkup.Status.DONE:
        from bizzcheckup.reports.views import report_page

        return report_page(request, checkup)
    return render(request, "checkups/progress.html", progress_context(checkup))


@require_GET
def progress(request: HttpRequest, checkup_id: UUID) -> HttpResponse:
    """The latest progress as a tiny HTML snippet. HTMX asks for it every second.

    When the check-up has finished, the answer uses status 286, which tells HTMX to
    stop polling. The page's script then plays the "ready" animation and opens the
    report (or the error page).
    """
    checkup = get_object_or_404(Checkup, pk=checkup_id)
    services.expire_if_stuck(checkup)
    status = 286 if checkup.is_finished else 200
    return render(request, "checkups/_progress_data.html", {"checkup": checkup}, status=status)


@require_GET
def screenshot(request: HttpRequest, checkup_id: UUID) -> HttpResponse:
    checkup = get_object_or_404(Checkup.objects.only("screenshot"), pk=checkup_id)
    if not checkup.screenshot:
        raise Http404
    response = HttpResponse(bytes(checkup.screenshot), content_type="image/jpeg")
    response["Cache-Control"] = "public, max-age=86400, immutable"  # it never changes
    return response


@require_GET
def image(request: HttpRequest, checkup_id: UUID, kind: str) -> HttpResponse:
    """A report picture: the link preview picture, or the phone or tablet screenshot."""
    if kind not in CheckupImage.Kind.values:
        raise Http404
    picture = get_object_or_404(CheckupImage, checkup_id=checkup_id, kind=kind)
    if picture.content_type not in CheckupImage.ALLOWED_TYPES:
        raise Http404
    response = HttpResponse(bytes(picture.data), content_type=picture.content_type)
    response["Cache-Control"] = "public, max-age=86400, immutable"
    return response


def progress_context(checkup: Checkup) -> dict[str, object]:
    return {"checkup": checkup, "steps": steps_for(checkup.progress)}
