"""The site's main URL list: which address is handled by which app."""

from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path

from bizzcheckup.core.sitemaps import SITEMAPS
from bizzcheckup.core.views import llms_txt, robots_txt, security_txt

urlpatterns = [
    # ===== Admin ========================================================================
    path("admin/", admin.site.urls),
    # ===== Check-ups and their reports (private links, never indexed) ====================
    path("checkups/", include("bizzcheckup.checkups.urls")),
    path("checkups/", include("bizzcheckup.reports.urls")),
    # ===== For search engines and AI assistants: they look for these at the root =========
    path("robots.txt", robots_txt, name="robots_txt"),
    path("sitemap.xml", sitemap, {"sitemaps": SITEMAPS}, name="sitemap"),
    path("llms.txt", llms_txt, name="llms_txt"),
    path(".well-known/security.txt", security_txt, name="security_txt"),
    # ===== Public pages: the homepage and the policies ===================================
    path("", include("bizzcheckup.core.urls")),
]
