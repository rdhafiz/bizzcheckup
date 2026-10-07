import httpx
import respx

from bizzcheckup.engine.collectors.probes import collect_probes
from bizzcheckup.engine.config import EngineConfig
from bizzcheckup.engine.context import PROBES
from bizzcheckup.engine.fetcher import Fetcher
from bizzcheckup.engine.types import RobotsInfo

from .factories import make_context, make_page


def mock_agent_and_llms_routes(router: respx.Router) -> None:
    """Routes every probe run needs: /llms.txt and the homepage for two User-Agents."""
    router.get("https://shop.test/llms.txt").respond(404)
    router.get("https://shop.test/").respond(200, html="<h1>Shop</h1>")


HOME = make_page(
    '<a href="/about">About</a> <a href="/gone">Old page</a> <a href="/flaky">Flaky</a>'
    ' <a href="/private/x">Private</a> <a href="https://other.test/">Partner</a>'
    ' <a href="/about#team">About team</a>'
)


async def test_probes_record_link_statuses_and_http_redirect(
    fetcher: Fetcher, router: respx.Router
) -> None:
    router.head("http://shop.test/").respond(301, headers={"Location": "https://shop.test/"})
    router.head("https://shop.test/").respond(200)
    router.head("https://shop.test/about").respond(200)
    router.head("https://shop.test/gone").respond(404)
    router.head("https://shop.test/flaky").mock(side_effect=httpx.ConnectError("down"))
    robots = RobotsInfo(
        url="https://shop.test/robots.txt", exists=True, text="User-agent: *\nDisallow: /private/\n"
    )
    ctx = make_context(HOME, robots=robots)
    mock_agent_and_llms_routes(router)

    await collect_probes(ctx, fetcher, EngineConfig())

    assert ctx.has(PROBES)
    assert ctx.probes.http_final_url == "https://shop.test/"
    assert ctx.probes.link_status == {
        "https://shop.test/": 200,  # the homepage itself (crawled)
        "https://shop.test/about": 200,
        "https://shop.test/gone": 404,
        "https://shop.test/flaky": 0,  # unreachable
    }
    assert "https://other.test/" not in ctx.probes.link_status  # other sites aren't checked
    assert "https://shop.test/private/x" not in ctx.probes.link_status  # robots.txt says no
    assert ctx.probes.link_sources["https://shop.test/gone"] == ["https://shop.test/"]


async def test_head_not_allowed_falls_back_to_get(fetcher: Fetcher, router: respx.Router) -> None:
    router.head("https://shop.test/page").respond(405)
    router.get("https://shop.test/page").respond(200)
    assert await fetcher.status("https://shop.test/page") == 200


async def test_http_version_unreachable_is_recorded(fetcher: Fetcher, router: respx.Router) -> None:
    router.head("http://shop.test/").mock(side_effect=httpx.ConnectError("port 80 closed"))
    ctx = make_context(make_page("<p>No links</p>"))
    mock_agent_and_llms_routes(router)

    await collect_probes(ctx, fetcher, EngineConfig())

    assert ctx.probes.http_final_url is None
    assert ctx.probes.http_error


async def test_link_check_limit(fetcher: Fetcher, router: respx.Router) -> None:
    links = "".join(f'<a href="/p{i}">p</a>' for i in range(10))
    router.head("http://shop.test/").respond(301, headers={"Location": "https://shop.test/"})
    router.head("https://shop.test/").respond(200)
    route = router.head(url__regex=r"https://shop\.test/p\d+").respond(200)
    ctx = make_context(make_page(links))
    mock_agent_and_llms_routes(router)

    await collect_probes(ctx, fetcher, EngineConfig(max_link_checks=3))

    assert route.call_count == 3


async def test_llms_txt_and_agent_probes(fetcher: Fetcher, router: respx.Router) -> None:
    router.head("http://shop.test/").respond(301, headers={"Location": "https://shop.test/"})
    router.head("https://shop.test/").respond(200)
    router.get("https://shop.test/llms.txt").respond(200, text="# Sweet Moments\n> Bakery")

    def by_user_agent(request: httpx.Request) -> httpx.Response:
        if "GPTBot" in request.headers["user-agent"]:
            return httpx.Response(403, html="<title>Just a moment...</title>")
        return httpx.Response(200, html="<h1>Welcome to the shop</h1>" + "x" * 500)

    router.get("https://shop.test/").mock(side_effect=by_user_agent)
    ctx = make_context(make_page("<p>No links</p>"))

    await collect_probes(ctx, fetcher, EngineConfig())

    assert ctx.probes.llms_txt_status == 200
    assert ctx.probes.llms_txt_text.startswith("# Sweet Moments")
    assert ctx.probes.as_ai_agent is not None
    assert ctx.probes.as_browser is not None
    assert (ctx.probes.as_ai_agent.status_code, ctx.probes.as_ai_agent.challenge) == (403, True)
    assert (ctx.probes.as_browser.status_code, ctx.probes.as_browser.challenge) == (200, False)


async def test_html_llms_txt_soft_404_is_ignored(fetcher: Fetcher, router: respx.Router) -> None:
    router.head("http://shop.test/").respond(301, headers={"Location": "https://shop.test/"})
    router.head("https://shop.test/").respond(200)
    router.get("https://shop.test/llms.txt").respond(200, html="<html>Home page</html>")
    router.get("https://shop.test/").respond(200, html="<h1>Shop</h1>")
    ctx = make_context(make_page("<p>No links</p>"))

    await collect_probes(ctx, fetcher, EngineConfig())

    assert ctx.probes.llms_txt_status == 200
    assert ctx.probes.llms_txt_text == ""
