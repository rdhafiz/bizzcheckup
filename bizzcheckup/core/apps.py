from django.apps import AppConfig


class CoreConfig(AppConfig):
    """Site-wide pages and helpers: landing page, privacy, health check."""

    name = "bizzcheckup.core"
    label = "core"
