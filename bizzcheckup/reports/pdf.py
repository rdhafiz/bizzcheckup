"""Turn the report into a PDF with headless Chromium (Playwright).

The PDF uses the same report sections as the web page. Chromium gets NO network
access: every request is answered from our own files (CSS, fonts), the
check-up's screenshot from the database, or the branding photo. Everything
else is refused.
"""

import contextlib
import mimetypes
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlsplit

from asgiref.sync import async_to_sync
from django.conf import settings
from django.contrib.staticfiles import finders
from django.contrib.staticfiles.storage import staticfiles_storage
from django.template.loader import render_to_string
from django.urls import reverse
from playwright.async_api import Route, async_playwright

from bizzcheckup.checkups.models import Checkup

from .builder import build_report

ORIGIN = "http://report.local"  # a made-up address; nothing ever leaves the browser
Resolver = Callable[[str], tuple[bytes, str] | None]  # path -> (body, content type)

FOOTER_TEMPLATE = """
<div style="width:100%; font-family: sans-serif; font-size:8px; color:#4a5a5e;
            padding:0 14mm; display:flex; justify-content:space-between;">
  <span>{note}</span>
  <span><span class="pageNumber"></span> / <span class="totalPages"></span></span>
</div>
"""


def static_file(path: str) -> tuple[bytes, str] | None:
    """Find a static file by its URL path, in development and after collectstatic."""
    prefix = "/" + str(settings.STATIC_URL).lstrip("/")  # "static/" -> "/static/"
    if not path.startswith(prefix):
        return None
    name = path.removeprefix(prefix)
    candidates: list[Path] = []
    # After collectstatic (production): the collected, possibly hashed file name.
    with contextlib.suppress(NotImplementedError):
        candidates.append(Path(staticfiles_storage.path(name)))
    # During development: the original file in static/.
    found = finders.find(name)
    if isinstance(found, str):
        candidates.append(Path(found))
    for candidate in candidates:
        if candidate.is_file():
            content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
            return candidate.read_bytes(), content_type
    return None


async def html_to_pdf(
    html: str, resolve: Resolver, *, allowed_urls: set[str], footer_note: str
) -> bytes:
    async def handle(route: Route) -> None:
        url = route.request.url
        if url == f"{ORIGIN}/":
            await route.fulfill(body=html, content_type="text/html; charset=utf-8")
            return
        if url in allowed_urls:  # e.g. the consultant's photo from branding.yaml
            await route.continue_()
            return
        if url.startswith(ORIGIN):
            found = resolve(urlsplit(url).path)
            if found is not None:
                await route.fulfill(body=found[0], content_type=found[1])
                return
        await route.abort("blockedbyclient")

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(args=["--disable-dev-shm-usage"])
        try:
            page = await browser.new_page()
            await page.emulate_media(media="print", color_scheme="light")
            await page.route("**/*", handle)
            await page.goto(f"{ORIGIN}/", wait_until="networkidle", timeout=30_000)
            pdf: bytes = await page.pdf(
                format="A4",
                print_background=True,
                margin={"top": "14mm", "bottom": "16mm", "left": "14mm", "right": "14mm"},
                display_header_footer=True,
                header_template="<div></div>",
                footer_template=FOOTER_TEMPLATE.format(note=footer_note),
            )
        finally:
            await browser.close()
    return pdf


def render_pdf(checkup: Checkup) -> bytes:
    """Build the PDF for a finished check-up (runs Chromium, takes a second or two)."""
    view = build_report(checkup)
    html = render_to_string(
        "reports/report_pdf.html", {"view": view, "product_name": "BizzCheckup"}
    )
    screenshot_path = reverse("checkups:screenshot", args=[checkup.pk])

    def resolve(path: str) -> tuple[bytes, str] | None:
        if path == screenshot_path and checkup.screenshot:
            return bytes(checkup.screenshot), "image/jpeg"
        return static_file(path)

    allowed = {str(view.branding.photo_url)} if view.branding.photo_url else set()
    return async_to_sync(html_to_pdf)(
        html, resolve, allowed_urls=allowed, footer_note=view.branding.footer_note
    )


def ensure_pdf(checkup: Checkup) -> bytes:
    """The stored PDF, created (and saved) first if it doesn't exist yet."""
    if checkup.pdf:
        return bytes(checkup.pdf)
    pdf = render_pdf(checkup)
    Checkup.objects.filter(pk=checkup.pk).update(pdf=pdf)
    checkup.pdf = pdf
    return pdf
