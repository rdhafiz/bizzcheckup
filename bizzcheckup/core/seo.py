"""SEO for BizzCheckup's own pages: one place that decides every page's meta tags.

Each view describes its page with a `PageMeta` (title, description, address, picture,
whether search engines may list it, structured data). `partials/seo.html` turns it into
the tags in <head>: the title, description, canonical link, robots, Open Graph (Facebook,
LinkedIn, WhatsApp), Twitter card and JSON-LD (schema.org). Pages that don't set one get
`default_meta()`, so no page is ever left without tags.

Addresses are built from SITE_URL, the site's real public address, so the canonical link
and the share picture are right even when the page is reached another way (localhost,
the Cloudflare Tunnel, a www. address).
"""

import json
from dataclasses import dataclass, field
from datetime import date
from typing import Any

from django.conf import settings
from django.templatetags.static import static
from django.urls import reverse
from django.utils.html import format_html
from django.utils.safestring import SafeString

from bizzcheckup.reports.branding import Branding, load_branding

# ---------------------------------------------------------------------------------------
# Defaults
# ---------------------------------------------------------------------------------------

SITE_DESCRIPTION = (
    "Free website health check-up for business owners: speed, accessibility, security, "
    "Google visibility and AI readiness, explained in plain language, in about a minute."
)
SHARE_IMAGE = "img/og-image.png"  # 1200 x 630, made from templates/core/og_image.html
SHARE_IMAGE_SIZE = (1200, 630)
INDEX = "index, follow, max-image-preview:large"
NO_INDEX = "noindex, nofollow"  # private pages: reports, progress, unsubscribe, ...

Schema = dict[str, Any]  # one JSON-LD object, e.g. {"@type": "Organization", ...}


# ---------------------------------------------------------------------------------------
# The page description
# ---------------------------------------------------------------------------------------


@dataclass
class PageMeta:
    title: str  # the full <title>, 50-60 characters is ideal
    description: str = SITE_DESCRIPTION  # 120-160 characters is ideal
    path: str = "/"  # the page's address on this site, for the canonical link
    robots: str = INDEX
    og_type: str = "website"  # "website", or "article" for a text page like a policy
    image: str = SHARE_IMAGE  # a static file, or a full https:// address (a report's card)
    image_alt: str = ""
    image_width: int = SHARE_IMAGE_SIZE[0]
    image_height: int = SHARE_IMAGE_SIZE[1]
    updated: date | None = None  # when the content last changed (legal pages)
    schema: list[Schema] = field(default_factory=list)  # JSON-LD objects for this page

    # --- addresses, always on the public domain ---------------------------------------
    @property
    def url(self) -> str:
        return absolute(self.path)

    @property
    def image_url(self) -> str:
        if self.image.startswith(("http://", "https://")):
            return self.image
        return absolute(static(self.image))

    @property
    def indexable(self) -> bool:
        return self.robots.startswith("index")

    # --- the JSON-LD <script> block ----------------------------------------------------
    @property
    def json_ld(self) -> SafeString:
        """The structured data as one <script type="application/ld+json"> block.

        It's a data block, not a script: browsers never run it, so the Content Security
        Policy (no inline scripts) doesn't apply. "<", ">" and "&" are escaped, so a value
        can never close the tag early.
        """
        if not self.schema:
            return SafeString("")
        graph = {"@context": "https://schema.org", "@graph": self.schema}
        text = (
            json.dumps(graph, ensure_ascii=False, separators=(",", ":"))
            .replace("<", "\\u003c")
            .replace(">", "\\u003e")
            .replace("&", "\\u0026")
        )
        return format_html('<script type="application/ld+json">{}</script>', SafeString(text))


def absolute(path: str) -> str:
    """ "/privacy/" -> "https://bizzcheckup.example/privacy/" (SITE_URL + path)."""
    return str(settings.SITE_URL).rstrip("/") + path


# Addresses search engines must never list: private reports and technical pages.
PRIVATE_PATHS = ("/checkups/", "/admin/", "/styleguide/", "/healthz/")


def is_private(path: str) -> bool:
    return path.startswith(PRIVATE_PATHS)


