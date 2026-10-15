"""The sitemap (/sitemap.xml): the public pages search engines may list.

Only the homepage and the legal pages. Reports are private links, so they are never in it.
The full addresses use SITE_URL, like the canonical links, so they always match.
"""

from datetime import date
from typing import TYPE_CHECKING, Any
from urllib.parse import urlsplit

from django.conf import settings
from django.contrib.sitemaps import Sitemap
from django.urls import reverse

from bizzcheckup.reports.branding import load_branding

from .views import LEGAL_PAGES

# The type checker knows Sitemap as generic (Sitemap[str]: each item is a URL name), but
# the real class isn't, so `Sitemap[str]` would crash when the app starts. Give each its own.
if TYPE_CHECKING:
    PagesSitemapBase = Sitemap[str]
else:
    PagesSitemapBase = Sitemap


class StaticPagesSitemap(PagesSitemapBase):
    # ----- Which pages ------------------------------------------------------------------
    def items(self) -> list[str]:
        return ["home", *(name for name, _ in LEGAL_PAGES)]

    def location(self, item: str) -> str:
        return reverse(f"core:{item}")

    def lastmod(self, item: str) -> date | None:
        """Legal pages changed on the "updated" date in branding.yaml; the homepage has none."""
        return None if item == "home" else load_branding().legal.updated

    # ----- Their addresses: always the public domain (SITE_URL) ------------------------
    # The same addresses as the canonical links (core/seo.py), even when the sitemap is
    # opened through localhost or the tunnel.
    def get_protocol(self, protocol: str | None = None) -> str:
        return urlsplit(str(settings.SITE_URL)).scheme or "https"

    def get_domain(self, site: Any = None) -> str:
        return urlsplit(str(settings.SITE_URL)).netloc


SITEMAPS = {"pages": StaticPagesSitemap}
