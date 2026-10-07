"""Agentic browsing checks, tested against local HTML and fake probe results (no network)."""

import pytest

from bizzcheckup.engine.checks import agentic
from bizzcheckup.engine.checks.base import Check
from bizzcheckup.engine.context import PROBES, RENDER, AuditContext
from bizzcheckup.engine.types import AgentProbe, Level, RenderResult, RobotsInfo, Severity

from ..factories import fixture_html, make_context, make_page

HOME = "https://shop.test/"


def severities(check: type[Check], ctx: AuditContext) -> list[Severity]:
    return [finding.severity for finding in check().run(ctx)]


def robots(text: str) -> RobotsInfo:
    return RobotsInfo(url=f"{HOME}robots.txt", exists=True, text=text)


def probe_context(**probes: object) -> AuditContext:
    ctx = make_context(make_page(fixture_html("healthy")), capabilities={PROBES})
    for name, value in probes.items():
        setattr(ctx.probes, name, value)
    return ctx


# --- llms.txt ----------------------------------------------------------------


def test_llms_txt() -> None:
    good = probe_context(llms_txt_text="# Sweet Moments\n> Handmade cakes in Dhaka")
    no_heading = probe_context(llms_txt_text="Sweet Moments bakery")
    assert severities(agentic.LlmsTxt, good) == [Severity.PASS]
    assert severities(agentic.LlmsTxt, no_heading) == [Severity.PASS, Severity.INFO]
    assert severities(agentic.LlmsTxt, probe_context()) == [Severity.WARN]


# --- AI crawlers in robots.txt -----------------------------------------------


def test_ai_crawlers_allowed_without_robots() -> None:
    assert severities(agentic.AiCrawlers, make_context()) == [Severity.PASS]


def test_blocking_ai_search_bots_fails() -> None:
    ctx = make_context(robots=robots("User-agent: OAI-SearchBot\nDisallow: /\n"))
    finding = agentic.AiCrawlers().run(ctx)[0]
    assert finding.severity is Severity.FAIL
    assert finding.impact is Level.HIGH
    assert "OAI-SearchBot" in finding.message


def test_blocking_only_training_bots_is_info() -> None:
    text = "User-agent: GPTBot\nDisallow: /\n\nUser-agent: ClaudeBot\nDisallow: /\n"
    finding = agentic.AiCrawlers().run(make_context(robots=robots(text)))[0]
    assert finding.severity is Severity.INFO
    assert "GPTBot, ClaudeBot" in finding.message


def test_blocking_everyone_reports_both() -> None:
    ctx = make_context(robots=robots("User-agent: *\nDisallow: /\n"))
    assert severities(agentic.AiCrawlers, ctx) == [Severity.FAIL, Severity.INFO]


# --- firewall / CDN blocking -------------------------------------------------

OK = AgentProbe(status_code=200, text_length=10_000)


@pytest.mark.parametrize(
    ("ai", "browser", "expected"),
    [
        (OK, OK, Severity.PASS),
        (AgentProbe(status_code=403, text_length=500), OK, Severity.FAIL),
        (AgentProbe(status_code=200, text_length=800, challenge=True), OK, Severity.FAIL),
        (AgentProbe(), OK, Severity.FAIL),  # no answer at all
        (AgentProbe(status_code=403), AgentProbe(status_code=403), Severity.WARN),
        (AgentProbe(status_code=200, text_length=2_000), OK, Severity.WARN),  # much shorter page
    ],
)
def test_bot_blocking(ai: AgentProbe, browser: AgentProbe, expected: Severity) -> None:
    ctx = probe_context(as_ai_agent=ai, as_browser=browser)
    assert severities(agentic.BotBlocking, ctx) == [expected]


def test_challenge_message() -> None:
    ai = AgentProbe(status_code=200, text_length=800, challenge=True)
    finding = agentic.BotBlocking().run(probe_context(as_ai_agent=ai, as_browser=OK))[0]
    assert "prove you're human" in finding.message


# --- structure, structured data, names ----------------------------------------


def test_structured_data_present() -> None:
    assert severities(
        agentic.StructuredDataPresent, make_context(make_page(fixture_html("healthy")))
    ) == [Severity.PASS]
    assert severities(agentic.StructuredDataPresent, make_context()) == [Severity.WARN]


def test_landmarks() -> None:
    check = agentic.SemanticLandmarks()
    assert severities(
        agentic.SemanticLandmarks, make_context(make_page(fixture_html("healthy")))
    ) == [Severity.PASS]
    findings = check.run(make_context(make_page('<div role="main">x</div><nav>menu</nav>')))
    assert findings[0].message.endswith("<header>, <footer>.")
    assert findings[0].impact is Level.LOW  # main is present (as role="main")
    assert check.score(findings) == 0.5


def test_named_controls() -> None:
    assert severities(
        agentic.AgentReadableControls, make_context(make_page(fixture_html("healthy")))
    ) == [Severity.PASS]
    neglected = make_context(make_page(fixture_html("neglected")))
    assert severities(agentic.AgentReadableControls, neglected) == [Severity.WARN]


# --- content without JavaScript -------------------------------------------------


def js_context(raw_html: str, rendered_text_length: int) -> AuditContext:
    ctx = make_context(make_page(raw_html), capabilities={RENDER})
    ctx.render = RenderResult(url=HOME, html=raw_html, text_length=rendered_text_length)
    return ctx


def test_server_rendered_page_passes() -> None:
    text = "Handmade cakes. " * 50  # 800 characters
    assert severities(agentic.ContentWithoutJs, js_context(f"<p>{text}</p>", 800)) == [
        Severity.PASS
    ]


def test_javascript_only_page_fails() -> None:
    raw = (
        "<div id='app'></div><script>render('lots of text')</script><noscript>Enable JS</noscript>"
    )
    finding = agentic.ContentWithoutJs().run(js_context(raw, 5000))[0]
    assert finding.severity is Severity.FAIL
    assert "only 0%" in finding.message


def test_half_rendered_page_warns() -> None:
    text = "x" * 400
    assert severities(agentic.ContentWithoutJs, js_context(f"<p>{text}</p>", 1000)) == [
        Severity.WARN
    ]


def test_tiny_pages_are_not_judged() -> None:
    assert agentic.ContentWithoutJs().run(js_context("<p>Hi</p>", 50)) == []


def test_visible_text_ignores_scripts_and_styles() -> None:
    html = "<style>body{}</style><script>var a=1</script><p>Hello world</p>"
    assert agentic.visible_text_length(html) == len("Hello world")