def default_meta(title: str, *, path: str = "/") -> PageMeta:
    """For pages that don't describe themselves: the site's description, noindex if private."""
    return PageMeta(title=title, path=path, robots=NO_INDEX if is_private(path) else INDEX)


# ---------------------------------------------------------------------------------------
# Structured data (schema.org), shared by the pages
# ---------------------------------------------------------------------------------------


def organization(brand: Branding) -> Schema:
    """Who runs BizzCheckup: the consultant from branding.yaml, and where else to find them."""
    same_as = [str(u) for u in (brand.website, brand.github, brand.portfolio_url) if u]
    person: Schema = {
        "@type": "Person",
        "@id": absolute("/#person"),
        "name": brand.name,
        "jobTitle": brand.title,
        "email": f"mailto:{brand.email}",
        "sameAs": same_as,
    }
    if brand.photo_url:
        person["image"] = str(brand.photo_url)
    return person


def website(brand: Branding) -> Schema:
    return {
        "@type": "WebSite",
        "@id": absolute("/#website"),
        "url": absolute("/"),
        "name": brand.product_name,
        "description": SITE_DESCRIPTION,
        "inLanguage": "en",
        "publisher": {"@id": absolute("/#person")},
    }


def web_application(brand: Branding, check_count: int) -> Schema:
    """BizzCheckup itself, as a free web app (this is what search results can show)."""
    return {
        "@type": "WebApplication",
        "@id": absolute("/#app"),
        "name": brand.product_name,
        "url": absolute("/"),
        "applicationCategory": "BusinessApplication",
        "operatingSystem": "Any (runs in the browser)",
        "description": (
            f"Runs {check_count} checks on a business website and explains the results in "
            "plain language, with a treatment plan, quick wins first."
        ),
        "offers": {"@type": "Offer", "price": "0", "priceCurrency": "USD"},
        "image": absolute(static(SHARE_IMAGE)),
        "provider": {"@id": absolute("/#person")},
    }


def faq_page(questions: list[tuple[str, str]]) -> Schema:
    """The FAQ shown on the page, as schema.org FAQPage (the same text, never different)."""
    return {
        "@type": "FAQPage",
        "@id": absolute("/#faq"),
        "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in questions
        ],
    }


def breadcrumbs(*trail: tuple[str, str]) -> Schema:
    """Home > Privacy policy, as schema.org BreadcrumbList. `trail` is (name, path) pairs."""
    return {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": i, "name": name, "item": absolute(path)}
            for i, (name, path) in enumerate(trail, start=1)
        ],
    }


def web_page(meta: PageMeta) -> Schema:
    page: Schema = {
        "@type": "WebPage",
        "@id": meta.url,
        "url": meta.url,
        "name": meta.title,
        "description": meta.description,
        "isPartOf": {"@id": absolute("/#website")},
        "inLanguage": "en",
    }
    if meta.updated:
        page["dateModified"] = meta.updated.isoformat()
    return page


# ---------------------------------------------------------------------------------------
# Each public page's description
# ---------------------------------------------------------------------------------------


def home_meta(check_count: int, faq: list[tuple[str, str]]) -> PageMeta:
    brand = load_branding()
    meta = PageMeta(
        title=f"{brand.product_name}: free website health check-up for business owners",
        description=(
            f"Check your business website for free in about a minute: {check_count} checks "
            "of speed, accessibility, security, Google visibility and AI readiness, "
            "explained in plain language."
        ),
        path=reverse("core:home"),
        image_alt=f"{brand.product_name}: a website health check-up report",
    )
    meta.schema = [
        organization(brand),
        website(brand),
        web_application(brand, check_count),
        web_page(meta),
        faq_page(faq),
    ]
    return meta


def legal_meta(page: str, title: str, description: str) -> PageMeta:
    brand = load_branding()
    path = reverse(f"core:{page}")
    meta = PageMeta(
        title=f"{title} | {brand.product_name}",
        description=description,
        path=path,
        og_type="article",
        updated=brand.legal.updated,
    )
    meta.schema = [web_page(meta), breadcrumbs(("Home", "/"), (title, path))]
    return meta
