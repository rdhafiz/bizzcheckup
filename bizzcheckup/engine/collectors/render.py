"""RENDER collector: open the homepage in a real browser (headless Chromium).

Collects what only a browser can see: the page after JavaScript runs, a
screenshot, JavaScript errors, cookies, library versions and an axe-core
accessibility scan.

Safety: the browser could be tricked into visiting internal addresses just
like our fetcher, so EVERY browser request goes through `_SafeRouter`:
- each URL, and each hop of every redirect, passes the SSRF guard
  (Playwright doesn't show us redirect hops itself, so we follow them here)
- WebSockets and service workers, which bypass request interception, are blocked
"""

import contextlib
import logging
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

from playwright.async_api import ConsoleMessage, Route, WebSocketRoute, async_playwright
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page as BrowserPage

from ..config import EngineConfig
from ..context import RENDER, AuditContext
from ..fetcher import REDIRECT_CODES, Fetcher
from ..netguard import BlockedURLError, NetGuard
from ..types import AxeRule, Cookie, RenderResult
from ..urls import same_site

logger = logging.getLogger(__name__)

AXE_SOURCE = (Path(__file__).resolve().parent.parent / "vendor" / "axe.min.js").read_text(
    encoding="utf-8"
)
AXE_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa", "wcag22aa", "best-practice"]
MAX_TARGETS = 5  # example elements kept per failing rule

# Runs inside the page. Returns small, plain data (big results would be slow).
AXE_RUN = (
    """async (tags) => {
  const result = await axe.run(document, {
    runOnly: { type: "tag", values: tags },
    resultTypes: ["violations"],
  });
  return {
    violations: result.violations.map((v) => ({
      id: v.id,
      impact: v.impact || "minor",
      help: v.help,
      help_url: v.helpUrl,
      nodes: v.nodes.length,
      targets: v.nodes.slice(0, MAX_TARGETS).map((n) => String(n.target)),
    })),
    passes: result.passes.map((p) => p.id),
  };
}"""
).replace("MAX_TARGETS", str(MAX_TARGETS))

# Versions of popular libraries, read from the running page.
LIBRARIES_JS = """() => {
  const found = {};
  try {
    if (window.jQuery && jQuery.fn && jQuery.fn.jquery) found.jQuery = jQuery.fn.jquery;
  } catch (e) {}
  try {
    const bs = (window.bootstrap && bootstrap.Tooltip && bootstrap.Tooltip.VERSION)
      || (window.jQuery && jQuery.fn.tooltip && jQuery.fn.tooltip.Constructor
          && jQuery.fn.tooltip.Constructor.VERSION);
    if (bs) found.Bootstrap = bs;
  } catch (e) {}
  try {
    if (window.angular && angular.version) found.AngularJS = angular.version.full;
  } catch (e) {}
  try {
    if (window._ && _.VERSION && typeof _.flatMapDeep === "function") found.Lodash = _.VERSION;
  } catch (e) {}
  return found;
}"""


class _SafeRouter:
    """Intercepts every browser request and only lets safe ones through."""

    def __init__(self, guard: NetGuard, max_redirects: int) -> None:
        self.guard = guard
        self.max_redirects = max_redirects
        self.blocked: list[str] = []

    async def handle(self, route: Route) -> None:
        url = route.request.url
        if url.startswith(("data:", "blob:", "about:")):
            await route.continue_()
            return

        current = url
        for _ in range(self.max_redirects + 1):
            try:
                await self.guard.check_url(current)
            except BlockedURLError:
                self.blocked.append(current)
                await route.abort("blockedbyclient")
                return
            try:
                response = await route.fetch(url=current, max_redirects=0)
            except PlaywrightError:
                await route.abort("failed")
                return
            location = response.headers.get("location")
            if response.status in REDIRECT_CODES and location:
                current = urljoin(current, location)  # check the next hop first
                continue
            await route.fulfill(response=response)
            return
        await route.abort("failed")  # too many redirects


async def collect_render(ctx: AuditContext, fetcher: Fetcher, config: EngineConfig) -> None:
    url = ctx.homepage.final_url  # already known: no redirect needed at the start
    router = _SafeRouter(fetcher.guard, config.max_redirects)
    errors: list[str] = []
    timeout_ms = config.render_timeout * 1000

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(args=["--disable-dev-shm-usage"])
        try:
            context = await browser.new_context(
                user_agent=config.user_agent,
                viewport={"width": config.viewport_width, "height": config.viewport_height},
                service_workers="block",  # service workers would bypass our router
            )
            await context.route("**/*", router.handle)
            await context.route_web_socket("**/*", _refuse_websocket)
            page = await context.new_page()

            def on_console(message: ConsoleMessage) -> None:
                if message.type == "error":
                    errors.append(message.text)

            def on_page_error(error: PlaywrightError) -> None:
                errors.append(str(error))

            page.on("console", on_console)
            page.on("pageerror", on_page_error)

            await page.goto(url, wait_until="load", timeout=timeout_ms)
            await _wait_until_quiet(page)

            html = (await page.content())[: config.max_page_bytes]
            text_length = int(
                await page.evaluate("() => document.body ? document.body.innerText.length : 0")
            )
            screenshot = await page.screenshot(type="jpeg", quality=70)
            libraries: dict[str, str] = await page.evaluate(LIBRARIES_JS)
            axe = await _run_axe(page)
            cookies = await context.cookies()
        finally:
            await browser.close()

    host = urlsplit(url).hostname or ""
    ctx.render = RenderResult(
        url=url,
        html=html,
        text_length=text_length,
        console_errors=[e for e in errors if not _caused_by_us(e)],
        cookies=[
            Cookie(
                name=str(c.get("name", "")),
                domain=str(c.get("domain", "")).lstrip("."),
                third_party=not same_site(str(c.get("domain", "")), host),
            )
            for c in cookies
        ],
        libraries={str(k): str(v) for k, v in libraries.items()},
        axe_violations=[AxeRule.model_validate(v) for v in axe.get("violations", [])],
        axe_passes=[str(p) for p in axe.get("passes", [])],
        blocked_requests=router.blocked,
        screenshot_jpeg=screenshot,
    )
    ctx.capabilities.add(RENDER)


async def _refuse_websocket(ws: WebSocketRoute) -> None:
    await ws.close()


async def _wait_until_quiet(page: BrowserPage) -> None:
    """Give late scripts a moment, without waiting forever on busy pages."""
    with contextlib.suppress(PlaywrightError):
        await page.wait_for_load_state("networkidle", timeout=5000)


async def _run_axe(page: BrowserPage) -> dict[str, Any]:
    # page.evaluate runs through the browser's debugging protocol, so the site's
    # Content-Security-Policy can't block it (an injected <script> tag could be).
    await page.evaluate(AXE_SOURCE)
    result: dict[str, Any] = await page.evaluate(AXE_RUN, AXE_TAGS)
    return result


def _caused_by_us(message: str) -> bool:
    """Errors from requests our safety router blocked aren't the site's fault."""
    return "ERR_BLOCKED_BY_CLIENT" in message
