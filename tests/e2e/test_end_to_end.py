"""End to end: the landing form → Celery task → real engine (Chromium, axe, all checks)
→ saved report → report page → PDF, against a small website served by the test itself.

Celery runs tasks inline in tests (CELERY_TASK_ALWAYS_EAGER), so this goes through the
same task code the worker runs. Nothing reaches the internet.
"""

import re
import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import pytest
from django.test import Client
from django.urls import reverse

from bizzcheckup.checkups import services
from bizzcheckup.checkups.models import Checkup
from bizzcheckup.engine.netguard import NetGuard

from ..conftest import fake_dns
from ..fixtures_paths import FIXTURES

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.browser]

SITE: dict[str, tuple[str, str]] = {}  # path -> (content type, body); filled per test


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args: object) -> None:
        pass

    def do_GET(self) -> None:  # the method name is required by http.server
        found = SITE.get(self.path.split("?")[0])
        if found is None:
            self.send_response(404)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h1>Not found</h1>")
            return
        content_type, body = found
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.end_headers()
        self.wfile.write(body.encode())

    do_HEAD = do_GET  # noqa: N815 (http.server naming)


@pytest.fixture
def site(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_port
    base = f"http://127.0.0.1:{port}"
    html = "text/html; charset=utf-8"
    home = (FIXTURES / "healthy.html").read_text(encoding="utf-8")
    about = "<!doctype html><html lang=en><title>About Sweet Moments</title><h1>About</h1>"
    robots = f"User-agent: *\nAllow: /\nSitemap: {base}/sitemap.xml\n"
    sitemap = (
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
        f"<url><loc>{base}/</loc></url><url><loc>{base}/about</loc></url></urlset>"
    )
    SITE.clear()
    SITE.update(
        {
            "/": (html, home.replace("https://shop.test", base)),
            "/about": (html, about),
            "/robots.txt": ("text/plain", robots),
            "/sitemap.xml": ("application/xml", sitemap),
            "/llms.txt": ("text/plain", "# Sweet Moments\n> Handmade cakes in Dhaka\n"),
        }
    )
    threading.Thread(target=server.serve_forever, daemon=True).start()

    class LocalSiteGuard(NetGuard):
        """The real SSRF rules, except that our own test website is allowed."""

        async def check_url(self, url: str) -> None:
            parts = urlsplit(url)
            if parts.hostname == "127.0.0.1" and parts.port == port:
                return
            await super().check_url(url)

    monkeypatch.setattr(services, "make_guard", lambda: LocalSiteGuard(resolver=fake_dns))
    yield f"{base}/"
    server.shutdown()


def test_full_checkup_through_the_worker(client: Client, site: str) -> None:
    response = client.post(reverse("checkups:start"), {"url": site, "consent": "on"})

    checkup = Checkup.objects.get()
    if (
        checkup.status == Checkup.Status.FAILED
        and "Executable doesn't exist" in checkup.error_message
    ):
        pytest.skip("Chromium isn't installed")
    assert response.status_code == 302
    assert checkup.status == Checkup.Status.DONE, checkup.error_message

    # Every category except PageSpeed-only data was measured (no PSI key in tests).
    for field in ("score_accessibility", "score_best_practices", "score_seo", "score_agentic"):
        assert getattr(checkup, field) is not None, field
    assert checkup.health_score is not None
    assert checkup.findings.count() >= 30
    assert checkup.raw_results["pages"] == [site, f"{site}about"]
    assert checkup.screenshot is not None
    assert checkup.pdf is not None
    assert bytes(checkup.pdf).startswith(b"%PDF")

    # The same URL now shows the report.
    html = client.get(reverse("checkups:detail", args=[checkup.pk])).content.decode()
    assert "The diagnosis" in html
    assert "How Ridwanul can help" in " ".join(re.sub(r"<[^>]+>", " ", html).split())

    pdf = client.get(reverse("reports:pdf", args=[checkup.pk]))
    assert pdf["Content-Type"] == "application/pdf"
