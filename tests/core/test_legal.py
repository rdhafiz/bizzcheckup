"""Legal pages, the site footer, and the files for crawlers (robots, sitemap, llms.txt)."""

from datetime import date

import pytest
from django.test import Client
from django.urls import reverse

from bizzcheckup.core.views import LEGAL_PAGES
from bizzcheckup.engine.checks import agentic
from bizzcheckup.engine.context import PROBES
from bizzcheckup.engine.types import RobotsInfo, Severity
from bizzcheckup.reports.branding import load_branding

from ..engine.factories import fixture_html, make_context, make_page

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    ("name", "heading"),
    [
        ("privacy", "Your data, in plain words"),
        ("terms", "Terms of service"),
        ("cookies", "Cookie policy"),
        ("acceptable_use", "Acceptable use policy"),
        ("disclaimer", "Disclaimer"),
    ],
)
def test_every_legal_page_renders(client: Client, name: str, heading: str) -> None:
    response = client.get(reverse(f"core:{name}"))
    html = response.content.decode()

    assert response.status_code == 200
    assert heading in html
    assert "Run by Ridwanul Hafiz" in html  # operator from branding.yaml
    assert 'aria-current="page"' in html  # the side menu marks the open page
    for other, _ in LEGAL_PAGES:  # ...and links to every legal page
        assert reverse(f"core:{other}") in html


def test_terms_use_the_country_and_the_real_limits(client: Client, settings) -> None:  # type: ignore[no-untyped-def]
    settings.CHECKUP_RATE_LIMIT_PER_HOUR = 7
    settings.CHECKUP_MAX_PAGES = 12
    html = client.get(reverse("core:terms")).content.decode()
    assert "governed by the laws of Bangladesh" in html
    assert "up to 7 check-ups an hour" in html
    assert "up to 12 public pages" in html


def test_cookie_policy_lists_what_the_site_really_stores(client: Client) -> None:
    html = client.get(reverse("core:cookies")).content.decode()
    for name in ("csrftoken", "messages", "bizzcheckup-theme", "bizzcheckup-plan-"):
        assert name in html


def test_branding_has_legal_details() -> None:
    legal = load_branding().legal
    assert legal.operator == "Ridwanul Hafiz"
    assert legal.country == "Bangladesh"
    assert isinstance(legal.updated, date)


def test_footer_on_every_page(client: Client) -> None:
    for url in (reverse("core:home"), reverse("core:terms")):
        html = client.get(url).content.decode()
        assert 'class="site-footer on-dark"' in html
        assert f"© {date.today().year} Ridwanul Hafiz" in html
        assert "mailto:ridwanul.hafiz@gmail.com" in html
        assert 'aria-label="GitHub"' in html
        for name, _ in LEGAL_PAGES:
            assert f'href="{reverse(f"core:{name}")}"' in html


# --- robots.txt and sitemap.xml -----------------------------------------------------------


def test_robots_txt_keeps_crawlers_out_of_reports_and_points_to_the_sitemap(client: Client) -> None:
    response = client.get("/robots.txt")
    text = response.content.decode()

    assert response.status_code == 200
    assert response["Content-Type"] == "text/plain; charset=utf-8"
    assert "User-agent: *" in text
    for path in ("/checkups/", "/admin/", "/healthz/", "/styleguide/"):
        assert f"Disallow: {path}" in text
    assert "Sitemap: http://testserver/sitemap.xml" in text  # absolute, as crawlers need


def test_sitemap_lists_the_home_and_legal_pages(client: Client) -> None:
    response = client.get("/sitemap.xml")
    xml = response.content.decode()

    assert response.status_code == 200
    assert "<loc>http://testserver/</loc>" in xml
    for name, _ in LEGAL_PAGES:
        assert f"<loc>http://testserver{reverse(f'core:{name}')}</loc>" in xml
    updated = load_branding().legal.updated.isoformat()
    assert xml.count(f"<lastmod>{updated}</lastmod>") == len(LEGAL_PAGES)
    assert "/checkups/" not in xml  # reports are private, never listed


# --- llms.txt ------------------------------------------------------------------------------


def test_llms_txt_is_a_markdown_guide_for_ai_assistants(client: Client) -> None:
    response = client.get("/llms.txt")
    text = response.content.decode()

    assert response.status_code == 200
    assert response["Content-Type"] == "text/plain; charset=utf-8"
    lines = text.splitlines()
    assert lines[0] == "# BizzCheckup"  # llmstxt.org: the name as the first heading...
    assert lines[2].startswith("> BizzCheckup is a free website health check-up")  # ...a summary
    for name, _ in LEGAL_PAGES:  # ...and absolute links to the key pages
        assert f"(http://testserver{reverse(f'core:{name}')})" in text
    assert "(http://testserver/sitemap.xml)" in text
    assert "Google's own speed test" in text  # plain text, not HTML-escaped
    assert "&#x27;" not in text
    assert "please don't index" in text  # reports are private


def test_our_own_ai_checks_pass_on_our_site(client: Client) -> None:
    """BizzCheckup should pass the AI-readiness checks it gives other websites."""
    robots = RobotsInfo(
        url="https://shop.test/robots.txt",
        exists=True,
        text=client.get("/robots.txt").content.decode(),
    )
    ctx = make_context(make_page(fixture_html("healthy")), robots=robots, capabilities={PROBES})
    ctx.probes.llms_txt_text = client.get("/llms.txt").content.decode()
    for check in (agentic.LlmsTxt, agentic.AiCrawlers):
        assert {f.severity for f in check().run(ctx)} == {Severity.PASS}, check.id
