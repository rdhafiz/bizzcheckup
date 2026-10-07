import httpx
import respx

from bizzcheckup.engine.collectors.probes import collect_probes
from bizzcheckup.engine.config import EngineConfig
from bizzcheckup.engine.context import PROBES
from bizzcheckup.engine.fetcher import Fetcher
from bizzcheckup.engine.types import RobotsInfo

from .factories import make_context, make_page

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

    await collect_probes(ctx, fetcher, EngineConfig())

    assert ctx.probes.http_final_url is None
    assert ctx.probes.http_error


async def test_link_check_limit(fetcher: Fetcher, router: respx.Router) -> None:
    links = "".join(f'<a href="/p{i}">p</a>' for i in range(10))
    router.head("http://shop.test/").respond(301, headers={"Location": "https://shop.test/"})
    router.head("https://shop.test/").respond(200)
    route = router.head(url__regex=r"https://shop\.test/p\d+").respond(200)
    ctx = make_context(make_page(links))

    await collect_probes(ctx, fetcher, EngineConfig(max_link_checks=3))

    assert route.call_count == 3
