"""Template filters used across BizzCheckup pages: {% load bizz %}."""

from django import template

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


@register.filter
def remaining(items: list[str], count: int = 5) -> int:
    """How many items are left after the first `count`."""
    return max(0, len(items) - count)
