"""The site's main URL list: which address is handled by which app."""

from django.contrib import admin
from django.contrib.sitemaps.views import sitemap
from django.urls import include, path

from bizzcheckup.core.sitemaps import SITEMAPS
from bizzcheckup.core.views import llms_txt, robots_txt

urlpatterns = [
    path("admin/", admin.site.urls),
    path("checkups/", include("bizzcheckup.checkups.urls")),
    path("checkups/", include("bizzcheckup.reports.urls")),
    # For search engines. They look for these at the root of the site.
    path("robots.txt", robots_txt, name="robots_txt"),
    path("sitemap.xml", sitemap, {"sitemaps": SITEMAPS}, name="sitemap"),
    path("llms.txt", llms_txt, name="llms_txt"),  # for AI assistants
    path("", include("bizzcheckup.core.urls")),
]
