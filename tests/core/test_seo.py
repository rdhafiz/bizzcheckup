"""SEO of BizzCheckup's own pages: meta tags, link previews, structured data, crawl files."""

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

import pytest
from django.conf import settings
from django.test import Client
from django.urls import reverse
from pytest_django.fixtures import Settings

from bizzcheckup.checkups import services
from bizzcheckup.checkups.models import Checkup
from bizzcheckup.core.seo import PageMeta
from bizzcheckup.core.views import LEGAL_PAGES
from bizzcheckup.reports.branding import load_branding
from tests.checkups.conftest import make_report

SITE = "https://check.example"


@pytest.fixture(autouse=True)
def public_address(settings: Settings) -> None:
    settings.SITE_URL = SITE


def tag(html: str, attribute: str, name: str) -> str:
    """The content of <meta property="og:title" content="..."> (or name=...)."""
    match = re.search(rf'<meta {attribute}="{re.escape(name)}" content="([^"]*)"', html)
    assert match, f"no {name} tag"
    return match.group(1)


def json_ld(html: str) -> list[dict[str, Any]]:
    match = re.search(r'<script type="application/ld\+json">(.*?)</script>', html, re.S)
    assert match, "no JSON-LD"
    graph: list[dict[str, Any]] = json.loads(match.group(1))["@graph"]
    return graph


# --- The homepage ---------------------------------------------------------------------


@pytest.mark.django_db
def test_home_has_every_tag_on_the_public_address(client: Client) -> None:
    html = client.get("/").content.decode()

    assert f'<link rel="canonical" href="{SITE}/">' in html
    assert tag(html, "name", "robots").startswith("index, follow")
    title = tag(html, "property", "og:title")
    assert title == "BizzCheckup: free website health check-up for business owners"
    assert tag(html, "name", "twitter:card") == "summary_large_image"
    assert tag(html, "property", "og:image") == f"{SITE}/static/img/og-image.png"
    assert tag(html, "property", "og:image:width") == "1200"
    description = tag(html, "name", "description")
    assert 120 <= len(description) <= 170  # the length search engines show in full


@pytest.mark.django_db
def test_home_structured_data_matches_the_visible_faq(client: Client) -> None:
    html = client.get("/").content.decode()
    graph = json_ld(html)

    types = [item["@type"] for item in graph]
    assert types == ["Person", "WebSite", "WebApplication", "WebPage", "FAQPage"]
    faq = graph[-1]["mainEntity"]
    assert len(faq) == 5
    for question in faq:  # what search engines read is exactly what visitors see
        assert question["name"].replace("'", "&#x27;") in html
    app = graph[2]
    assert app["offers"]["price"] == "0"


def test_json_ld_can_never_close_its_script_tag() -> None:
    meta = PageMeta(title="x", schema=[{"name": "</script><script>alert(1)</script>"}])
    assert "</script><script>" not in str(meta.json_ld)
    assert "\\u003c/script\\u003e" in str(meta.json_ld)


# --- Legal pages ----------------------------------------------------------------------


@pytest.mark.django_db
@pytest.mark.parametrize("name", [name for name, _ in LEGAL_PAGES])
def test_each_legal_page_has_its_own_title_description_and_date(client: Client, name: str) -> None:
    html = client.get(reverse(f"core:{name}")).content.decode()
    path = reverse(f"core:{name}")

    assert f'<link rel="canonical" href="{SITE}{path}">' in html
    assert tag(html, "property", "og:type") == "article"
    updated = load_branding().legal.updated.isoformat()  # "Last updated" in branding.yaml
    assert tag(html, "property", "article:modified_time") == updated
    types = [item["@type"] for item in json_ld(html)]
    assert types == ["WebPage", "BreadcrumbList"]
    assert "| BizzCheckup</title>" in html


# --- Private pages --------------------------------------------------------------------


@pytest.mark.django_db
def test_reports_are_never_indexed_but_preview_nicely(client: Client) -> None:
    checkup = Checkup.objects.create(url="https://shop.test/", domain="shop.test")
    services.save_report(checkup, make_report())
    services.mark_done(checkup)

    response = client.get(reverse("checkups:detail", args=[checkup.pk]))
    html = response.content.decode()

    assert tag(html, "name", "robots") == "noindex, nofollow"
    assert response["X-Robots-Tag"] == "noindex, nofollow"  # PDFs and pictures too
    assert tag(html, "property", "og:title") == "shop.test: health score 66/100 | BizzCheckup"
    share = reverse("checkups:share_card", args=[checkup.pk])
    assert tag(html, "property", "og:image") == f"{SITE}{share}"


@pytest.mark.django_db
def test_public_pages_have_no_robots_header(client: Client) -> None:
    assert "X-Robots-Tag" not in client.get("/")


# --- Files for crawlers ---------------------------------------------------------------


def test_security_txt_has_a_contact_and_a_future_expiry(client: Client) -> None:
    text = client.get("/.well-known/security.txt").content.decode()

    assert re.search(r"^Contact: mailto:\S+@\S+$", text, re.M)
    expires = re.search(r"^Expires: (\d{4})-", text, re.M)
    assert expires
    assert int(expires.group(1)) > date.today().year - 1
    assert f"Canonical: {SITE}/.well-known/security.txt" in text


@pytest.mark.django_db
def test_robots_txt_and_sitemap_use_the_public_address(client: Client) -> None:
    assert f"Sitemap: {SITE}/sitemap.xml" in client.get("/robots.txt").content.decode()
    assert f"<loc>{SITE}/</loc>" in client.get("/sitemap.xml").content.decode()


def test_share_picture_and_icon_exist_at_the_right_size() -> None:
    folder = Path(settings.BASE_DIR) / "static" / "img"
    for name, size in [("og-image.png", (1200, 630)), ("apple-touch-icon.png", (180, 180))]:
        png = (folder / name).read_bytes()
        width = int.from_bytes(png[16:20], "big")
        height = int.from_bytes(png[20:24], "big")
        assert (width, height) == size, name
