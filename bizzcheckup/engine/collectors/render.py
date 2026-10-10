"""RENDER collector: open the homepage in a real browser (headless Chromium).

Collects what only a browser can see: the page after JavaScript runs, a
screenshot, JavaScript errors, cookies, library versions and an axe-core
accessibility scan. Then it opens the page again as a phone and as a tablet to
see whether it fits, and whether it can be tapped and read there.

Safety: the browser could be tricked into visiting internal addresses just
like our fetcher, so EVERY browser request goes through `_SafeRouter`:
- each URL, and each hop of every redirect, passes the SSRF guard
  (Playwright doesn't show us redirect hops itself, so we follow them here)
- WebSockets and service workers, which bypass request interception, are blocked
"""

import asyncio
import contextlib
import logging
from pathlib import Path
from typing import Any
from urllib.parse import urljoin, urlsplit

from playwright.async_api import (
    Browser,
    ConsoleMessage,
    Route,
    WebSocketRoute,
    async_playwright,
)
from playwright.async_api import Error as PlaywrightError
from playwright.async_api import Page as BrowserPage

from ..config import DEVICES, EngineConfig
from ..context import RENDER, AuditContext
from ..fetcher import REDIRECT_CODES, Fetcher
from ..firewall import blocked_message, checkpoint_provider
from ..netguard import BlockedURLError, NetGuard
from ..types import AxeRule, Cookie, DeviceView, RenderResult
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
      details: v.nodes.slice(0, MAX_TARGETS).map((n) => ({
        target: String(n.target),
        html: (n.html || "").slice(0, 400),
        summary: (n.failureSummary || "").slice(0, 600),
        text: (() => {
          try {
            const el = document.querySelector(String(n.target));
            return el ? (el.innerText || el.getAttribute("alt") || "").trim().slice(0, 80) : "";
          } catch (e) { return ""; }
        })(),
      })),
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

            response = await page.goto(url, wait_until="load", timeout=timeout_ms)
            await _wait_until_quiet(page)

            # A firewall checkpoint ("We're verifying your browser")? Some clear by
            # themselves after a few seconds; if this one doesn't, we must not report
            # on the checkpoint page as if it were the website.
            status = response.status if response else 200
            headers = {k.lower(): v for k, v in (response.headers if response else {}).items()}
            provider = checkpoint_provider(status, headers, await page.content())
            if provider is not None:
                provider = await _wait_for_checkpoint_to_clear(page)
            if provider is not None:
                ctx.unavailable[RENDER] = blocked_message(provider, "browser")
                logger.info("Browser checks skipped for %s: %s checkpoint", url, provider or "a")
                return

            html = (await page.content())[: config.max_page_bytes]
            text_length = int(
                await page.evaluate("() => document.body ? document.body.innerText.length : 0")
            )
            screenshot = await page.screenshot(type="jpeg", quality=70)
            libraries: dict[str, str] = await page.evaluate(LIBRARIES_JS)
            axe = await _run_axe(page)
            violations = [AxeRule.model_validate(v) for v in axe.get("violations", [])]
            element_shots = await _photograph_elements(page, violations)
            cookies = await context.cookies()
            await context.close()
            views = await asyncio.gather(
                *(_view_on_device(browser, router, url, config, name) for name in DEVICES)
            )
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
        axe_violations=violations,
        axe_passes=[str(p) for p in axe.get("passes", [])],
        blocked_requests=router.blocked,
        screenshot_jpeg=screenshot,
        element_shots=element_shots,
        devices=[view for view in views if view is not None],
    )
    ctx.capabilities.add(RENDER)


async def _wait_for_checkpoint_to_clear(page: BrowserPage, seconds: float = 10) -> str | None:
    """Give a checkpoint page a few seconds; returns the provider if it's still there."""
    provider: str | None = None
    for _ in range(int(seconds * 2)):
        await page.wait_for_timeout(500)
        provider = checkpoint_provider(200, {}, await page.content())
        if provider is None:
            await _wait_until_quiet(page)  # the real site is loading now
            return None
    return provider


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


# --- phones and tablets -------------------------------------------------------------------

