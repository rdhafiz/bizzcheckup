"""The site's main URL list: which address is handled by which app."""

from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("checkups/", include("bizzcheckup.checkups.urls")),
    path("", include("bizzcheckup.core.urls")),
]
