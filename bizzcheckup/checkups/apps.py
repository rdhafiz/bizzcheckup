from django.apps import AppConfig


class CheckupsConfig(AppConfig):
    """Check-ups, their findings and leads; runs the audit engine in Celery."""

    name = "bizzcheckup.checkups"
    label = "checkups"
    verbose_name = "Check-ups"
