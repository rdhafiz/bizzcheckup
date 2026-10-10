"""Pictures of where each problem is: the locators checks give, and the shots step."""

import threading
from collections.abc import Iterator
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest
from selectolax.lexbor import LexborHTMLParser

from bizzcheckup.engine.checks import accessibility, best_practices, seo
from bizzcheckup.engine.checks._helpers import css_path, describe, shot_of
from bizzcheckup.engine.checks.base import MAX_SHOTS_PER_FINDING
from bizzcheckup.engine.checks.mobile import quoted_text
from bizzcheckup.engine.collectors import shots as shots_step
from bizzcheckup.engine.config import EngineConfig
from bizzcheckup.engine.context import PROBES
from bizzcheckup.engine.types import CheckResult, CheckStatus, Severity, Shot

from .factories import fixture_html, make_context, make_finding, make_page

HOME = "https://shop.test/"

# --- the locators checks give ----------------------------------------------------------


def test_css_path_and_description() -> None:
    tree = LexborHTMLParser(
        "<html><body><main><div><p>Hi</p><img src='/a.jpg'></div>"
        "<div id='gallery'><img src='/b.jpg'><img src='/uploads/c.jpg'></div></main></body></html>"
    )
    first, _, third = tree.css("img")
    assert css_path(first) == "body > main > div:nth-of-type(1) > img"
    assert css_path(third) == "#gallery > img:nth-of-type(2)"  # stops at a usable id
    assert describe(third) == '<img src="c.jpg">'
    shot = shot_of(third, HOME)
    assert (shot.match_tag, shot.match_attr, shot.match_value) == ("img", "src", "/uploads/c.jpg")


def test_text_is_kept_to_find_the_element_again() -> None:
    link = LexborHTMLParser("<nav><a href='/cart'>  Your   cart </a></nav>").css_first("a")
    assert link is not None
    assert shot_of(link, HOME).match_text == "Your cart"
    assert quoted_text('a.nav "Home"') == "Home"
    assert quoted_text("button.close") == ""


def neglected() -> object:
    ctx = make_context(make_page(fixture_html("neglected")), capabilities={PROBES})
    ctx.probes.link_status = {HOME: 200, f"{HOME}old-offer": 404}
    ctx.probes.link_sources = {f"{HOME}old-offer": [HOME]}
    return ctx


@pytest.mark.parametrize(
    ("check", "labels"),
    [
        (accessibility.ImageAlt, ['<img src="banner.jpg">']),
        (seo.SingleH1, ['<h1> "Welcome"', '<h1> "Our products"']),
        (accessibility.HeadingOrder, ['<h4> "Fine print"']),
        (seo.BrokenLinks, ['<a> "Old offer"']),
        (accessibility.FormLabels, ['<input name="email">']),
    ],
    ids=lambda value: getattr(value, "id", ""),
)
def test_checks_point_at_the_elements(check: type, labels: list[str]) -> None:
    findings = check().run(neglected())
    shots = [shot for finding in findings for shot in finding.shots]
    assert [shot.label for shot in shots] == labels
    assert all(shot.page == HOME and shot.device == "desktop" for shot in shots)


def test_insecure_images_are_pointed_at() -> None:
    html = "<html><body><img src='http://shop.test/old.jpg'></body></html>"
    [finding] = best_practices.MixedContent().run(make_context(make_page(html)))
    assert [shot.label for shot in finding.shots] == ['<img src="old.jpg">']


def test_a_finding_keeps_at_most_three_shots() -> None:
    body = "".join(f"<img src='/{n}.jpg'>" for n in range(6))
    [finding] = accessibility.ImageAlt().run(make_context(make_page(f"<body>{body}</body>")))
    assert len(finding.shots) == MAX_SHOTS_PER_FINDING == 3


# --- the shots step -----------------------------------------------------------------------


def result(*findings: object) -> CheckResult:
    return CheckResult(
        check_id="seo.example",
        category="seo",
        title="Example",
        weight=5,
        status=CheckStatus.RAN,
        score=0.5,
        findings=list(findings),
    )


def shot(name: str) -> Shot:
    return Shot(page=HOME, selector=f"#{name}", label=name)


def with_shots(severity: Severity, *names: str) -> object:
    return make_finding(severity).model_copy(update={"shots": [shot(n) for n in names]})


def test_the_most_serious_problems_are_photographed_first() -> None:
    results = [
        result(with_shots(Severity.INFO, "note"), with_shots(Severity.WARN, "warn1", "warn2")),
        result(with_shots(Severity.FAIL, "fail"), with_shots(Severity.PASS, "fine")),
    ]
    chosen = shots_step._choose(results, limit=3)
    assert [s.label for _, s in chosen] == ["fail", "warn1", "warn2"]  # never the passed one


def test_pictures_are_attached_to_their_shots() -> None:
    results = [result(with_shots(Severity.WARN, "a", "b"))]
    updated = shots_step._with_images(results, {(0, 0, 1): "shot-1"})
    assert [s.image for s in updated[0].findings[0].shots] == ["", "shot-1"]


async def test_nothing_to_photograph_does_not_start_a_browser() -> None:
    results = [result(make_finding(Severity.WARN))]
    assert await shots_step.take_shots(results, guard=None, config=EngineConfig()) == (  # type: ignore[arg-type]
        results,
        {},
    )


# --- in a real browser --------------------------------------------------------------------

PAGE = b"""<!doctype html><html><body style="margin:0">
<nav><a href="/">Home</a><a href="/services">Services</a></nav>
<p style="height:900px">Long text</p>
<img src="/missing.jpg" alt="" width="200" height="100">
<button style="display:none">Hidden</button>
</body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args: object) -> None:
        pass

    def do_GET(self) -> None:  # the method name is required by http.server
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(PAGE)


@pytest.fixture(scope="module")
def server_port() -> Iterator[int]:
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield server.server_port
    server.shutdown()


@pytest.mark.browser
async def test_shots_outline_the_right_elements(server_port: int) -> None:
    from .test_render import LocalTestGuard

    url = f"http://127.0.0.1:{server_port}/"
    shots = [
        Shot(
            page=url,
            selector="body > img",
            match_tag="img",
            match_attr="src",
            match_value="/missing.jpg",
            label="image",
        ),
        # The path points at "Home", but the text says "Services": the text wins.
        Shot(page=url, selector="nav > a:nth-of-type(1)", match_text="Services", label="link"),
        Shot(page=url, selector="button", label="hidden button"),  # can't be seen: no picture
        Shot(page=url, selector="nav > a", match_text="Services", label="phone", device="mobile"),
    ]
    finding = make_finding(Severity.WARN).model_copy(update={"shots": shots})
    try:
        results, images = await shots_step.take_shots(
            [result(finding)], LocalTestGuard(server_port), EngineConfig(render_timeout=20)
        )
    except Exception as error:
        if "Executable doesn't exist" in str(error):
            pytest.skip("Chromium isn't installed: python -m playwright install chromium")
        raise
    taken = [s.image for s in results[0].findings[0].shots]
    assert taken == ["shot-1", "shot-2", "", "shot-3"]
    assert all(image.data[:3] == bytes([0xFF, 0xD8, 0xFF]) for image in images.values())
