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


def top_level_parts(selector: str) -> list[str]:
    """Split "a, b:is(c, d)" into ["a", "b:is(c, d)"]: commas inside brackets don't count."""
    parts, depth, current = [], 0, ""
    for char in selector:
        depth += {"(": 1, ")": -1}.get(char, 0)
        if char == "," and depth == 0:
            parts.append(current)
            current = ""
        else:
            current += char
    return [*parts, current]


def test_css_only_hides_content_once_the_script_has_armed_it() -> None:
    """Fail open: every [data-reveal] rule needs a flag a script set (.motion-ready/-boot)."""
    selectors = re.findall(r"([^{}]*\[data-reveal[^{}]*)\{", CSS)
    assert selectors  # the rules exist...
    for selector in selectors:
        for part in top_level_parts(selector):
            if "[data-reveal" in part:  # ...and every one of them is gated
                assert "html.motion-ready" in part or "html.motion-boot" in part, part.strip()


def test_boot_flags_have_a_css_fail_safe() -> None:
    """motion-boot.js hides content before motion.js loads; CSS must undo that on its own."""
    assert "html.motion-boot [data-reveal]:not(.is-revealed)" in CSS
    assert "@keyframes reveal-failsafe" in CSS


def test_script_never_writes_style_attributes() -> None:
    """Our Content Security Policy blocks style="" attributes; CSSOM writes are fine."""
    assert 'setAttribute("style"' not in JS
    assert "cssText" not in JS


def test_homepage_marks_every_section(client: Client) -> None:
    html = client.get(reverse("core:home")).content.decode()

    assert "js/motion-boot.js" in html  # blocking, in <head>: no flash before the entrance
    assert html.index("js/motion-boot.js") < html.index("</head>")
    assert "js/motion.js" in html
    assert "data-reveal-group" in html
    for section in ('class="hero-full"', 'class="signs"', 'class="how"', 'class="benefits"'):
        start = html.index(section)
        assert "data-reveal" in html[start : start + 4000], section
    hero = html[html.index('class="hero-full"') : html.index('class="signs"')]
    # Reveal on the hero's children, parallax on the wrapper: never both on one element.
    assert '<div class="hero__text on-dark" data-parallax="-0.1" data-reveal-group>' in hero
    assert 'data-parallax="0.22" data-parallax-fill' in hero


@pytest.mark.parametrize("name", ["home", "terms", "privacy"])
def test_no_template_syntax_leaks_onto_the_page(client: Client, name: str) -> None:
    """A {# comment #} spread over two lines is printed as text, and broke the hero once."""
    html = client.get(reverse(f"core:{name}")).content.decode()
    assert "{#" not in html
    assert "{%" not in html
