"""The browser collector, tested against a tiny local web server (no internet).

These tests start real headless Chromium, so they take a few seconds. They are
skipped automatically if Chromium isn't installed (python -m playwright install chromium).
"""

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

import pytest

from bizzcheckup.engine.collectors.render import collect_render
from bizzcheckup.engine.config import EngineConfig
from bizzcheckup.engine.context import RENDER
from bizzcheckup.engine.fetcher import Fetcher
from bizzcheckup.engine.netguard import NetGuard

from .conftest import fake_resolver
from .factories import make_context, make_page

pytestmark = pytest.mark.browser

PAGE = """<!doctype html>
<html><head><title>Test shop</title></head>
<body>
  <h1>Test shop</h1>
  <img src="/photo.gif">
  <img src="http://localhost:{port}/pixel.gif" alt="">
  <img src="http://169.254.169.254/latest/meta-data/" alt="">
  <img src="/sneaky-redirect" alt="">
  <script>
    window.jQuery = {{ fn: {{ jquery: "1.12.4" }} }};
    console.error("Something broke in the shop script");
    try {{ new WebSocket("ws://10.0.0.1:6379/"); }} catch (e) {{}}
  </script>
  <script>undefinedFunction();</script>
</body></html>
"""
CHECKPOINT = """<!doctype html><title>Vercel Security Checkpoint</title>
<p>We're verifying your browser</p>"""

# The smallest valid GIF image (1x1 pixel).
GIF = bytes.fromhex(
    "47494638396101000100800000000000ffffff21f90401000000002c00000000010001000002024401003b"
)


class Handler(BaseHTTPRequestHandler):
    port = 0  # set by the server_port fixture once the server has a port

    def log_message(self, *args: object) -> None:  # keep test output quiet
        pass

    def do_GET(self) -> None:  # the method name is required by http.server
        if self.path == "/checkpoint":
            self.send_response(429)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(CHECKPOINT.encode())
        elif self.path == "/sneaky-redirect":
            self.send_response(302)
            self.send_header("Location", "http://10.0.0.1/admin")  # internal address!
            self.end_headers()
        elif self.path.endswith(".gif"):
            self.send_response(200)
            self.send_header("Content-Type", "image/gif")
            if self.path == "/pixel.gif":
                self.send_header("Set-Cookie", "tracker=1; Path=/")
            self.end_headers()
            self.wfile.write(GIF)
        else:
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Set-Cookie", "session=abc; Path=/")
            self.end_headers()
            self.wfile.write(PAGE.format(port=self.port).encode())


@pytest.fixture(scope="module")
def server_port() -> Iterator[int]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    Handler.port = server.server_port
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_port
    server.shutdown()


class LocalTestGuard(NetGuard):
    """The real SSRF rules, except that our own test server is allowed."""

    def __init__(self, port: int) -> None:
        super().__init__(resolver=fake_resolver)
        self.port = port

    async def check_url(self, url: str) -> None:
        parts = urlsplit(url)
        if parts.hostname in ("127.0.0.1", "localhost") and parts.port == self.port:
            return
        await super().check_url(url)


async def test_render_collects_browser_data_safely(server_port: int) -> None:
    url = f"http://127.0.0.1:{server_port}/"
    ctx = make_context(make_page("", url=url))
    config = EngineConfig(render_timeout=20)
    fetcher = Fetcher(config, guard=LocalTestGuard(server_port))

    try:
        await collect_render(ctx, fetcher, config)
    except Exception as error:  # Chromium not installed on this machine
        if "Executable doesn't exist" in str(error):
            pytest.skip("Chromium isn't installed: python -m playwright install chromium")
        raise

    assert ctx.has(RENDER)
    render = ctx.render
    assert render is not None

    # The page as the browser saw it
    assert "<h1>Test shop</h1>" in render.html
    assert render.text_length > 0
    assert render.screenshot_jpeg is not None
    assert render.screenshot_jpeg[:2] == b"\xff\xd8"  # JPEG files start with these bytes

    # JavaScript problems
    assert any("Something broke" in e for e in render.console_errors)
    assert any("undefinedFunction" in e for e in render.console_errors)
    assert not any("ERR_BLOCKED_BY_CLIENT" in e for e in render.console_errors)

    # Libraries seen at runtime
    assert render.libraries == {"jQuery": "1.12.4"}

    # Cookies: "session" from the site itself, "tracker" from another host (localhost)
    cookies = {c.name: c.third_party for c in render.cookies}
    assert cookies == {"session": False, "tracker": True}

    # SSRF: the metadata address and the redirect to 10.0.0.1 were both stopped
    assert "http://169.254.169.254/latest/meta-data/" in render.blocked_requests
    assert "http://10.0.0.1/admin" in render.blocked_requests

    # axe-core ran: the first image has no alt text
    assert "image-alt" in {v.id for v in render.axe_violations}
    assert render.axe_passes


async def test_firewall_checkpoint_is_not_reported_as_the_website(
    server_port: int, monkeypatch: pytest.MonkeyPatch
) -> None:
    """If the browser only sees "We're verifying your browser", discard what it saw."""
    import functools

    from bizzcheckup.engine.collectors import render

    monkeypatch.setattr(  # don't wait the full 10 seconds in tests
        render,
        "_wait_for_checkpoint_to_clear",
        functools.partial(render._wait_for_checkpoint_to_clear, seconds=1),
    )
    url = f"http://127.0.0.1:{server_port}/checkpoint"
    ctx = make_context(make_page("", url=url))
    config = EngineConfig(render_timeout=20)

    try:
        await collect_render(ctx, Fetcher(config, guard=LocalTestGuard(server_port)), config)
    except Exception as error:
        if "Executable doesn't exist" in str(error):
            pytest.skip("Chromium isn't installed")
        raise

    assert not ctx.has(RENDER)  # browser checks will be skipped, not fed the checkpoint
    assert ctx.render is None  # no checkpoint screenshot in the report
    assert "security firewall (Vercel)" in ctx.unavailable[RENDER]
