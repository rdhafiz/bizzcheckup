"""Scroll reveal and parallax: the rules that keep the page readable if the script fails.

The animation itself runs in the browser (static/js/motion.js) and was checked there; these
tests guard what Python can see: the markup and the CSS source.
"""

import re
from pathlib import Path

import pytest
from django.test import Client
from django.urls import reverse

ROOT = Path(__file__).resolve().parents[2]
CSS = (ROOT / "frontend" / "tailwind.css").read_text(encoding="utf-8")
JS = (ROOT / "static" / "js" / "motion.js").read_text(encoding="utf-8")

pytestmark = pytest.mark.django_db


def test_css_only_hides_content_once_the_script_has_armed_it() -> None:
    """Fail open: no rule may hide [data-reveal] unless motion.js set .motion-ready."""
    selectors = re.findall(r"([^{}]*\[data-reveal[^{}]*)\{", CSS)
    assert selectors  # the rules exist...
    for selector in selectors:
        for part in selector.split(","):
            if "[data-reveal" in part:  # ...and every one of them is gated
                assert "html.motion-ready" in part, part.strip()


def test_script_never_writes_style_attributes() -> None:
    """Our Content Security Policy blocks style="" attributes; CSSOM writes are fine."""
    assert 'setAttribute("style"' not in JS
    assert "cssText" not in JS


def test_homepage_marks_sections_but_not_the_hero(client: Client) -> None:
    html = client.get(reverse("core:home")).content.decode()

    assert "js/motion.js" in html
    assert html.count("data-reveal") >= 15  # the sections below the hero, and the footer
    assert "data-reveal-group" in html
    hero = html[html.index('class="hero-full"') : html.index('class="signs"')]
    # The first screen is never faded in: it would delay the page looking loaded.
    assert "data-reveal" not in hero
    assert 'data-parallax="0.12" data-parallax-fill' in hero  # the photo drifts instead


@pytest.mark.parametrize("name", ["home", "terms", "privacy"])
def test_no_template_syntax_leaks_onto_the_page(client: Client, name: str) -> None:
    """A {# comment #} spread over two lines is printed as text, and broke the hero once."""
    html = client.get(reverse(f"core:{name}")).content.decode()
    assert "{#" not in html
    assert "{%" not in html
