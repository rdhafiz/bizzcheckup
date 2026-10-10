"""Pictures of where each problem is, taken after the checks have run.

Checks are pure (no browser), so they only say *where* a problem is: a `Shot` with a CSS
path and, when possible, an attribute to find the element by (an image's src, a link's
href). This step opens each of those pages once in headless Chromium, finds each element,
outlines it in red, dims the rest and takes a cropped screenshot. Phone-layout problems
are photographed in a phone-sized window.

Limits keep a check-up quick: at most `config.max_shots` pictures, the most serious
problems first, and `config.shots_budget` seconds in total. Whatever isn't done by then
is simply left without a picture. Every browser request passes the SSRF guard, as in the
render collector.
"""

import asyncio
import contextlib
import logging
from collections import defaultdict
from typing import Any

from playwright.async_api import Error as PlaywrightError
from playwright.async_api import async_playwright

from ..config import DEVICES, EngineConfig
from ..firewall import checkpoint_provider
from ..netguard import NetGuard
from ..types import CheckResult, ReportImage, Severity, Shot
from .render import (
    SHOT_MAX_HEIGHT,
    SHOT_MIN_WIDTH,
    SHOT_PADDING,
    UNHIGHLIGHT_JS,
    _refuse_websocket,
    _SafeRouter,
    _wait_until_quiet,
)

logger = logging.getLogger(__name__)

SEVERITY_FIRST = {Severity.FAIL: 0, Severity.WARN: 1, Severity.INFO: 2, Severity.PASS: 3}

# Finds the element (by attribute first, then by CSS path), scrolls it to the middle of
# the screen, outlines it and dims the rest. Returns the area to photograph, or null if
# the element isn't there or can't be seen (hidden in a closed menu, zero size...).
FIND_AND_HIGHLIGHT_JS = r"""(args) => {
  const [selector, tag, attr, value, text, padding, minWidth, maxHeight] = args;
  const words = (s) => (s || "").replace(/ +/g, " ").trim();
  const visible = (el) => {
    const box = el.getBoundingClientRect();
    const style = getComputedStyle(el);
    return box.width > 2 && box.height > 2
      && style.visibility !== "hidden" && style.display !== "none";
  };
  // Right element: visible, and (when we know its text) showing that text.
  const fits = (el) => el && visible(el) && (!text || words(el.textContent).includes(text));
  // The tag, from the match or from the last step of the path ("a:nth-of-type(2)" -> "a").
  const lastTag = (tag || selector.split(">").pop().trim().split(/[:.#\[]/)[0] || "*");
  let el = null;
  if (tag && attr) {
    el = [...document.getElementsByTagName(tag)]
      .find((e) => e.getAttribute(attr) === value && fits(e)) || null;
  }
  if (!el) {
    let byPath = null;
    try { byPath = document.querySelector(selector); } catch (e) { byPath = null; }
    if (fits(byPath)) el = byPath;
  }
  if (!el && text) {  // the page moved things around: find it by its text instead
    el = [...document.getElementsByTagName(lastTag)]
      .find((e) => fits(e) && words(e.textContent).startsWith(text)) || null;
  }
  if (!el) return null;
  el.scrollIntoView({ block: "center", inline: "nearest", behavior: "instant" });
  const box = el.getBoundingClientRect();
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
  const x = Math.max(0, Math.min(vw - width, box.left + box.width / 2 - width / 2));
  const y = Math.max(0, Math.min(vh - height, box.top + box.height / 2 - height / 2));
  return { x: x, y: y, width: width, height: height };
}"""

# For sites that animate anyway: no transitions or animations while we take pictures.
STILL_CSS = "*, *::before, *::after { transition: none !important; animation: none !important; }"

ShotKey = tuple[int, int, int]  # (result, finding, shot) positions


async def take_shots(
    results: list[CheckResult], guard: NetGuard, config: EngineConfig
) -> tuple[list[CheckResult], dict[str, ReportImage]]:
    """Photograph the shots of the most serious findings. Returns the results with each
    photographed shot's `image` filled in, and the pictures ("shot-1", "shot-2", ...)."""
    wanted = _choose(results, config.max_shots)
    if not wanted:
        return results, {}
    pictures: dict[ShotKey, bytes] = {}
    try:
        async with asyncio.timeout(config.shots_budget):
            await _photograph(wanted, guard, config, pictures)
    except TimeoutError:
        logger.info("Shots: time budget used up after %d pictures", len(pictures))
    except PlaywrightError as error:  # e.g. Chromium missing: the report just has no pictures
        logger.warning("Shots: the browser failed: %s", error)

    images: dict[str, ReportImage] = {}
    keys: dict[ShotKey, str] = {}
    for position, (key, _) in enumerate(sorted(pictures.items()), 1):
        keys[key] = f"shot-{position}"
        images[keys[key]] = ReportImage(content_type="image/jpeg", data=pictures[key])
    return _with_images(results, keys), images


