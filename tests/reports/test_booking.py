"""The booking calendar (branding.yaml `booking_url`, e.g. Cal.com) in the report."""

from pathlib import Path

import pytest
from django.template.loader import render_to_string
from django.test import Client
from django.urls import reverse
from pytest_django.fixtures import Settings

from bizzcheckup.checkups import services
from bizzcheckup.checkups.models import Checkup
from bizzcheckup.core import security
from bizzcheckup.reports.branding import read_branding
from bizzcheckup.reports.builder import build_report
from tests.checkups.conftest import make_report

ROOT = Path(__file__).resolve().parents[2]
CAL = "https://cal.com/amy/30min"


@pytest.fixture
def booking(tmp_path: Path, settings: Settings) -> None:
    """branding.yaml with a booking page."""
    text = (ROOT / "branding.yaml").read_text(encoding="utf-8")
    branding = tmp_path / "branding.yaml"
    branding.write_text(text + f"\nbooking_url: {CAL}\n", encoding="utf-8")
    settings.BRANDING_FILE = branding


@pytest.fixture
def checkup(db: None) -> Checkup:
    checkup = Checkup.objects.create(url="https://shop.test/", domain="shop.test")
    services.save_report(checkup, make_report())
    services.mark_done(checkup)
    return checkup


def test_embed_url_asks_for_just_the_calendar(tmp_path: Path) -> None:
    text = (ROOT / "branding.yaml").read_text(encoding="utf-8")
    path = tmp_path / "branding.yaml"
    path.write_text(text + f"\nbooking_url: {CAL}?duration=30\n", encoding="utf-8")
    assert read_branding(path).booking_embed_url == (
        f"{CAL}?duration=30&embed=true&layout=month_view"
    )


def test_no_calendar_without_a_booking_page(client: Client, checkup: Checkup) -> None:
    response = client.get(reverse("checkups:detail", args=[checkup.pk]))
    assert 'id="book"' not in response.content.decode()
    assert "frame-src 'none'" in response["Content-Security-Policy"]


@pytest.mark.usefixtures("booking")
def test_report_shows_the_calendar_and_the_csp_allows_it(client: Client, checkup: Checkup) -> None:
    response = client.get(reverse("checkups:detail", args=[checkup.pk]))
    html = response.content.decode()

    assert 'id="book"' in html
    assert f'src="{CAL}?embed=true&amp;layout=month_view"' in html
    assert 'loading="lazy"' in html
    assert 'href="#book"' in html  # "Book a free review call" jumps to the calendar
    assert "frame-src https://cal.com" in response["Content-Security-Policy"]
    assert security.booking_origin() == "https://cal.com"


@pytest.mark.usefixtures("booking")
def test_pdf_links_to_the_booking_page_instead(checkup: Checkup) -> None:
    html = render_to_string("reports/report_pdf.html", {"view": build_report(checkup)})
    assert "<iframe" not in html
    assert f'href="{CAL}"' in html
