from django.urls import path

from . import views

app_name = "checkups"

urlpatterns = [
    path("new/", views.start, name="start"),
    path("<uuid:checkup_id>/", views.detail, name="detail"),
    path("<uuid:checkup_id>/progress/", views.progress, name="progress"),
    path("<uuid:checkup_id>/recheck/", views.recheck, name="recheck"),
    path("<uuid:checkup_id>/email/", views.email_report, name="email_report"),
    path("<uuid:checkup_id>/compare/", views.compare, name="compare"),
    path("<uuid:checkup_id>/full-checkup/", views.full_checkup, name="full_checkup"),
    path("unsubscribe/<uuid:token>/", views.unsubscribe, name="unsubscribe"),
    path("<uuid:checkup_id>/badge.svg", views.badge, name="badge"),
    path("<uuid:checkup_id>/share.png", views.share_card, name="share_card"),
    path("<uuid:checkup_id>/screenshot.jpg", views.screenshot, name="screenshot"),
    path("<uuid:checkup_id>/images/<slug:kind>/", views.image, name="image"),
]
