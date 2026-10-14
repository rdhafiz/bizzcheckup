"""The score badge a healthy website can show on its own pages (an SVG picture).

The badge is drawn from a template (templates/checkups/badge.svg). Its width follows
the product name from branding.yaml, so a longer name never spills into the score.
"""

from dataclasses import dataclass

from django.template.loader import render_to_string

from bizzcheckup.engine.types import Band
from bizzcheckup.reports.branding import load_branding

from .models import Checkup

HEIGHT = 44
SCORE_WIDTH = 100  # the coloured part on the right
NAME_X = 42  # where the product name starts (after the logo)
CHAR_WIDTH = 7.8  # about one bold 12 px letter in Verdana, the badge's font

# The score's band colours, like the report (the band's name is always written too).
COLOURS = {
    Band.HEALTHY: ("#31ac64", "#ffffff"),
    Band.ATTENTION: ("#f5b544", "#2b1d00"),
    Band.URGENT: ("#e5484d", "#ffffff"),
}


@dataclass(frozen=True)
class BadgeSize:
    width: int
    split: int  # where the dark part ends and the score begins
    score_x: int  # the centre of the score


def badge_size(product_name: str) -> BadgeSize:
    split = NAME_X + max(80, round(len(product_name) * CHAR_WIDTH)) + 12
    return BadgeSize(width=split + SCORE_WIDTH, split=split, score_x=split + SCORE_WIDTH // 2)


def latest_checkup(first: Checkup) -> Checkup:
    """The newest finished check-up of the same address: an old badge shows today's score."""
    newest = (
        Checkup.objects.filter(
            url=first.url, status=Checkup.Status.DONE, created_at__gte=first.created_at
        )
        .order_by("-created_at")
        .first()
    )
    return newest or first


def badge_svg(first: Checkup) -> str:
    checkup = latest_checkup(first)
    band = checkup.health_band or Band.ATTENTION
    colour, text_colour = COLOURS[band]
    name = load_branding().product_name
    return render_to_string(
        "checkups/badge.svg",
        {
            "score": checkup.health_score if checkup.health_score is not None else "?",
            "label": band.label,
            "colour": colour,
            "text_colour": text_colour,
            "product_name": name,
            "size": badge_size(name),
            "height": HEIGHT,
        },
    )
