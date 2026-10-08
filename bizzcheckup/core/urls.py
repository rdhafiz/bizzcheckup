from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    # Legal pages: one view, the page name is passed as an extra argument.
    path("privacy/", views.legal_page, {"page": "privacy"}, name="privacy"),
    path("terms/", views.legal_page, {"page": "terms"}, name="terms"),
    path("cookies/", views.legal_page, {"page": "cookies"}, name="cookies"),
    path("acceptable-use/", views.legal_page, {"page": "acceptable_use"}, name="acceptable_use"),
    path("disclaimer/", views.legal_page, {"page": "disclaimer"}, name="disclaimer"),
    path("healthz/", views.healthz, name="healthz"),
    path("styleguide/", views.styleguide, name="styleguide"),
]
