"""Run a whole audit: crawl -> collectors -> checks -> scores -> AuditReport.

    report = await run_audit("https://shop.com", EngineConfig(), on_progress=save)

Everything here is async because fetching many pages at once is much faster
than one after another. The Celery task calls it with asyncio.run().
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable, Sequence
from datetime import UTC, datetime
from itertools import groupby

import httpx

from . import preview
from .checks.base import Check
from .collectors import DEFAULT_COLLECTORS, Collector
from .collectors.shots import take_shots
from .config import EngineConfig
from .context import PAGESPEED, PROBES, RENDER, AuditContext
from .crawler import UnusableHomepageError, crawl
from .fetcher import Fetcher, FetchError
from .netguard import BlockedURLError, NetGuard
from .registry import Registry, load_builtin_checks
from .scoring import band_for, health_score, score_categories
from .types import AuditReport, CheckResult, CheckStatus, LinkPreview, ReportImage

logger = logging.getLogger(__name__)

# on_progress(percent, step) is awaited after every stage.
ProgressCallback = Callable[[int, str], Awaitable[None]]

# Progress milestones (percent). The progress page's steps use the same numbers
# (checkups/progress.py), so keep them in sync.
CRAWL_START = 3
COLLECT_START = 20  # the slow part: browser, PageSpeed, probes (in parallel)
COLLECT_END = 70
CHECKS_START = 70  # five categories, quick
CHECKS_STEP = 4
SHOTS_START = 88  # pictures of where the problems are
REPORT_START = 90  # scoring here, then the web app saves the report and makes the PDF

# What the visitor reads while each data source is still working.
COLLECTOR_LABELS = {
    "collect_probes": "Checking links, security and AI access",
    "collect_render": "Opening your site in a real browser",
    "collect_pagespeed": "Measuring speed with Google PageSpeed",
}

SKIP_REASONS = {  # a data source was tried but failed
    RENDER: "We couldn't open your site in a browser, so this wasn't checked.",
    PAGESPEED: "Google PageSpeed couldn't measure your site this time, so speed wasn't checked.",
    PROBES: "Extra checks of your site couldn't be completed.",
}
NO_PAGESPEED_KEY = "Speed wasn't measured because no PageSpeed API key is configured."


class AuditError(Exception):
    """The audit could not run. The message is safe to show to the visitor."""


async def run_audit(
    url: str,
    config: EngineConfig,
    *,
    registry: Registry | None = None,
    collectors: Sequence[Collector] | None = None,
    on_progress: ProgressCallback | None = None,
    guard: NetGuard | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> AuditReport:
    """Audit `url` (already normalised). Raises AuditError with a friendly message.

    `collectors=None` uses DEFAULT_COLLECTORS; pass `()` to run checks on the crawl only.
    """
    if collectors is None:
        collectors = DEFAULT_COLLECTORS
    try:
        async with asyncio.timeout(config.total_timeout):
            return await _run(url, config, registry, collectors, on_progress, guard, transport)
    except TimeoutError as error:
        raise AuditError(
            "Your website took too long to check. Please try again in a few minutes."
        ) from error


async def _run(
    url: str,
    config: EngineConfig,
    registry: Registry | None,
    collectors: Sequence[Collector],
    on_progress: ProgressCallback | None,
    guard: NetGuard | None,
    transport: httpx.AsyncBaseTransport | None,
) -> AuditReport:
    async def progress(percent: int, step: str) -> None:
        if on_progress is not None:
            await on_progress(percent, step)

    started_at = datetime.now(UTC)
    checks = (registry or load_builtin_checks()).all()

    async with Fetcher(config, guard=guard, transport=transport) as fetcher:
        await progress(CRAWL_START, "Visiting your website")
        try:
            result = await crawl(fetcher, url)
        except (BlockedURLError, UnusableHomepageError) as error:
            raise AuditError(str(error)) from error
        except FetchError as error:
            raise AuditError(
                "We couldn't reach your website. Please check the address and try again."
            ) from error

        ctx = AuditContext(crawl=result)
        net_guard = fetcher.guard  # the shots step (after the checks) uses it too
        page_word = "page" if len(result.pages) == 1 else "pages"
        await progress(COLLECT_START, f"Found {len(result.pages)} {page_word}, taking vital signs")

        # Collectors run at the same time; one failing data source must not stop the
        # audit. Each one that finishes moves the progress bar and the message shows
        # what is still running (usually the slow PageSpeed test).
        # Fixed order for messages: quick probes, then the browser, then PageSpeed (slowest).
        order = list(COLLECTOR_LABELS)
        pending = sorted(
            (getattr(c, "__name__", "") for c in collectors),
            key=lambda n: order.index(n) if n in order else len(order),
        )

        async def run_collector(collector: Collector) -> None:
            try:
                await collector(ctx, fetcher, config)
            finally:
                name = getattr(collector, "__name__", "")
                if name in pending:
                    pending.remove(name)
                done = len(collectors) - len(pending)
                percent = COLLECT_START + round(
                    (COLLECT_END - COLLECT_START) * done / max(len(collectors), 1)
                )
                waiting = [COLLECTOR_LABELS.get(n, "Taking vital signs") for n in pending]
                await progress(percent, f"{waiting[0]}…" if waiting else "Vital signs taken")

        if collectors:
            first = [COLLECTOR_LABELS.get(n, "Taking vital signs") for n in pending]
            await progress(COLLECT_START + 1, f"{first[0]}…")
        outcomes = await asyncio.gather(
            *(run_collector(collector) for collector in collectors),
            return_exceptions=True,
        )
        for collector, outcome in zip(collectors, outcomes, strict=True):
            if isinstance(outcome, BaseException):
                name = getattr(collector, "__name__", repr(collector))
                logger.error("Collector %s failed: %r", name, outcome, exc_info=outcome)
        if not config.psi_api_key:
            ctx.unavailable[PAGESPEED] = NO_PAGESPEED_KEY

    results: list[CheckResult] = []
    groups = [(category, list(items)) for category, items in groupby(checks, lambda c: c.category)]
    for index, (category, group) in enumerate(groups):
        await progress(CHECKS_START + CHECKS_STEP * index, f"Checking {category.label}")
        results.extend(run_check(check, ctx) for check in group)

    # Pictures of where the problems are, if a browser could open the site.
    shot_images: dict[str, ReportImage] = {}
    if ctx.has(RENDER) and config.max_shots:
        await progress(SHOTS_START, "Taking pictures of the problems")
        results, shot_images = await take_shots(results, net_guard, config)

    await progress(REPORT_START, "Preparing your report")
    categories = score_categories(results)
    overall = health_score(categories)

    notes: list[str] = []
    if RENDER in ctx.unavailable:  # e.g. a firewall checkpoint stopped the browser
        notes.append(ctx.unavailable[RENDER])
    if result.skipped_by_robots:
        notes.append(
            f"Your robots.txt asks robots not to visit {len(result.skipped_by_robots)} "
            "page(s), so we left them out."
        )

    return AuditReport(
        url=url,
        final_url=result.final_url,
        started_at=started_at,
        finished_at=datetime.now(UTC),
        pages=[page.final_url for page in result.pages],
        discovered_pages=result.discovered or [page.final_url for page in result.pages],
        categories=categories,
        health_score=overall,
        health_band=band_for(overall),
        results=results,
        notes=notes,
        browser_note=ctx.unavailable.get(RENDER, ""),
        link_preview=link_preview(ctx),
        screenshot_jpeg=ctx.render.screenshot_jpeg if ctx.render else None,
        images=report_images(ctx) | shot_images,
    )


def link_preview(ctx: AuditContext) -> LinkPreview:
    """How the homepage looks when shared, for the preview card in the report."""
    summary = preview.summary(ctx.homepage.final_url, ctx.tree(ctx.homepage))
    return summary.model_copy(update={"image_ok": ctx.probes.og_image is not None})


def report_images(ctx: AuditContext) -> dict[str, ReportImage]:
    images: dict[str, ReportImage] = {}
    if ctx.probes.og_image is not None:
        images["link_preview"] = ReportImage(
            content_type=ctx.probes.og_image_type, data=ctx.probes.og_image
        )
    for key, data in (ctx.render.element_shots if ctx.render else {}).items():
        images[key] = ReportImage(content_type="image/jpeg", data=data)
    for view in ctx.render.devices if ctx.render else []:
        if view.screenshot_jpeg:
            images[view.name] = ReportImage(content_type="image/jpeg", data=view.screenshot_jpeg)
    return images


def run_check(check_class: type[Check], ctx: AuditContext) -> CheckResult:
    """Run one check safely. A crash is recorded, never raised."""

    def result(status: CheckStatus, **extra: object) -> CheckResult:
        return CheckResult.model_validate(
            {
                "check_id": check_class.id,
                "category": check_class.category,
                "title": check_class.title,
                "weight": check_class.weight,
                "status": status,
                **extra,
            }
        )

    missing = sorted(check_class.requires - ctx.capabilities)
    if missing:
        reason = ctx.unavailable.get(missing[0]) or SKIP_REASONS.get(missing[0], "Not checked.")
        return result(CheckStatus.SKIPPED, note=reason)

    check = check_class()
    try:
        findings = check.run(ctx)
        score = check.score(findings)
    except Exception:
        logger.exception("Check %s failed", check_class.id)
        return result(CheckStatus.ERROR, note="This check could not be completed.")

    if not findings:  # e.g. "form labels" on a site without forms
        return result(CheckStatus.SKIPPED, note="Not applicable to this website.")
    if any(f.category is not check_class.category for f in findings):
        logger.error("Check %s returned findings for another category", check_class.id)
        return result(CheckStatus.ERROR, note="This check could not be completed.")

    return result(CheckStatus.RAN, score=max(0.0, min(1.0, score)), findings=findings)
