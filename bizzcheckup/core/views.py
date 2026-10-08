from functools import lru_cache

from django.conf import settings
from django.http import Http404, HttpRequest, HttpResponse, JsonResponse
from django.shortcuts import render
from django.urls import reverse

from bizzcheckup.checkups.forms import CheckupForm
from bizzcheckup.engine.registry import load_builtin_checks

# The five vital signs on the homepage. `icon` is a name from templates/partials/icon.html,
# `tone` one of the accent colours in frontend/tailwind.css (tone-green, tone-blue, ...).
VITAL_SIGNS = [
    {
        "title": "Performance",
        "text": "How fast your pages load on phones and computers, using Google's own speed test.",
        "icon": "chart-solid",
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
        "icon": "shield-solid",
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
        "icon": "sparkles-solid",
        "tone": "amber",
    },
]


@lru_cache(maxsize=1)
def check_count() -> int:
    """How many checks the engine runs (45 today). Counted once, then remembered."""
    return len(load_builtin_checks().all())


def how_it_works_steps(max_pages: int, checks: int) -> list[dict[str, object]]:
    """The "How it works" timeline. The numbers come from the settings and the engine, so the
    text can't promise more (or less) than the app does. `icon`: partials/icon.html,
    `art`: partials/step_art.html."""
    return [
        {
            "title": "Enter your address",
            "text": "Type your website's address. No account, no installation, nothing to add "
            "to your site. Your name and email are optional, for follow-up tips.",
            "facts": ["No account", "Name and email optional", "Free"],
            "icon": "globe",
            "art": "address",
            "tone": "teal",
        },
        {
            "title": "We visit like a customer",
            "text": f"We open up to {max_pages} public pages the way a customer, Google and an "
            "AI assistant would: robots.txt and sitemap first, and we never log in or fill in "
            "forms.",
            "facts": [f"Up to {max_pages} pages", "Respects robots.txt", "Public pages only"],
            "icon": "seo",
            "art": "visit",
            "tone": "blue",
        },
        {
            "title": f"{checks} checks, while you watch",
            "text": "Google PageSpeed measures your speed, a real browser opens your homepage, an "
            "accessibility scan looks for barriers and we test what AI assistants can read, "
            "live on screen.",
            "facts": ["Google PageSpeed", "Real browser", "Accessibility scan", "AI readiness"],
            "icon": "chart",
            "art": "checks",
            "tone": "violet",
        },
        {
            "title": "Get your Health Report",
            "text": "A Business Health Score from 0 to 100, your five vital signs and the top "
            "risks to your business, each explained in plain language with its fix. On a "
            "private page and as a PDF.",
            "facts": ["Score 0 to 100", "Top risks first", "PDF to share"],
            "icon": "file",
            "art": "report",
            "tone": "amber",
        },
        {
            "title": "Fix, then check again",
            "text": "Follow the treatment plan, quick wins first, ticking steps off as you go. "
            "Then check again to see your new score, or book a free review call for a hand.",
            "facts": ["Quick wins first", "Check again anytime", "Free review call"],
            "icon": "growth",
            "art": "fix",
            "tone": "rose",
        },
    ]


def home(request: HttpRequest) -> HttpResponse:
    """Landing page with the check-up form."""
    checks = check_count()
    return render(
        request,
        "core/home.html",
        {
            "form": CheckupForm(),
            "vital_signs": VITAL_SIGNS,
            "check_count": checks,
            "steps": how_it_works_steps(settings.CHECKUP_MAX_PAGES, checks),
        },
    )


# The legal pages: (URL name, menu label). Each has a template in templates/core/legal/.
LEGAL_PAGES = [
    ("privacy", "Privacy policy"),
    ("terms", "Terms of service"),
    ("cookies", "Cookie policy"),
    ("acceptable_use", "Acceptable use"),
    ("disclaimer", "Disclaimer"),
]


def legal_page(request: HttpRequest, page: str) -> HttpResponse:
    """One legal page. The numbers in the text come from the settings, so they never go stale."""
    return render(
        request,
        f"core/legal/{page}.html",
        {
            "page": page,
            "legal_pages": LEGAL_PAGES,
            "turnstile": bool(settings.TURNSTILE_SITE_KEY and settings.TURNSTILE_SECRET_KEY),
            "reuse_hours": settings.CHECKUP_REUSE_HOURS,
            "rate_limit": settings.CHECKUP_RATE_LIMIT_PER_HOUR,
            "max_pages": settings.CHECKUP_MAX_PAGES,
        },
    )


# Private or technical areas crawlers should stay out of. /checkups/ holds the reports
# (private links) and their progress pages, so well-behaved bots, AI crawlers included,
# never read a client's report.
ROBOTS_DISALLOW = ["/checkups/", "/admin/", "/healthz/", "/styleguide/"]


def robots_txt(request: HttpRequest) -> HttpResponse:
    """/robots.txt: what search engines may crawl, and where the sitemap is."""
    lines = [
        "User-agent: *",
        *(f"Disallow: {path}" for path in ROBOTS_DISALLOW),
        "Allow: /",
        "",
        f"Sitemap: {request.build_absolute_uri(reverse('sitemap'))}",
        "",
    ]
    return HttpResponse("\n".join(lines), content_type="text/plain; charset=utf-8")


def llms_txt(request: HttpRequest) -> HttpResponse:
    """/llms.txt: a short Markdown guide to the site for AI assistants (https://llmstxt.org)."""
    return render(
        request,
        "core/llms.txt",
        {
            # Links must be absolute; built from the request, like robots.txt.
            "base_url": request.build_absolute_uri("/").rstrip("/"),
            "vital_signs": VITAL_SIGNS,
            "max_pages": settings.CHECKUP_MAX_PAGES,
            "rate_limit": settings.CHECKUP_RATE_LIMIT_PER_HOUR,
        },
        content_type="text/plain; charset=utf-8",
    )


def healthz(request: HttpRequest) -> JsonResponse:
    """Tiny endpoint Docker uses to know the web server is alive."""
    return JsonResponse({"status": "ok"})


def styleguide(request: HttpRequest) -> HttpResponse:
    """All brand building blocks on one page. Only available while DEBUG is on."""
    if not settings.DEBUG:
        raise Http404
    return render(request, "core/styleguide.html")
