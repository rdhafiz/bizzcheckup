import asyncio
from collections.abc import Sequence

import httpx
import pytest
import respx

from bizzcheckup.engine.checks.base import Check
from bizzcheckup.engine.collectors import Collector
from bizzcheckup.engine.config import EngineConfig
from bizzcheckup.engine.context import PAGESPEED, AuditContext
from bizzcheckup.engine.fetcher import Fetcher
from bizzcheckup.engine.netguard import NetGuard
from bizzcheckup.engine.registry import Registry
from bizzcheckup.engine.runner import AuditError, run_audit, run_check
from bizzcheckup.engine.types import (
    AuditReport,
    Band,
    Category,
    CheckStatus,
    Finding,
    Level,
    Severity,
)

from .conftest import fake_resolver
from .factories import make_context


class HasTitle(Check, register=False):
    id = "seo.has_title"
    category = Category.SEO
    title = "Page title"

    def run(self, ctx: AuditContext) -> list[Finding]:
        if ctx.tree(ctx.homepage).css_first("title"):
            return [self.passed("Your homepage has a title.", "Google shows it.")]
        return [self.finding(Severity.FAIL, "No title.", "Google shows it.", "Add one.")]


class NeedsPageSpeed(Check, register=False):
    id = "performance.psi"
    category = Category.PERFORMANCE
    title = "PageSpeed"
    requires = frozenset({PAGESPEED})

    def run(self, ctx: AuditContext) -> list[Finding]:
        raise AssertionError("must be skipped without a PageSpeed key")


class Crashes(Check, register=False):
    id = "agentic.crashes"
    category = Category.AGENTIC
    title = "Crashes"

    def run(self, ctx: AuditContext) -> list[Finding]:
        raise ZeroDivisionError


class NotApplicable(Check, register=False):
    id = "accessibility.forms"
    category = Category.ACCESSIBILITY
    title = "Form labels"

    def run(self, ctx: AuditContext) -> list[Finding]:
        return []


class SeriousProblem(Check, register=False):
    id = "best_practices.https"
    category = Category.BEST_PRACTICES
    title = "HTTPS"

    def run(self, ctx: AuditContext) -> list[Finding]:
        return [
            self.finding(
                Severity.FAIL, "No HTTPS.", "Browsers warn.", "Add TLS.", impact=Level.HIGH
            )
        ]


def registry_with(*checks: type[Check]) -> Registry:
    registry = Registry()
    for check in checks:
        registry.register(check)
    return registry


@pytest.fixture
def site(router: respx.Router) -> respx.Router:
    router.get("https://shop.test/").respond(
        200, html="<html><head><title>Shop</title></head><body>Hi</body></html>"
    )
    router.get("https://shop.test/robots.txt").respond(404)
    router.get("https://shop.test/sitemap.xml").respond(404)
    return router


async def audit(
    router: respx.Router, registry: Registry, collectors: Sequence[Collector] = ()
) -> AuditReport:
    return await run_audit(
        "https://shop.test/",
        EngineConfig(retries=0),
        registry=registry,
        collectors=collectors,
        guard=NetGuard(fake_resolver),
        transport=httpx.MockTransport(router.async_handler),
    )


async def test_full_audit_scores_and_handles_skips_and_crashes(site: respx.Router) -> None:
    steps: list[tuple[int, str]] = []

    async def on_progress(percent: int, step: str) -> None:
        steps.append((percent, step))

    registry = registry_with(HasTitle, NeedsPageSpeed, Crashes, NotApplicable, SeriousProblem)
    report = await run_audit(
        "https://shop.test/",
        EngineConfig(retries=0),
        registry=registry,
        collectors=(),
        guard=NetGuard(fake_resolver),
        transport=httpx.MockTransport(site.async_handler),
        on_progress=on_progress,
    )

    statuses = {r.check_id: r.status for r in report.results}
    assert statuses == {
        "performance.psi": CheckStatus.SKIPPED,
        "accessibility.forms": CheckStatus.SKIPPED,
        "best_practices.https": CheckStatus.RAN,
        "seo.has_title": CheckStatus.RAN,
        "agentic.crashes": CheckStatus.ERROR,
    }

    assert report.category(Category.SEO).score == 100
    assert report.category(Category.BEST_PRACTICES).score == 0
    assert report.category(Category.PERFORMANCE).score is None
    assert "PageSpeed API key" in report.category(Category.PERFORMANCE).note
    # Only SEO (25) and Best practices (20) were scored: (25*100 + 20*0) / 45 = 55.6 -> 56
    assert report.health_score == 56
    assert report.health_band is Band.ATTENTION

    percents = [p for p, _ in steps]
    assert percents == sorted(percents)
    assert steps[0] == (3, "Visiting your website")
    assert steps[-1] == (90, "Preparing your report")


async def test_collectors_add_capabilities(site: respx.Router) -> None:
    async def pagespeed_collector(ctx: AuditContext, fetcher: Fetcher, cfg: EngineConfig) -> None:
        ctx.capabilities.add(PAGESPEED)

    class UsesPageSpeed(Check, register=False):
        id = "performance.uses"
        category = Category.PERFORMANCE
        title = "Uses PSI"
        requires = frozenset({PAGESPEED})

        def run(self, ctx: AuditContext) -> list[Finding]:
            return [self.passed("Fast.", "Speed sells.")]

    report = await audit(site, registry_with(UsesPageSpeed), collectors=[pagespeed_collector])
    assert report.category(Category.PERFORMANCE).score == 100