def _choose(results: list[CheckResult], limit: int) -> list[tuple[ShotKey, Shot]]:
    """The shots to take: problems before notes, failures before warnings, at most `limit`."""
    candidates = [
        ((ri, fi, si), shot, finding.severity)
        for ri, result in enumerate(results)
        for fi, finding in enumerate(result.findings)
        if finding.severity is not Severity.PASS
        for si, shot in enumerate(finding.shots)
    ]
    candidates.sort(key=lambda item: (SEVERITY_FIRST[item[2]], item[0]))
    return [(key, shot) for key, shot, _ in candidates[:limit]]


async def _photograph(
    wanted: list[tuple[ShotKey, Shot]],
    guard: NetGuard,
    config: EngineConfig,
    pictures: dict[ShotKey, bytes],
) -> None:
    by_page: dict[tuple[str, str], list[tuple[ShotKey, Shot]]] = defaultdict(list)
    for key, shot in wanted:
        by_page[(shot.page, shot.device)].append((key, shot))

    router = _SafeRouter(guard, config.max_redirects)
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(args=["--disable-dev-shm-usage"])
        try:
            for (url, device), items in by_page.items():
                window: dict[str, Any] = (
                    {
                        "user_agent": DEVICES["mobile"]["user_agent"],
                        "viewport": {
                            "width": DEVICES["mobile"]["width"],
                            "height": DEVICES["mobile"]["height"],
                        },
                        "is_mobile": True,
                        "has_touch": True,
                    }
                    if device == "mobile"
                    else {
                        "user_agent": config.user_agent,
                        "viewport": {
                            "width": config.viewport_width,
                            "height": config.viewport_height,
                        },
                    }
                )
                # Reduced motion: most sites then show content at once instead of fading it
                # in on scroll, so pictures never catch an element half-faded.
                context = await browser.new_context(
                    service_workers="block", reduced_motion="reduce", **window
                )
                try:
                    await context.route("**/*", router.handle)
                    await context.route_web_socket("**/*", _refuse_websocket)
                    page = await context.new_page()
                    await page.goto(url, wait_until="load", timeout=config.render_timeout * 1000)
                    await _wait_until_quiet(page)
                    await page.add_style_tag(content=STILL_CSS)
                    if checkpoint_provider(200, {}, await page.content()) is not None:
                        continue  # a firewall checkpoint, not the website
                    for key, shot in items:
                        picture = await _shoot(page, shot)
                        if picture is not None:
                            pictures[key] = picture
                except PlaywrightError as error:
                    logger.info("Shots: couldn't open %s: %s", url, error)
                finally:
                    await context.close()
        finally:
            await browser.close()


async def _shoot(page: Any, shot: Shot) -> bytes | None:
    try:
        clip = await page.evaluate(
            FIND_AND_HIGHLIGHT_JS,
            [
                shot.selector,
                shot.match_tag,
                shot.match_attr,
                shot.match_value,
                shot.match_text,
                SHOT_PADDING,
                SHOT_MIN_WIDTH,
                SHOT_MAX_HEIGHT,
            ],
        )
        if not clip:
            return None
        await page.wait_for_timeout(400)  # let scroll-triggered animations settle
        picture: bytes = await page.screenshot(type="jpeg", quality=75, clip=clip)
        return picture
    except PlaywrightError as error:
        logger.info("Shots: couldn't photograph %s: %s", shot.label, error)
        return None
    finally:
        with contextlib.suppress(PlaywrightError):
            await page.evaluate(UNHIGHLIGHT_JS)


def _with_images(results: list[CheckResult], keys: dict[ShotKey, str]) -> list[CheckResult]:
    if not keys:
        return results
    updated = []
    for ri, result in enumerate(results):
        findings = [
            finding.model_copy(
                update={
                    "shots": [
                        shot.model_copy(update={"image": keys[(ri, fi, si)]})
                        if (ri, fi, si) in keys
                        else shot
                        for si, shot in enumerate(finding.shots)
                    ]
                }
            )
            if any((ri, fi, si) in keys for si in range(len(finding.shots)))
            else finding
            for fi, finding in enumerate(result.findings)
        ]
        updated.append(result.model_copy(update={"findings": findings}))
    return updated
