"""Performance checks and PageSpeed parsing, using a saved PageSpeed answer (no network)."""

import json
from pathlib import Path

import httpx
import pytest
import respx

from bizzcheckup.engine.checks import performance as perf
from bizzcheckup.engine.checks.base import Check
from bizzcheckup.engine.collectors.pagespeed import collect_pagespeed, parse_speed_test
from bizzcheckup.engine.config import EngineConfig
from bizzcheckup.engine.context import PAGESPEED, AuditContext
from bizzcheckup.engine.fetcher import Fetcher
from bizzcheckup.engine.netguard import NetGuard
from bizzcheckup.engine.types import FieldData, Level, PageSpeedResult, Severity, SpeedTest

from ..conftest import fake_resolver
from ..factories import fixture_html, make_context, make_page

PSI_FIXTURE = Path(__file__).resolve().parents[2] / "fixtures" / "pagespeed" / "mobile.json"


def psi_answer() -> dict[str, object]:
    data: dict[str, object] = json.loads(PSI_FIXTURE.read_text(encoding="utf-8"))
    return data


def severities(check: type[Check], ctx: AuditContext) -> list[Severity]:
    return [finding.severity for finding in check().run(ctx)]


def speed_context(mobile: SpeedTest | None, desktop: SpeedTest | None = None) -> AuditContext:
    ctx = make_context(make_page(fixture_html("healthy")), capabilities={PAGESPEED})
    ctx.pagespeed = PageSpeedResult(mobile=mobile, desktop=desktop)
    return ctx


FAST = SpeedTest(
    strategy="mobile",
    score=0.97,
    lcp_ms=1400,
    cls=0.02,
    tbt_ms=50,
    fcp_ms=900,
    total_bytes=900_000,
)


# --- parsing Google's answer -------------------------------------------------


def test_parse_speed_test() -> None:
    test = parse_speed_test(psi_answer(), "mobile")

    assert test.score == 0.42
    assert test.lcp_ms == pytest.approx(5200.4)
    assert test.cls == pytest.approx(0.31)
    assert test.total_bytes == 5452595
    assert test.render_blocking == [
        "https://shop.test/css/theme.css",
        "https://shop.test/js/jquery.js",
    ]
    assert test.render_blocking_savings_ms == 1350
    assert len(test.offscreen_images) == 2
    assert test.unsized_images == ["https://shop.test/img/logo.png"]
    assert test.field == FieldData(lcp_ms=3100, cls=0.05, inp_ms=650, fcp_ms=1500)


def test_parse_handles_missing_field_data() -> None:
    data = psi_answer()
    del data["loadingExperience"]
    assert parse_speed_test(data, "desktop").field is None


async def test_collector_calls_api_with_key_in_header(router: respx.Router) -> None:
    route = router.get(url__startswith="https://www.googleapis.com/pagespeedonline/v5/runPagespeed")
    route.mock(return_value=httpx.Response(200, json=psi_answer()))

    config = EngineConfig(psi_api_key="secret-test-key")
    ctx = make_context()
    google_dns = {"www.googleapis.com": ["142.250.74.10"]}

    async def resolver(host: str) -> list[str]:
        return google_dns.get(host) or await fake_resolver(host)

    async with Fetcher(config, NetGuard(resolver), httpx.MockTransport(router.async_handler)) as f:
        await collect_pagespeed(ctx, f, config)

    assert ctx.has(PAGESPEED)
    assert ctx.pagespeed is not None
    assert ctx.pagespeed.mobile is not None
    assert ctx.pagespeed.desktop is not None
    assert route.call_count == 2
    request = route.calls.last.request
    assert request.headers["x-goog-api-key"] == "secret-test-key"
    assert "secret-test-key" not in str(request.url)  # never in the URL (logs!)


async def test_collector_does_nothing_without_key() -> None:
    ctx = make_context()
    config = EngineConfig(psi_api_key="")
    await collect_pagespeed(ctx, Fetcher(config), config)
    assert not ctx.has(PAGESPEED)


# --- speed scores ------------------------------------------------------------


