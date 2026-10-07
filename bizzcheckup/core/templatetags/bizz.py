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
