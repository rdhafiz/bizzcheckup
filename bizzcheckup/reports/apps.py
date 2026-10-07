from typing import Any

from django.apps import AppConfig
from django.core import checks


class ReportsConfig(AppConfig):
    """The Health Report: report page, treatment plan, proposal, contact, PDF."""

    name = "bizzcheckup.reports"
    label = "reports"

    def ready(self) -> None:
        checks.register(check_branding_file)


def check_branding_file(app_configs: Any = None, **kwargs: Any) -> list[checks.CheckMessage]:
    """`manage.py check` (and every server start) validates branding.yaml."""
    import yaml
    from pydantic import ValidationError

    from .branding import load_branding

    try:
        load_branding()
    except FileNotFoundError:
        return [checks.Error("branding.yaml is missing.", id="reports.E001")]
    except (ValidationError, ValueError, yaml.YAMLError) as error:
        return [
            checks.Error(
                "branding.yaml has a mistake.",
                hint=str(error),
                id="reports.E002",
            )
        ]
    return []
