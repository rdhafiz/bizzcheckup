"""The share card: the score as a 1200 x 630 picture for social media."""

from urllib.parse import unquote

import pytest
from django.test import Client
from django.urls import reverse

from bizzcheckup.checkups import services
from bizzcheckup.checkups.models import Checkup, CheckupImage
from bizzcheckup.reports.builder import build_report
from bizzcheckup.reports.share_card import HEIGHT, WIDTH, render_share_card
from tests.checkups.conftest import make_report

pytestmark = pytest.mark.django_db

PNG_SIGNATURE = bytes([0x89]) + b"PNG"


@pytest.fixture
def checkup() -> Checkup:
    checkup = Checkup.objects.create(url="https://shop.test/", domain="shop.test")
    services.save_report(checkup, make_report())
    services.mark_done(checkup)
    return checkup


def png_size(png: bytes) -> tuple[int, int]:
    """Width and height from a PNG's header (bytes 16-24)."""
    return int.from_bytes(png[16:20], "big"), int.from_bytes(png[20:24], "big")


@pytest.mark.browser
def test_share_card_is_a_1200_by_630_picture(checkup: Checkup) -> None:
    png = render_share_card(checkup)  # real Chromium, offline
    assert png.startswith(PNG_SIGNATURE)
    assert png_size(png) == (WIDTH, HEIGHT)


def test_share_card_is_made_once_then_kept(
    client: Client, checkup: Checkup, monkeypatch: pytest.MonkeyPatch
) -> None:
    from bizzcheckup.reports import share_card

    made: list[str] = []

    def fake(c: Checkup) -> bytes:
        made.append(str(c.pk))
        return PNG_SIGNATURE + b"-fake"

    monkeypatch.setattr(share_card, "render_share_card", fake)
    url = reverse("checkups:share_card", args=[checkup.pk])
    first = client.get(url)
    client.get(url)

    assert first.status_code == 200
    assert first["Content-Type"] == "image/png"
    assert len(made) == 1
    assert CheckupImage.objects.filter(checkup=checkup, kind="share_card").exists()
    download = client.get(url + "?download=1")
    assert (
        download["Content-Disposition"] == 'attachment; filename="bizzcheckup-shop.test-score.png"'
    )


def test_share_links_point_to_our_homepage_not_the_report(checkup: Checkup, settings) -> None:  # type: ignore[no-untyped-def]
    settings.SITE_URL = "https://check.example"
    view = build_report(checkup)
    links = dict(view.share_links)

    assert set(links) == {"WhatsApp", "LinkedIn", "Facebook", "X"}
    for link in links.values():
        assert "https://check.example/" in unquote(link)
        assert str(checkup.pk) not in link  # the report stays private
    assert "shop.test scored 66/100" in unquote(links["WhatsApp"])


def test_report_has_the_share_button(client: Client, checkup: Checkup) -> None:
    html = client.get(reverse("checkups:detail", args=[checkup.pk])).content.decode()
    assert "Share your score" in html
    assert reverse("checkups:share_card", args=[checkup.pk]) + "?download=1" in html
