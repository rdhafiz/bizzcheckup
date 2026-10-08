"""Template filters used across BizzCheckup pages: {% load bizz %}."""

import re
from datetime import datetime, timedelta
from urllib.parse import urlsplit

from django import template
from django.utils import timezone
from django.utils.timesince import timesince

from bizzcheckup.engine.scoring import band_for

register = template.Library()


@register.filter
def band(score: int | None) -> str:
    """CSS band name for a score: {{ 72|band }} -> "attention" ("none" if not checked)."""
    result = band_for(score)
    return result.value if result else "none"


@register.filter
def band_label(score: int | None) -> str:
    """Plain-language label: {{ 72|band_label }} -> "Needs attention"."""
    result = band_for(score)
    return result.label if result else "Not checked"


SEVERITY_LABELS = {
    "fail": "Needs treatment",
    "warn": "Worth fixing",
    "info": "Good to know",
    "pass": "Healthy",
}
SEVERITY_BANDS = {"fail": "urgent", "warn": "attention", "info": "none", "pass": "healthy"}


@register.filter
def severity_label(severity: str) -> str:
    """{{ finding.severity|severity_label }} -> "Needs treatment" / "Worth fixing" / ..."""
    return SEVERITY_LABELS.get(str(severity), str(severity))


@register.filter
def severity_band(severity: str) -> str:
    """CSS band for a severity, so badges use the same colours as scores."""
    return SEVERITY_BANDS.get(str(severity), "none")


@register.filter
def first_items(items: list[str], count: int = 5) -> list[str]:
    """The first `count` items of a list (for long URL lists)."""
    return list(items)[:count]


HEX_COLOUR = r"#(?:[0-9a-fA-F]{3}){1,2}"
CONTRAST = re.compile(
    rf"contrast of (?P<ratio>[0-9.]+) \(foreground color: (?P<fg>{HEX_COLOUR}), "
    rf"background color: (?P<bg>{HEX_COLOUR}).*?Expected contrast ratio of (?P<expected>[0-9.]+:1)"
)


@register.filter
def contrast(note: str) -> dict[str, str] | None:
    """The colours and ratios in axe's colour-contrast explanation, to draw a sample.

    "...contrast of 4.11 (foreground color: #e3b24b, background color: #52504b, ...).
    Expected contrast ratio of 4.5:1" -> {"fg": "#e3b24b", "bg": "#52504b", ...}
    """
    match = CONTRAST.search(note or "")
    return match.groupdict() if match else None


@register.filter
def url_path(url: str) -> str:
    """The part after the domain: https://shop.com/about?x=1 -> /about?x=1"""
    parts = urlsplit(url)
    return parts.path + (f"?{parts.query}" if parts.query else "") or "/"


@register.filter
def remaining(items: list[str], count: int = 5) -> int:
    """How many items are left after the first `count`."""
    return max(0, len(items) - count)


@register.filter
def ago(moment: datetime | None) -> str:
    """{{ checkup.finished_at|ago }} -> "just now" or "2 hours, 18 minutes ago"."""
    if moment is None:
        return ""
    if timezone.now() - moment < timedelta(minutes=1):
        return "just now"
    return f"{timesince(moment)} ago"
