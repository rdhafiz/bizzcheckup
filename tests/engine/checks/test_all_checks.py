"""Rules every check must follow (acceptance checklist), tested across all the checks."""

import pytest

from bizzcheckup.engine.checks.base import Check
from bizzcheckup.engine.context import PAGESPEED, PROBES, RENDER, AuditContext
from bizzcheckup.engine.registry import load_builtin_checks
from bizzcheckup.engine.types import (
    AgentProbe,
    AxeRule,
    Cookie,
    PageSpeedResult,
    RenderResult,
    RobotsInfo,
    Severity,
    SpeedTest,
)

from ..factories import fixture_html, make_context, make_page

CHECKS = load_builtin_checks().all()
HOME = "https://shop.test/"


def sick_site() -> AuditContext:
    """A site with as many problems as possible, with every data source available."""
    page = make_page(fixture_html("neglected"), headers={"content-type": "text/html"})
    ctx = make_context(
        page,
        robots=RobotsInfo(
            url=f"{HOME}robots.txt", exists=True, text="User-agent: *\nDisallow: /\n"
        ),
        capabilities={PROBES, RENDER, PAGESPEED},
    )
    ctx.probes.http_final_url = "http://shop.test/"
    ctx.probes.link_status = {HOME: 200, f"{HOME}old-offer": 404}
    ctx.probes.link_sources = {f"{HOME}old-offer": [HOME]}
    ctx.probes.as_ai_agent = AgentProbe(status_code=403, text_length=100)
    ctx.probes.as_browser = AgentProbe(status_code=200, text_length=9000)
    ctx.render = RenderResult(
        url=HOME,
        html=fixture_html("neglected"),
        text_length=5000,
        console_errors=["TypeError: x is undefined"],
        cookies=[Cookie(name="_fbp", domain="facebook.com", third_party=True)],
        libraries={"jQuery": "1.12.4"},
        axe_violations=[
            AxeRule(
                id="color-contrast",
                impact="serious",
                help="Contrast",
                help_url="https://x",
                nodes=3,
            )
        ],
        axe_passes=["document-title"],
    )
    slow = SpeedTest(
        strategy="mobile", score=0.3, lcp_ms=6000, cls=0.4, tbt_ms=900, fcp_ms=3500,
        total_bytes=6_000_000, render_blocking=["https://shop.test/a.css"],
        offscreen_images=["https://shop.test/b.jpg"],
    )  # fmt: skip
    ctx.pagespeed = PageSpeedResult(
        mobile=slow, desktop=slow.model_copy(update={"strategy": "desktop"})
    )
    return ctx


def test_check_count_across_five_categories() -> None:
    assert len(CHECKS) == 54
    assert len({check.category for check in CHECKS}) == 5


@pytest.mark.parametrize("check", CHECKS, ids=lambda c: c.id)
def test_every_finding_is_complete(check: type[Check]) -> None:
    for finding in check().run(sick_site()):
        assert finding.check_id == check.id
        assert finding.category is check.category
        assert finding.message.strip()
        assert finding.why_it_matters.strip()
        assert finding.how_to_fix.strip()
        assert finding.effort and finding.impact  # noqa: PT018
        if finding.severity in (Severity.FAIL, Severity.WARN):
            assert finding.affected_urls, f"{check.id}: problem without affected URLs"


@pytest.mark.parametrize("check", CHECKS, ids=lambda c: c.id)
def test_every_check_scores_between_0_and_1(check: type[Check]) -> None:
    instance = check()
    findings = instance.run(sick_site())
    if findings:
        assert 0.0 <= instance.score(findings) <= 1.0