async def test_failing_collector_does_not_stop_the_audit(site: respx.Router) -> None:
    async def broken(ctx: AuditContext, fetcher: Fetcher, cfg: EngineConfig) -> None:
        raise RuntimeError("PageSpeed is down")

    report = await audit(site, registry_with(HasTitle), collectors=[broken])
    assert report.health_score == 100


async def test_blocked_url_gives_friendly_error(router: respx.Router) -> None:
    router.get("https://shop.test/").respond(302, headers={"Location": "http://127.0.0.1/"})
    with pytest.raises(AuditError, match="private or internal network"):
        await audit(router, registry_with(HasTitle))


async def test_unreachable_site_gives_friendly_error(router: respx.Router) -> None:
    router.get("https://shop.test/").mock(side_effect=httpx.ConnectError("refused"))
    with pytest.raises(AuditError, match="couldn't reach your website"):
        await audit(router, registry_with(HasTitle))


async def test_error_status_homepage(router: respx.Router) -> None:
    router.get("https://shop.test/").respond(500)
    with pytest.raises(AuditError, match="HTTP 500"):
        await audit(router, registry_with(HasTitle))


async def test_non_html_homepage(router: respx.Router) -> None:
    router.get("https://shop.test/").respond(200, json={"api": True})
    with pytest.raises(AuditError, match="doesn't show a web page"):
        await audit(router, registry_with(HasTitle))


async def test_total_timeout(router: respx.Router) -> None:
    async def slow(request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(5)
        return httpx.Response(200)

    router.get("https://shop.test/").mock(side_effect=slow)
    with pytest.raises(AuditError, match="took too long"):
        await run_audit(
            "https://shop.test/",
            EngineConfig(total_timeout=0.1, retries=0),
            registry=registry_with(HasTitle),
            collectors=(),
            guard=NetGuard(fake_resolver),
            transport=httpx.MockTransport(router.async_handler),
        )


def test_check_returning_wrong_category_is_an_error() -> None:
    class Confused(Check, register=False):
        id = "seo.confused"
        category = Category.SEO
        title = "Confused"

        def run(self, ctx: AuditContext) -> list[Finding]:
            other = SeriousProblem()
            return [other.finding(Severity.FAIL, "x", "y", "z")]

    assert run_check(Confused, make_context()).status is CheckStatus.ERROR


async def test_skip_note_says_no_key_only_when_there_is_no_key(site: respx.Router) -> None:
    async def failing_pagespeed(ctx: AuditContext, fetcher: Fetcher, cfg: EngineConfig) -> None:
        raise RuntimeError("Google quota exceeded")

    async def run(key: str) -> str:
        report = await run_audit(
            "https://shop.test/",
            EngineConfig(retries=0, psi_api_key=key),
            registry=registry_with(NeedsPageSpeed),
            collectors=[failing_pagespeed],
            guard=NetGuard(fake_resolver),
            transport=httpx.MockTransport(site.async_handler),
        )
        return report.category(Category.PERFORMANCE).note

    assert "no PageSpeed API key" in await run("")
    assert "couldn't measure your site this time" in await run("a-real-key")


async def test_each_finished_data_source_moves_the_progress_bar(site: respx.Router) -> None:
    steps: list[tuple[int, str]] = []

    async def on_progress(percent: int, step: str) -> None:
        steps.append((percent, step))

    async def collect_probes(ctx: AuditContext, fetcher: Fetcher, cfg: EngineConfig) -> None:
        pass

    async def collect_pagespeed(ctx: AuditContext, fetcher: Fetcher, cfg: EngineConfig) -> None:
        await asyncio.sleep(0.05)  # the slow one finishes last

    await run_audit(
        "https://shop.test/",
        EngineConfig(retries=0),
        registry=registry_with(HasTitle),
        collectors=[collect_probes, collect_pagespeed],
        guard=NetGuard(fake_resolver),
        transport=httpx.MockTransport(site.async_handler),
        on_progress=on_progress,
    )

    messages = [step for _, step in steps]
    assert "Measuring speed with Google PageSpeed…" in messages  # what we're waiting for
    assert (45, "Measuring speed with Google PageSpeed…") in steps  # 1 of 2 finished
    assert (70, "Vital signs taken") in steps  # 2 of 2 finished
    assert [p for p, _ in steps] == sorted(p for p, _ in steps)  # never goes backwards


async def test_browser_note_explains_a_missing_browser_visit(site: respx.Router) -> None:
    from bizzcheckup.engine.context import RENDER

    async def blocked_browser(ctx: AuditContext, fetcher: Fetcher, cfg: EngineConfig) -> None:
        ctx.unavailable[RENDER] = "Your website's security firewall (Vercel) showed our browser…"

    report = await audit(site, registry_with(HasTitle), collectors=[blocked_browser])
    assert report.browser_note.startswith("Your website's security firewall (Vercel)")
    assert report.browser_note in report.notes
