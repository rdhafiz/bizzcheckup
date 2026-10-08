"""The sitemap (/sitemap.xml): the public pages search engines may list.

Only the homepage and the legal pages. Reports are private links, so they are never in it.
Django builds the full addresses from the incoming request, so the same code works on
localhost and on the real domain.
"""

from datetime import date
from typing import TYPE_CHECKING

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
    def items(self) -> list[str]:
        return ["home", *(name for name, _ in LEGAL_PAGES)]

    def location(self, item: str) -> str:
        return reverse(f"core:{item}")

    def lastmod(self, item: str) -> date | None:
        """Legal pages changed on the "updated" date in branding.yaml; the homepage has none."""
        return None if item == "home" else load_branding().legal.updated


SITEMAPS = {"pages": StaticPagesSitemap}
