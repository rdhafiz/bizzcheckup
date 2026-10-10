"""Branding, the report builder, the report page and the PDF."""

import re
from pathlib import Path
from unittest.mock import patch

import httpx
import pytest
import respx
from asgiref.sync import async_to_sync
from django.core import checks
from django.test import Client
from django.urls import reverse
from pydantic import ValidationError

from bizzcheckup.checkups import services
from bizzcheckup.checkups.models import Checkup
from bizzcheckup.engine.types import (
    AuditReport,
    Category,
    Level,
    LinkPreview,
    ReportImage,
    Severity,
    Shot,
)
from bizzcheckup.reports import pdf as pdf_module
from bizzcheckup.reports.apps import check_branding_file
from bizzcheckup.reports.branding import load_branding, read_branding
from bizzcheckup.reports.builder import build_report, qr_code_svg, recommend_services, top_risks

from ..checkups.conftest import make_report

ROOT = Path(__file__).resolve().parents[2]


def visible_text(html: str) -> str:
    """The page as a reader sees it: tags removed, spaces collapsed."""
    return " ".join(re.sub(r"<[^>]+>", " ", html).split())


@pytest.fixture
def finished(db: None) -> Checkup:
    checkup = Checkup.objects.create(url="https://shop.test/", domain="shop.test")
    services.save_report(checkup, make_report())
    services.mark_done(checkup)
    return checkup


# --- branding.yaml -------------------------------------------------------------


def test_project_branding_file_is_valid() -> None:
    branding = read_branding(ROOT / "branding.yaml")
    assert branding.product_name == "BizzCheckup"
    assert branding.first_name == "Ridwanul"
    assert branding.call_to_action.button_label
    assert {c for s in branding.services for c in s.related_categories} == set(Category)


def test_branding_rejects_unknown_category(tmp_path: Path) -> None:
    bad = tmp_path / "branding.yaml"
    text = (ROOT / "branding.yaml").read_text(encoding="utf-8")
    bad.write_text(text.replace("[performance]", "[speed]"), encoding="utf-8")
    with pytest.raises(ValidationError):
        read_branding(bad)


def test_system_check_reports_broken_branding(tmp_path: Path, settings) -> None:  # type: ignore[no-untyped-def]
    bad = tmp_path / "branding.yaml"
    bad.write_text("name: [unclosed", encoding="utf-8")
    settings.BRANDING_FILE = bad
    errors = check_branding_file()
    assert [e.id for e in errors] == ["reports.E002"]
    assert all(isinstance(e, checks.Error) for e in errors)

    settings.BRANDING_FILE = tmp_path / "missing.yaml"
    assert [e.id for e in check_branding_file()] == ["reports.E001"]


def test_services_for_prefers_the_most_specific_service() -> None:
    branding = load_branding()
    assert branding.services_for(Category.SEO)[0].name == "Technical SEO & Structured Data"


# --- builder -----------------------------------------------------------------------


def test_build_report(finished: Checkup) -> None:
    view = build_report(finished)

    assert [s.category for s in view.vital_signs] == list(Category)
    seo = view.vital_signs[3]
    assert [f.check_id for f in seo.problems] == ["seo.title"]
    assert [f.check_id for f in seo.healthy] == ["seo.sitemap"]
    assert "<svg" in view.qr_svg


def test_overview_numbers_and_verdict(finished: Checkup) -> None:
    view = build_report(finished)
    assert (view.needs_treatment, view.worth_fixing) == (1, 0)
    assert view.healthy_count == sum(len(s.healthy) for s in view.vital_signs)
    assert view.verdict == (
        "Your website works, but 1 serious problem is holding your business back."
    )
    assert [s.category for s in view.problem_categories] == [Category.SEO]

    performance, seo = view.vital_signs[0], view.vital_signs[3]
    assert seo.anchor == "sign-seo"
    assert seo.headline == "1 issue found; 1 needs treatment."
    assert performance.headline == "Not checked this time."


def test_recommendations_map_each_failing_area_to_a_service(finished: Checkup) -> None:
    view = build_report(finished)
    # 72 accessibility, 48 SEO, 60 agentic need care; 95 best practices doesn't;
    # performance wasn't checked.
    assert [(r.category, r.service.name) for r in view.recommendations] == [
        (Category.ACCESSIBILITY, "Accessibility Fixes (WCAG)"),
        (Category.SEO, "Technical SEO & Structured Data"),
        (Category.AGENTIC, "AI-Ready Website (Agentic Browsing)"),
    ]
    # Three or more areas need care -> the broad rebuild service is suggested too.
    assert [s.name for s in view.extra_services] == ["Custom Web App & Website Rebuild"]


