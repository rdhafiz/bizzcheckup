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

from .checks.base import Check
from .config import EngineConfig
from .context import PAGESPEED, PROBES, RENDER, AuditContext
from .crawler import UnusableHomepageError, crawl
from .fetcher import Fetcher, FetchError
from .netguard import BlockedURLError, NetGuard
from .registry import Registry, load_builtin_checks
from .scoring import band_for, health_score, score_categories
from .types import AuditReport, CheckResult, CheckStatus

logger = logging.getLogger(__name__)

# on_progress(percent, step) is awaited after every stage.
ProgressCallback = Callable[[int, str], Awaitable[None]]
# A collector adds data to the context and marks capabilities (phases 4-5).
Collector = Callable[[AuditContext, Fetcher, EngineConfig], Awaitable[None]]

SKIP_REASONS = {
    RENDER: "We couldn't open your site in a browser, so this wasn't checked.",
    PAGESPEED: "Speed wasn't measured because no PageSpeed API key is configured.",
    PROBES: "Extra checks of your site couldn't be completed.",
}


class AuditError(Exception):
    """The audit could not run. The message is safe to show to the visitor."""


async def run_audit(
    url: str,
    config: EngineConfig,
    *,
    registry: Registry | None = None,
    collectors: Sequence[Collector] = (),
    on_progress: ProgressCallback | None = None,
    guard: NetGuard | None = None,
    transport: httpx.AsyncBaseTransport | None = None,
) -> AuditReport:
    """Audit `url` (already normalised). Raises AuditError with a friendly message."""
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
        await progress(5, "Visiting your website")
        try:
            result = await crawl(fetcher, url)
        except (BlockedURLError, UnusableHomepageError) as error:
            raise AuditError(str(error)) from error
        except FetchError as error:
            raise AuditError(
                "We couldn't reach your website. Please check the address and try again."
            ) from error

        ctx = AuditContext(crawl=result)
        await progress(25, "Taking your website's vital signs")
        for collector in collectors:
            try:
                await collector(ctx, fetcher, config)
            except Exception:  # one failing data source must not stop the audit
                logger.exception("Collector %s failed", getattr(collector, "__name__", collector))

    results: list[CheckResult] = []
    groups = [(category, list(items)) for category, items in groupby(checks, lambda c: c.category)]
    for index, (category, group) in enumerate(groups):
        await progress(40 + round(50 * index / max(len(groups), 1)), f"Checking {category.label}")
        results.extend(run_check(check, ctx) for check in group)

    await progress(95, "Preparing your report")
    categories = score_categories(results)
    overall = health_score(categories)

    notes: list[str] = []
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
        categories=categories,
        health_score=overall,
        health_band=band_for(overall),
        results=results,
        notes=notes,
    )


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
        return result(CheckStatus.SKIPPED, note=SKIP_REASONS.get(missing[0], "Not checked."))

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
