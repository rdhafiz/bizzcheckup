from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render

from bizzcheckup.checkups.forms import CheckupForm
from bizzcheckup.reports.branding import load_branding

# The five vital signs on the homepage. `icon` is a name from templates/partials/icon.html,
# `tone` one of the accent colours in frontend/tailwind.css (tone-green, tone-blue, ...).
VITAL_SIGNS = [
    {
        "title": "Performance",
        "text": "How fast your pages load on phones and computers, using Google's own speed test.",
        "icon": "chart",
        "tone": "green",
    },
    {
        "title": "Accessibility",
        "text": "Whether everyone can use your site, including people using screen readers.",
        "icon": "accessibility",
        "tone": "blue",
    },
    {
        "title": "Best practices",
        "text": "Security and modern standards that protect your customers and reputation.",
        "icon": "shield",
        "tone": "rose",
    },
    {
        "title": "SEO",
        "text": "Whether Google can find, understand and show your pages to new customers.",
        "icon": "seo",
        "tone": "violet",
    },
    {
        "title": "AI readiness",
        "text": "Whether ChatGPT, Claude and AI search can read and recommend your business.",
        "icon": "sparkles",
        "tone": "amber",
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