def test_no_recommendations_for_a_healthy_site(finished: Checkup) -> None:
    view = build_report(finished)
    for sign in view.vital_signs:
        sign.score.score = 95
    recommendations, extra = recommend_services(view.branding, view.vital_signs)
    assert recommendations == []
    assert extra == []


def test_top_risks_order() -> None:
    report = make_report()
    base = report.findings[0]
    low = base.model_copy(update={"impact": Level.LOW, "message": "low"})
    warn = base.model_copy(update={"severity": Severity.WARN, "message": "warn"})
    passed = base.model_copy(update={"severity": Severity.PASS, "message": "pass"})
    risks = top_risks([low, passed, warn, base])
    assert [r.message for r in risks] == [base.message, "warn", "low"]


def test_qr_code_scales_to_its_box() -> None:
    svg = qr_code_svg("https://example.com")
    assert 'viewBox="' in svg  # CSS sizes it; no fixed width/height that would crop it
    assert "width=" not in svg.split(">", 1)[0]


def test_qr_code_is_inline_svg() -> None:
    svg = qr_code_svg("https://ridwanulhafiz.me")
    assert svg.startswith("<svg")
    assert "<script" not in svg


# --- report page -----------------------------------------------------------------------


def test_report_page_has_all_sections(client: Client, finished: Checkup) -> None:
    html = client.get(reverse("checkups:detail", args=[finished.pk])).content.decode()

    for heading in [
        "BizzCheckup Health Report",  # 1 overview
        "The diagnosis",
        "Fix these first",  # 2 the top risks
        "All issues",  # 3 one list of every issue
        "We found 1 page on your website",  # 4 pages
        "How Ridwanul can help",  # 5 proposal
        "Let&#x27;s fix this together",
        "ridwanul.hafiz@gmail.com",  # 6 contact
        "Generated by BizzCheckup — Check your business&#x27;s online health",
    ]:
        assert heading in visible_text(html), heading

    assert "Download PDF" in html
    assert 'data-copy-link="http://testserver/checkups/' in html
    assert "This vital sign wasn't checked." in html  # performance has no score
    assert "<svg" in html  # QR code


def test_report_page_helps_find_issues_and_solutions(client: Client, finished: Checkup) -> None:
    html = client.get(reverse("checkups:detail", args=[finished.pk])).content.decode()
    for anchor in ["#overview", "#fix-first", "#issues", "#pages", "#help"]:
        assert f'href="{anchor}"' in html, anchor
    # The sidebar: a vital sign filters the issue list.
    assert 'class="side-sign band-urgent" href="#issues" data-filter-category="seo"' in html
    # Each issue appears once, in the list: details on demand, a stable anchor.
    assert html.count('<span class="issue__message">Your homepage has no title.') == 1
    assert 'id="issue-seo-title-1"' in html
    assert 'href="#issue-seo-title-1"' in html  # "See how to fix it" from the top risks
    assert "data-plan" not in html  # no tick boxes or progress bar
    assert '<details class="issue"' in html


def test_report_shows_suggested_fixes_with_a_copy_button(client: Client, finished: Checkup) -> None:
    html = client.get(reverse("checkups:detail", args=[finished.pk])).content.decode()
    assert "Homepage: a title" in html
    assert "&lt;title&gt;Shop | Fresh cakes&lt;/title&gt;" in html  # shown as code, escaped
    assert "data-copy-code" in html


def test_report_shows_how_the_homepage_looks_when_shared(client: Client, db: None) -> None:
    report = make_report().model_copy(
        update={
            "link_preview": LinkPreview(
                url="https://shop.test/",
                domain="shop.test",
                title="Fresh cakes",
                description="Baked daily.",
            ),
            "images": {"link_preview": ReportImage(content_type="image/png", data=b"png")},
        }
    )
    checkup = Checkup.objects.create(url="https://shop.test/", domain="shop.test")
    services.save_report(checkup, report)
    services.mark_done(checkup)
    html = client.get(reverse("checkups:detail", args=[checkup.pk])).content.decode()
    assert "When someone shares your link" in html
    assert reverse("checkups:image", args=[checkup.pk, "link_preview"]) in html
    assert "Fresh cakes" in html
    assert "SHOP.TEST" in html


