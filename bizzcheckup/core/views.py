from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render

from bizzcheckup.checkups.forms import CheckupForm
from bizzcheckup.reports.branding import load_branding

# Simple line icons (our own SVG, so |safe is fine in the template).
_ICON = (
    '<svg viewBox="0 0 24 24" width="24" height="24" fill="none" stroke="currentColor" '
    'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{}</svg>'
)
VITAL_SIGNS = [
    {
        "title": "Performance",
        "text": "How fast your pages load on phones and computers, using Google's own speed test.",
        "icon": _ICON.format('<path d="M13 2 3 14h9l-1 8 10-12h-9l1-8z"/>'),
    },
    {
        "title": "Accessibility",
        "text": "Whether everyone can use your site, including people using screen readers.",
        "icon": _ICON.format(
            '<circle cx="12" cy="4.5" r="2"/><path d="M5 8.5 12 10l7-1.5M12 10v5l-3 6M12 15l3 6"/>'
        ),
    },
    {
        "title": "Best practices",
        "text": "Security and modern standards that protect your customers and reputation.",
        "icon": _ICON.format('<path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6l-8-3z"/>'),
    },
    {
        "title": "SEO",
        "text": "Whether Google can find, understand and show your pages to new customers.",
        "icon": _ICON.format('<circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/>'),
    },
    {
        "title": "AI readiness",
        "text": "Whether ChatGPT, Claude and AI search can read and recommend your business.",
        "icon": _ICON.format(
            '<path d="M12 3v3M12 18v3M3 12h3M18 12h3M6 6l2 2M16 16l2 2M6 18l2-2M16 8l2-2"/>'
            '<circle cx="12" cy="12" r="3"/>'
        ),
    },
]


def home(request: HttpRequest) -> HttpResponse:
    """Landing page with the check-up form."""
    return render(request, "core/home.html", {"form": CheckupForm(), "vital_signs": VITAL_SIGNS})


def privacy(request: HttpRequest) -> HttpResponse:
    """What we collect, why, and who sees it."""
    return render(
        request,
        "core/privacy.html",
        {
            "branding": load_branding(),
            "turnstile": bool(settings.TURNSTILE_SITE_KEY and settings.TURNSTILE_SECRET_KEY),
            "reuse_hours": settings.CHECKUP_REUSE_HOURS,
        },
    )


def healthz(request: HttpRequest) -> JsonResponse:
    """Tiny endpoint Docker uses to know the web server is alive."""
    return JsonResponse({"status": "ok"})


def styleguide(request: HttpRequest) -> HttpResponse:
    """All brand building blocks on one page. Only available while DEBUG is on."""
    if not settings.DEBUG:
        raise Http404
    return render(request, "core/styleguide.html")