@pytest.mark.parametrize(
    ("score", "expected", "impact"),
    [
        (0.95, Severity.PASS, Level.LOW),
        (0.7, Severity.WARN, Level.MEDIUM),
        (0.3, Severity.FAIL, Level.HIGH),
    ],
)
def test_mobile_speed_bands(score: float, expected: Severity, impact: Level) -> None:
    check = perf.MobileSpeed()
    findings = check.run(speed_context(FAST.model_copy(update={"score": score})))
    assert findings[0].severity is expected
    assert findings[0].impact is impact
    assert check.score(findings) == score
    assert f"{round(score * 100)} out of 100" in findings[0].message


def test_desktop_speed_not_applicable_when_only_mobile_ran() -> None:
    assert perf.DesktopSpeed().run(speed_context(FAST)) == []


# --- Core Web Vitals ---------------------------------------------------------


def test_vitals_prefer_real_visitor_data() -> None:
    test = parse_speed_test(psi_answer(), "mobile")  # field: LCP 3.1s, CLS .05, INP 650, FCP 1.5
    check = perf.CoreWebVitals()
    findings = check.run(speed_context(test))

    assert [(f.message.split(" (")[0], f.severity) for f in findings] == [
        ("Your main content takes 3.1s to appear", Severity.WARN),
        ("Your page takes 650 ms to react to taps and clicks", Severity.FAIL),
    ]
    assert "real visitors" in findings[0].message
    assert check.score(findings) == pytest.approx((0.5 + 1 + 0 + 1) / 4)


def test_vitals_fall_back_to_lab_data() -> None:
    test = parse_speed_test(psi_answer(), "mobile").model_copy(update={"field": None})
    findings = perf.CoreWebVitals().run(speed_context(test))
    names = [f.message.split("(")[-1].split(",")[0] for f in findings]
    assert names == ["LCP", "CLS", "TBT", "FCP"]  # lab LCP 5.2s, CLS .31, TBT 820, FCP 2.4
    assert "lab test" in findings[0].message


def test_vitals_all_good() -> None:
    assert severities(perf.CoreWebVitals, speed_context(FAST)) == [Severity.PASS]


# --- page weight -------------------------------------------------------------


@pytest.mark.parametrize(
    ("size", "expected"),
    [
        (1_500_000, Severity.PASS),
        (3 * 1024 * 1024, Severity.WARN),
        (5 * 1024 * 1024, Severity.FAIL),
    ],
)
def test_page_weight(size: int, expected: Severity) -> None:
    ctx = speed_context(FAST.model_copy(update={"total_bytes": size}))
    assert severities(perf.PageWeight, ctx) == [expected]


# --- checks that also work without PageSpeed -------------------------------


def test_image_dimensions() -> None:
    html = '<img src="a.jpg" width="10" height="10"><img src="b.jpg" width="10"><img src="data:x">'
    check = perf.ImageDimensions()
    findings = check.run(make_context(make_page(html)))
    assert findings[0].message == "1 of your 2 images don't declare their width and height."
    assert check.score(findings) == 0.75


def test_lazy_images_static_fallback() -> None:
    eager = make_page("".join(f'<img src="{i}.jpg">' for i in range(5)))
    lazy = make_page("".join(f'<img src="{i}.jpg" loading="lazy">' for i in range(5)))
    few = make_page('<img src="a.jpg">')
    assert severities(perf.LazyImages, make_context(eager)) == [Severity.WARN]
    assert severities(perf.LazyImages, make_context(lazy)) == [Severity.PASS]
    assert perf.LazyImages().run(make_context(few)) == []


def test_lazy_images_uses_pagespeed_when_available() -> None:
    test = parse_speed_test(psi_answer(), "mobile")
    finding = perf.LazyImages().run(speed_context(test))[0]
    assert finding.message.startswith("2 images below the first screen")


def test_render_blocking_from_pagespeed() -> None:
    finding = perf.RenderBlocking().run(speed_context(parse_speed_test(psi_answer(), "mobile")))[0]
    assert finding.severity is Severity.WARN
    assert "by about 1.4s" in finding.message
    assert finding.impact is Level.MEDIUM


@pytest.mark.parametrize(
    ("head", "expected"),
    [
        ('<script src="a.js"></script>', Severity.WARN),
        ('<script src="a.js" defer></script><script src="b.js" async></script>', Severity.PASS),
        ('<script type="module" src="a.js"></script>', Severity.PASS),
    ],
)
def test_render_blocking_static_fallback(head: str, expected: Severity) -> None:
    page = make_page(f"<html><head>{head}</head><body></body></html>")
    assert severities(perf.RenderBlocking, make_context(page)) == [expected]
