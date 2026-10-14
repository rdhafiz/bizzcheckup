"""The share card: a 1200 x 630 picture of a website's score, for social media.

Made like the PDF: headless Chromium opens templates/reports/share_card.html with no
network at all (only our fonts and the homepage screenshot), takes a photo of it, and the
PNG is saved as one of the check-up's pictures (kind "share_card"), so it's made once.
"""

from urllib.parse import urlsplit

from asgiref.sync import async_to_sync
from django.conf import settings
from django.template.loader import render_to_string
from django.urls import reverse
from playwright.async_api import async_playwright

from bizzcheckup.checkups.models import Checkup, CheckupImage

from .builder import build_report
from .pdf import ORIGIN, Resolver, offline_router, static_file

WIDTH, HEIGHT = 1200, 630  # the size Facebook, LinkedIn and WhatsApp show
BAND_COLOURS = {"healthy": "#31ac64", "attention": "#f5b544", "urgent": "#e5484d"}


async def html_to_png(html: str, resolve: Resolver) -> bytes:
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(args=["--disable-dev-shm-usage"])
        try:
            page = await browser.new_page(viewport={"width": WIDTH, "height": HEIGHT})
            await page.route("**/*", offline_router(html, resolve, set()))
            await page.goto(f"{ORIGIN}/", wait_until="networkidle", timeout=30_000)
            png: bytes = await page.screenshot(type="png")
        finally:
            await browser.close()
    return png


def render_share_card(checkup: Checkup) -> bytes:
    view = build_report(checkup)
    score = view.report.health_score
    band = view.report.health_band.value if view.report.health_band else "attention"
    html = render_to_string(
        "reports/share_card.html",
        {
            "checkup": checkup,
            "report": view.report,
            "signs": view.vital_signs,
            "colour": BAND_COLOURS.get(band, BAND_COLOURS["attention"]),
            "site_host": urlsplit(str(settings.SITE_URL)).netloc,
            "score": score,
        },
    )
    screenshot_path = reverse("checkups:screenshot", args=[checkup.pk])

    def resolve(path: str) -> tuple[bytes, str] | None:
        if path == screenshot_path and checkup.screenshot:
            return bytes(checkup.screenshot), "image/jpeg"
        return static_file(path)

    return async_to_sync(html_to_png)(html, resolve)


def ensure_share_card(checkup: Checkup) -> bytes:
    """The saved share card, made (and saved) first if it doesn't exist yet."""
    kind = CheckupImage.Kind.SHARE_CARD
    saved = CheckupImage.objects.filter(checkup=checkup, kind=kind).first()
    if saved is not None:
        return bytes(saved.data)
    png = render_share_card(checkup)
    CheckupImage.objects.get_or_create(
        checkup=checkup, kind=kind, defaults={"content_type": "image/png", "data": png}
    )
    return png