def test_report_lists_every_page_found_and_offers_a_full_checkup(client: Client, db: None) -> None:
    found = ["https://shop.test/", *(f"https://shop.test/p{n}" for n in range(40))]
    checkup = Checkup.objects.create(url="https://shop.test/", domain="shop.test")
    services.save_report(checkup, make_report().model_copy(update={"discovered_pages": found}))
    services.mark_done(checkup)
    html = client.get(reverse("checkups:detail", args=[checkup.pk])).content.decode()
    assert "We found 41 pages on your website" in visible_text(html)
    assert "The other 40 weren't checked this time" in html
    assert ">/p39<" in html  # behind "Show all 41 pages", shown without the domain
    assert "All 41 pages, not just 1." in html
    assert load_branding().full_audit_url in html.replace("&amp;", "&")


def test_no_proposal_when_every_page_was_checked(client: Client, finished: Checkup) -> None:
    html = client.get(reverse("checkups:detail", args=[finished.pk])).content.decode()
    assert "We found 1 page on your website" in visible_text(html)
    assert "This check-up looked at every one of them." in html
    assert 'id="proposal-title"' not in html


def test_report_shows_the_homepage_on_each_device(client: Client, db: None) -> None:
    jpeg = ReportImage(content_type="image/jpeg", data=b"jpeg")
    report = make_report().model_copy(update={"images": {"mobile": jpeg, "tablet": jpeg}})
    checkup = Checkup.objects.create(url="https://shop.test/", domain="shop.test")
    services.save_report(checkup, report)
    services.mark_done(checkup)
    html = client.get(reverse("checkups:detail", args=[checkup.pk])).content.decode()
    assert "device-stage--trio" in html
    for kind in ["mobile", "tablet"]:
        assert reverse("checkups:image", args=[checkup.pk, kind]) in html
    assert "Phone · 390 px" in html
    assert "computer, tablet, phone" in html  # "What we checked" counts the screens


def test_only_the_computer_without_phone_and_tablet_pictures(
    client: Client, finished: Checkup
) -> None:
    html = client.get(reverse("checkups:detail", args=[finished.pk])).content.decode()
    assert "device-stage--trio" not in html
    assert "Phone · 390 px" not in html
    assert 'role="tablist"' not in html  # the old tabs are gone for good


def test_what_we_checked_shows_how_much_of_the_site_was_checked(
    client: Client, finished: Checkup
) -> None:
    html = client.get(reverse("checkups:detail", args=[finished.pk])).content.decode()
    assert "100% of your website checked" in visible_text(html)


def test_hero_shows_the_sites_own_preview_image(client: Client, db: None) -> None:
    report = make_report().model_copy(
        update={"images": {"link_preview": ReportImage(content_type="image/png", data=b"png")}}
    )
    checkup = Checkup.objects.create(url="https://shop.test/", domain="shop.test")
    services.save_report(checkup, report)
    services.mark_done(checkup)
    html = client.get(reverse("checkups:detail", args=[checkup.pk])).content.decode()
    hero = html[html.index('<section id="overview"') :]
    assert f'src="{reverse("checkups:image", args=[checkup.pk, "link_preview"])}"' in hero[:1500]


def test_hero_falls_back_to_the_demo_picture(client: Client, finished: Checkup) -> None:
    html = client.get(reverse("checkups:detail", args=[finished.pk])).content.decode()
    hero = html[html.index('<section id="overview"') :]
    assert "img/report-hero-demo.svg" in hero[:1500]


def test_help_cards_link_to_the_issues_they_treat(client: Client, finished: Checkup) -> None:
    html = client.get(reverse("checkups:detail", args=[finished.pk])).content.decode()
    # seo scores 48 with 1 issue: its service card wears the homepage's SEO colour and icon
    assert '<article class="sign-card help-card tone-violet">' in html
    assert 'class="help-card__link" href="#issues" data-filter-category="seo"' in html
    assert "Treats the 1 seo issue in this report" in visible_text(html)


