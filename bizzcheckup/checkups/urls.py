from django.urls import path

from . import views

app_name = "checkups"

urlpatterns = [
    path("new/", views.start, name="start"),
    path("<uuid:checkup_id>/", views.detail, name="detail"),
    path("<uuid:checkup_id>/progress/", views.progress, name="progress"),
    path("<uuid:checkup_id>/screenshot.jpg", views.screenshot, name="screenshot"),
]
