"""Check-up pages (CONTROLLER layer): start a check-up, show progress, show the result."""

import logging
from uuid import UUID

from asgiref.sync import async_to_sync
from django.contrib import messages
from django.core.cache import cache
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods, require_POST

from bizzcheckup.core import security
from bizzcheckup.engine.netguard import BlockedURLError
from bizzcheckup.engine.urls import domain, site_root
from bizzcheckup.reports.branding import load_branding

from . import badges, emails, protection, services
from .forms import CheckupForm, CompetitorForm, EmailReportForm
from .models import Checkup, CheckupImage, Lead, ReportEmail, Subscription
from .progress import steps_for

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------------------
# Messages shown to visitors
# ---------------------------------------------------------------------------------------

BOT_ERROR = "We couldn't start your check-up. Please reload the page and try again."
RATE_LIMIT_ERROR = (
    "You've started several check-ups in the last hour. Please wait a little before "
    "starting another one."
)
BUSY_ERROR = "We're checking a lot of websites right now. Please try again in a few minutes."
# Shown when the visitor entered the address of one page: we check the whole site instead.
PAGE_DROPPED_NOTE = (
    "The free check-up covers your website from its main address, so we checked {domain} "
    "from its homepage. Checking specific pages, or every page of your website, is part of "
    "the full check-up: see the offer at the end of your report."
)


# ---------------------------------------------------------------------------------------
# Starting a check-up (the homepage form, "Check again now")
# ---------------------------------------------------------------------------------------


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
    if form.page_dropped:
        messages.info(request, PAGE_DROPPED_NOTE.format(domain=domain(url)))
    # Same site checked recently (or right now)? Show that instead of starting again.
    existing = protection.recent_report(url) or protection.in_progress(url)
    if existing is not None:
        lead = _save_lead(form)
        _subscribe(form, lead, url)
        if lead is not None and existing.lead_id is None:
            Checkup.objects.filter(pk=existing.pk).update(lead=lead)
            existing.lead = lead
            if existing.status == Checkup.Status.DONE:  # still running: sent when it ends
                emails.after_checkup(existing)
        return redirect("checkups:detail", checkup_id=existing.pk)

    ip_hash = security.hash_ip(ip)
    if protection.over_rate_limit(ip_hash):
        return _form_error(request, form, RATE_LIMIT_ERROR, status=429)
    if protection.too_busy():
        return _form_error(request, form, BUSY_ERROR, status=503)

    lead = _save_lead(form)
    _subscribe(form, lead, url)
    checkup = services.create_checkup(url, ip_hash=ip_hash, lead=lead)
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
    url = site_root(previous.url)  # older check-ups may have been made from a page address

    running = protection.in_progress(url)
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
        async_to_sync(services.make_guard().check_url)(url)
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

    checkup = services.create_checkup(url, ip_hash=ip_hash)
    return redirect("checkups:detail", checkup_id=checkup.pk)


# ---------------------------------------------------------------------------------------
# Compare with a competitor
# ---------------------------------------------------------------------------------------

COMPETITOR_SAME = "That's your own website: enter a competitor's address to compare."
COMPETITOR_STARTED = (
    "We're checking {domain} now. It takes about a minute: reload this page to see the comparison."
)


@require_POST
def compare(request: HttpRequest, checkup_id: UUID) -> HttpResponse:
    """ "Compare with a competitor": check their site (same rules as any check-up)."""
    checkup = get_object_or_404(Checkup, pk=checkup_id, status=Checkup.Status.DONE)
    back = redirect(reverse("checkups:detail", args=[checkup.pk]) + "#competitor")
    form = CompetitorForm(request.POST)
    if not form.is_valid():
        messages.error(request, str(form.errors["url"][0]))
        return back
    url = form.cleaned_data["url"]
    if url == checkup.url:
        messages.error(request, COMPETITOR_SAME)
        return back

    theirs = protection.recent_report(url) or protection.in_progress(url)
    if theirs is None:
        ip_hash = security.hash_ip(security.client_ip(request))
        if protection.over_rate_limit(ip_hash):
            messages.error(request, RATE_LIMIT_ERROR)
            return back
        if protection.too_busy():
            messages.error(request, BUSY_ERROR)
            return back
        theirs = services.create_checkup(url, ip_hash=ip_hash)
    Checkup.objects.filter(pk=checkup.pk).update(competitor=theirs)
    if theirs.status != Checkup.Status.DONE:
        messages.success(request, COMPETITOR_STARTED.format(domain=theirs.domain))
    return back


# ---------------------------------------------------------------------------------------
# Email me the report, and the full check-up offer
# ---------------------------------------------------------------------------------------

EMAIL_SENT = (
    "We've sent the report to {email}. It should arrive in a minute (check your spam folder too)."
)
EMAIL_FAILED = (
    "We couldn't send the email right now. Please try again in a few minutes, or download the PDF."
)
EMAIL_LIMIT = "This report has been emailed several times today. Please download the PDF instead."
EMAIL_INVALID = "Please enter a valid email address."