# Measures, inside the page, what makes a site hard to use on a small screen:
# - the layout width: without a viewport tag, phones lay the page out 980 px wide
#   and shrink it, so everything is tiny
# - sideways scrolling (the page is wider than the screen) and what sticks out
# - links and buttons too small to tap (WCAG 2.5.8: at least 24 x 24 CSS pixels);
#   links inside a sentence are exempt, like in WCAG
# - text smaller than 12 px
MEASURE_JS = """() => {
  const MAX_EXAMPLES = 8;
  const doc = document.documentElement;
  const width = doc.clientWidth;
  const scrollWidth = Math.max(doc.scrollWidth, document.body ? document.body.scrollWidth : 0);

  const describe = (el) => {
    let text = el.tagName.toLowerCase();
    if (el.id) text += "#" + el.id;
    const classes = (el.getAttribute("class") || "").trim().split(/ +/).filter(Boolean);
    if (classes.length) text += "." + classes.slice(0, 2).join(".");
    const label = (el.getAttribute("aria-label") || el.textContent || "")
      .trim().replace(/ +/g, " ");
    return label ? text + ' "' + label.slice(0, 40) + '"' : text;
  };
  // A CSS path to the element, so the shots step can photograph it later.
  const cssPath = (el) => {
    const parts = [];
    while (el && el.nodeType === 1 && el.tagName !== "HTML") {
      const tag = el.tagName.toLowerCase();
      if (tag === "body") { parts.unshift("body"); break; }
      if (el.id && /^[A-Za-z][A-Za-z0-9_-]*$/.test(el.id)) { parts.unshift("#" + el.id); break; }
      const parent = el.parentElement;
      const same = parent ? [...parent.children].filter((c) => c.tagName === el.tagName) : [];
      parts.unshift(same.length > 1 ? tag + ":nth-of-type(" + (same.indexOf(el) + 1) + ")" : tag);
      el = parent;
    }
    return parts.join(" > ");
  };
  const visible = (el, box) => {
    if (box.width === 0 || box.height === 0) return false;
    const style = getComputedStyle(el);
    return style.visibility !== "hidden" && style.display !== "none" && style.opacity !== "0";
  };

  const overflowing = [];
  if (scrollWidth > width + 2) {
    for (const el of document.body.querySelectorAll("*")) {
      const box = el.getBoundingClientRect();
      if (box.right > width + 2 && visible(el, box) && getComputedStyle(el).position !== "fixed") {
        // keep the outermost culprit only: skip children of an element already listed
        if (!overflowing.some((parent) => parent.contains(el))) overflowing.push(el);
        if (overflowing.length >= MAX_EXAMPLES) break;
      }
    }
  }

  const selector = 'a[href], button, input:not([type="hidden"]), select, textarea, [role="button"]';
  let targets = 0;
  const small = [];
  for (const el of document.querySelectorAll(selector)) {
    const box = el.getBoundingClientRect();
    if (!visible(el, box)) continue;
    const parent = el.parentElement;
    const inSentence = el.tagName === "A" && getComputedStyle(el).display === "inline"
      && parent && ["P", "LI", "TD", "SPAN", "LABEL"].includes(parent.tagName)
      && (parent.textContent || "").trim().length > (el.textContent || "").trim().length + 20;
    if (inSentence) continue;
    // Screen-reader-only links ("Skip to content") are 1 x 1 px until focused: not targets.
    if (box.width <= 2 || box.height <= 2) continue;
    targets += 1;
    if (box.width < 24 || box.height < 24) small.push(el);
  }

  let textChars = 0;
  let smallTextChars = 0;
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  while (walker.nextNode()) {
    const node = walker.currentNode;
    const length = node.textContent.trim().length;
    const el = node.parentElement;
    if (!length || !el) continue;
    const box = el.getBoundingClientRect();
    if (!visible(el, box)) continue;
    textChars += length;
    if (parseFloat(getComputedStyle(el).fontSize) < 12) smallTextChars += length;
  }

  return {
    layout_width: width,
    scroll_width: scrollWidth,
    overflowing: overflowing.map(describe),
    overflowing_selectors: overflowing.map(cssPath),
    tap_targets: targets,
    small_tap_targets: small.length,
    small_tap_examples: small.slice(0, MAX_EXAMPLES).map(describe),
    small_tap_selectors: small.slice(0, MAX_EXAMPLES).map(cssPath),
    text_chars: textChars,
    small_text_chars: smallTextChars,
  };
}"""