def test_report_shows_where_each_problem_is(client: Client, db: None) -> None:
    report = make_report()
    finding = report.results[0].findings[0]
    pictured = Shot(
        page="https://shop.test/", selector="h1", label='<h1> "Welcome"', image="shot-1"
    )
    lost = Shot(page="https://shop.test/", selector="h2", label="not saved", image="shot-2")
    unshot = Shot(page="https://shop.test/", selector="h3", label="never taken")
    result = report.results[0].model_copy(
        update={"findings": [finding.model_copy(update={"shots": [pictured, lost, unshot]})]}
    )
    report = report.model_copy(
        update={
            "results": [result],
            "images": {"shot-1": ReportImage(content_type="image/jpeg", data=b"jpeg")},
        }
    )
    checkup = Checkup.objects.create(url="https://shop.test/", domain="shop.test")
    services.save_report(checkup, report)
    services.mark_done(checkup)
    html = client.get(reverse("checkups:detail", args=[checkup.pk])).content.decode()
    picture = reverse("checkups:image", args=[checkup.pk, "shot-1"])
    assert "Where it is on the page" in html
    assert html.count(f'src="{picture}"') == 2  # in the issue, and on its "Fix these first" card
    assert "&lt;h1&gt; &quot;Welcome&quot;" in html
    assert "not saved" not in html  # no picture, not shown
    assert "never taken" not in html


def test_report_contact_links_come_from_branding(client: Client, finished: Checkup) -> None:
    html = client.get(reverse("checkups:detail", args=[finished.pk])).content.decode()
    branding = load_branding()
    for url in [branding.whatsapp_url, branding.github, branding.cv_url, branding.website]:
        assert str(url) in html


# --- PDF -------------------------------------------------------------------------------------


def test_pdf_download(client: Client, finished: Checkup) -> None:
    with patch.object(pdf_module, "render_pdf", return_value=b"%PDF-1.7 fake") as render:
        response = client.get(reverse("reports:pdf", args=[finished.pk]))
        again = client.get(reverse("reports:pdf", args=[finished.pk]))

    assert response.status_code == 200
    assert response["Content-Type"] == "application/pdf"
    assert response["Content-Disposition"].startswith(
        'attachment; filename="bizzcheckup-shop.test-'
    )
    assert again.content == b"%PDF-1.7 fake"
    render.assert_called_once()  # the second download used the stored PDF


def test_pdf_failure_shows_friendly_page(client: Client, finished: Checkup) -> None:
    with patch.object(pdf_module, "render_pdf", side_effect=RuntimeError("no chromium")):
        response = client.get(reverse("reports:pdf", args=[finished.pk]))
    assert response.status_code == 503
    assert "The PDF isn't available right now" in response.content.decode()


@pytest.mark.django_db
def test_pdf_only_for_finished_checkups(client: Client) -> None:
    running = Checkup.objects.create(url="https://a.test/", domain="a.test", status="running")
    assert client.get(reverse("reports:pdf", args=[running.pk])).status_code == 404


def test_static_file_resolution() -> None:
    found = pdf_module.static_file("/static/img/favicon.svg")
    assert found is not None
    assert found[1] == "image/svg+xml"
    assert pdf_module.static_file("/static/does-not-exist.css") is None
    assert pdf_module.static_file("/etc/passwd") is None  # only files under /static/


@pytest.mark.browser
def test_real_pdf_is_rendered(finished: Checkup) -> None:
    try:
        content = pdf_module.render_pdf(finished)
    except Exception as error:
        if "Executable doesn't exist" in str(error):
            pytest.skip("Chromium isn't installed: python -m playwright install chromium")
        raise
    assert content.startswith(b"%PDF")
    assert len(content) > 10_000


def test_report_json_round_trip(finished: Checkup) -> None:
    """What's stored in raw_results reads back into the same engine report."""
    report = AuditReport.model_validate(finished.raw_results)
    assert report.health_score == 66


# --- the branding photo in PDFs ------------------------------------------------------------


PHOTO = "https://photos.test/me.png"


def test_pdf_photo_is_fetched() -> None:
    with respx.mock() as router:
        router.get(PHOTO).respond(200, content=b"png-bytes", headers={"content-type": "image/png"})
        assert async_to_sync(pdf_module.fetch_photo)(PHOTO) == (b"png-bytes", "image/png")


def test_slow_or_broken_photo_never_holds_up_the_pdf() -> None:
    with respx.mock() as router:
        router.get(PHOTO).mock(side_effect=httpx.ReadTimeout("too slow"))
        assert async_to_sync(pdf_module.fetch_photo)(PHOTO) is None
    with respx.mock() as router:
        router.get(PHOTO).respond(404)
        assert async_to_sync(pdf_module.fetch_photo)(PHOTO) is None