@require_POST
def email_report(request: HttpRequest, checkup_id: UUID) -> HttpResponse:
    """ "Email me this report": send the report (with its PDF) to the address given."""
    checkup = get_object_or_404(Checkup, pk=checkup_id, status=Checkup.Status.DONE)
    back = redirect("checkups:detail", checkup_id=checkup.pk)
    form = EmailReportForm(request.POST)
    if not form.is_valid():
        messages.error(request, EMAIL_INVALID)
        return back
    if form.is_bot:
        return back  # say nothing to a bot
    if emails.emails_left_today(checkup) <= 0:
        messages.error(request, EMAIL_LIMIT)
        return back

    address = form.cleaned_data["email"].lower()
    if not emails.send_report(checkup, address):
        messages.error(request, EMAIL_FAILED)
        return back
    ip_hash = security.hash_ip(security.client_ip(request))
    ReportEmail.objects.create(checkup=checkup, email=address, ip_hash=ip_hash)

    # They left an email: that's a lead, kept like the homepage form's.
    lead = services.save_lead(name="", email=address, consent=form.cleaned_data["consent"])
    if lead is not None and checkup.lead_id is None:
        Checkup.objects.filter(pk=checkup.pk).update(lead=lead)
    if form.cleaned_data["monthly"]:
        services.subscribe(address, checkup.url, lead)
    emails.alert_owner(checkup, "asked for the report by email", lead)
    messages.success(request, EMAIL_SENT.format(email=address))
    return back


@require_GET
def full_checkup(request: HttpRequest, checkup_id: UUID) -> HttpResponse:
    """ "Get a full check-up": tell the consultant (once a day per report), then go to
    the offer's address from branding.yaml."""
    checkup = get_object_or_404(Checkup, pk=checkup_id, status=Checkup.Status.DONE)
    key = f"full-checkup-alert:{checkup.pk}"
    if cache.add(key, True, timeout=24 * 60 * 60):  # add() is False if already there
        emails.alert_owner(checkup, "clicked 'Get a full check-up'", checkup.lead)
    return redirect(load_branding().full_audit_url)


# ---------------------------------------------------------------------------------------
# Pictures to share: the score card and the badge
# ---------------------------------------------------------------------------------------


@require_GET
def share_card(request: HttpRequest, checkup_id: UUID) -> HttpResponse:
    """The score as a 1200 x 630 picture to post on social media (made once, then kept)."""
    from bizzcheckup.reports.share_card import ensure_share_card  # avoids a circular import

    checkup = get_object_or_404(Checkup, pk=checkup_id, status=Checkup.Status.DONE)
    try:
        png = ensure_share_card(checkup)
    except Exception as error:  # e.g. Chromium missing: never a raw error page
        logger.exception("Share card for %s failed", checkup.pk)
        raise Http404 from error
    response = HttpResponse(png, content_type="image/png")
    response["Cache-Control"] = "public, max-age=86400, immutable"  # it never changes
    if request.GET.get("download"):
        name = f"bizzcheckup-{checkup.domain}-score.png"
        response["Content-Disposition"] = f'attachment; filename="{name}"'
    return response


@require_GET
def badge(request: HttpRequest, checkup_id: UUID) -> HttpResponse:
    """An SVG badge with the website's latest health score, to show on the site itself.

    It always shows the newest finished check-up of the same address (e.g. the monthly
    re-check), so an old badge never shows an old score.
    """
    first = get_object_or_404(Checkup, pk=checkup_id, status=Checkup.Status.DONE)
    svg = badges.badge_svg(first)
    response = HttpResponse(svg, content_type="image/svg+xml; charset=utf-8")
    response["Cache-Control"] = "public, max-age=3600"  # new scores show within an hour
    # Other websites may show this picture (everything else here is same-origin only).
    response["Cross-Origin-Resource-Policy"] = "cross-origin"
    # An SVG can hold scripts: this one never does, and this tells browsers to run none.
    response["Content-Security-Policy"] = "default-src 'none'; style-src 'unsafe-inline'"
    return response


# ---------------------------------------------------------------------------------------
# Monthly re-checks: unsubscribe
# ---------------------------------------------------------------------------------------


@csrf_exempt  # the secret token in the address is the protection; mail apps POST here
@require_http_methods(["GET", "POST"])
def unsubscribe(request: HttpRequest, token: UUID) -> HttpResponse:
    """Stop the monthly re-checks. GET asks first (link checkers open links); POST stops.

    Gmail's and Outlook's own "Unsubscribe" button POSTs here directly (RFC 8058).
    """
    subscription = get_object_or_404(Subscription, token=token)
    if request.method == "POST" and subscription.active:
        services.unsubscribe(subscription)
    return render(request, "checkups/unsubscribe.html", {"subscription": subscription})


# ---------------------------------------------------------------------------------------
# Helpers for the forms above
# ---------------------------------------------------------------------------------------


def _subscribe(form: CheckupForm, lead: Lead | None, url: str) -> None:
    """The visitor ticked "re-check every month" and left an email: remember it."""
    if lead is not None and form.cleaned_data.get("monthly"):
        services.subscribe(lead.email, url, lead)


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


# ---------------------------------------------------------------------------------------
# The check-up page: progress while it runs, then the report
# ---------------------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------------------
# Pictures of the checked website
# ---------------------------------------------------------------------------------------


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
    """A report picture: link preview, phone or tablet screenshot, or a flagged element."""
    if not CheckupImage.is_known_kind(kind):
        raise Http404
    picture = get_object_or_404(CheckupImage, checkup_id=checkup_id, kind=kind)
    if picture.content_type not in CheckupImage.ALLOWED_TYPES:
        raise Http404
    response = HttpResponse(bytes(picture.data), content_type=picture.content_type)
    response["Cache-Control"] = "public, max-age=86400, immutable"
    return response


def progress_context(checkup: Checkup) -> dict[str, object]:
    return {"checkup": checkup, "steps": steps_for(checkup.progress)}