async def _view_on_device(
    browser: Browser,
    router: _SafeRouter,
    url: str,
    config: EngineConfig,
    name: str,
) -> DeviceView | None:
    """Open the homepage like a phone or tablet would. None if it couldn't be done."""
    device = DEVICES[name]
    context = await browser.new_context(
        user_agent=device["user_agent"],
        viewport={"width": device["width"], "height": device["height"]},
        is_mobile=True,
        has_touch=True,
        service_workers="block",
    )
    try:
        await context.route("**/*", router.handle)
        await context.route_web_socket("**/*", _refuse_websocket)
        page = await context.new_page()
        await page.goto(url, wait_until="load", timeout=config.render_timeout * 1000)
        await _wait_until_quiet(page)
        if checkpoint_provider(200, {}, await page.content()) is not None:
            return None
        measured: dict[str, Any] = await page.evaluate(MEASURE_JS)
        screenshot = await page.screenshot(type="jpeg", quality=70)
    except PlaywrightError as error:
        logger.info("Couldn't open %s as a %s: %s", url, name, error)
        return None
    finally:
        await context.close()
    return DeviceView(
        name=name,
        width=device["width"],
        height=device["height"],
        screenshot_jpeg=screenshot,
        **measured,
    )


# --- pictures of the elements axe flagged -------------------------------------------------

MAX_ELEMENT_SHOTS = 10  # screenshots per check-up (they take ~0.5 s each)
SHOTS_PER_RULE = 3
SHOT_PADDING = 32  # CSS pixels of surroundings around the element
SHOT_MIN_WIDTH = 360  # enough context to recognise the spot on the page
SHOT_MAX_HEIGHT = 420

# Scrolls the element to the middle of the screen, outlines it and dims the rest, and
# returns the area to photograph (screen coordinates), or null if it can't be seen.
HIGHLIGHT_JS = """(args) => {
  const [selector, padding, minWidth, maxHeight] = args;
  let el = null;
  try { el = document.querySelector(selector); } catch (e) { return null; }
  if (!el) return null;
  el.scrollIntoView({ block: "center", inline: "nearest", behavior: "instant" });
  const box = el.getBoundingClientRect();
  if (box.width === 0 || box.height === 0) return null;
  const mark = document.createElement("div");
  mark.id = "__bizzcheckup_mark";
  Object.assign(mark.style, {
    position: "fixed", left: (box.left - 4) + "px", top: (box.top - 4) + "px",
    width: (box.width + 8) + "px", height: (box.height + 8) + "px",
    border: "3px solid #e11d48", borderRadius: "6px", pointerEvents: "none",
    boxShadow: "0 0 0 9999px rgba(15, 23, 42, 0.35)", zIndex: "2147483647",
  });
  document.documentElement.appendChild(mark);
  const vw = document.documentElement.clientWidth, vh = window.innerHeight;
  const width = Math.min(vw, Math.max(minWidth, box.width + 2 * padding));
  const height = Math.min(vh, maxHeight, box.height + 2 * padding);
  const centerX = box.left + box.width / 2, centerY = box.top + box.height / 2;
  const x = Math.max(0, Math.min(vw - width, centerX - width / 2));
  const y = Math.max(0, Math.min(vh - height, centerY - height / 2));
  return { x: x, y: y, width: width, height: height };
}"""
UNHIGHLIGHT_JS = """() => {
  const mark = document.getElementById("__bizzcheckup_mark");
  if (mark) mark.remove();
}"""


async def _photograph_elements(page: BrowserPage, rules: list[AxeRule]) -> dict[str, bytes]:
    """Screenshot a few flagged elements, outlined in red. Fills in AxeNode.image."""
    shots: dict[str, bytes] = {}
    for rule in rules:
        for node in rule.details[:SHOTS_PER_RULE]:
            if len(shots) >= MAX_ELEMENT_SHOTS:
                return shots
            key = f"element-{len(shots) + 1}"
            try:
                clip = await page.evaluate(
                    HIGHLIGHT_JS, [node.target, SHOT_PADDING, SHOT_MIN_WIDTH, SHOT_MAX_HEIGHT]
                )
                if not clip:
                    continue
                await page.wait_for_timeout(400)  # let scroll animations settle
                shots[key] = await page.screenshot(type="jpeg", quality=75, clip=clip)
                node.image = key
            except PlaywrightError as error:
                logger.info("Couldn't photograph %s: %s", node.target, error)
            finally:
                with contextlib.suppress(PlaywrightError):
                    await page.evaluate(UNHIGHLIGHT_JS)
    return shots
