import httpx
import pytest
import respx

from bizzcheckup.engine.config import USER_AGENT, EngineConfig
from bizzcheckup.engine.fetcher import Fetcher, FetchError
from bizzcheckup.engine.netguard import BlockedURLError


async def test_fetch_returns_page_with_our_user_agent(
    fetcher: Fetcher, router: respx.Router
) -> None:
    route = router.get("https://shop.test/").respond(
        200, html="<h1>Hi</h1>", headers={"X-Thing": "1"}
    )

    page = await fetcher.get("https://shop.test/")

    assert page.status_code == 200
    assert page.text == "<h1>Hi</h1>"
    assert page.is_html
    assert page.headers["x-thing"] == "1"
    assert route.calls.last.request.headers["user-agent"] == USER_AGENT
    assert USER_AGENT.endswith("BizzCheckup/0.1 (+https://ridwanulhafiz.me)")


async def test_sends_browser_like_accept_headers(fetcher: Fetcher, router: respx.Router) -> None:
    """Some CDNs (e.g. Hostinger's) answer 403 to requests without these headers."""
    route = router.get("https://shop.test/").respond(200)
    await fetcher.get("https://shop.test/")
    headers = route.calls.last.request.headers
    assert headers["accept"].startswith("text/html")
    assert headers["accept-language"].startswith("en")
    assert headers["user-agent"] == USER_AGENT  # still honest about who we are


async def test_custom_user_agent(fetcher: Fetcher, router: respx.Router) -> None:
    route = router.get("https://shop.test/").respond(200)
    await fetcher.get("https://shop.test/", user_agent="GPTBot/1.0")
    assert route.calls.last.request.headers["user-agent"] == "GPTBot/1.0"


async def test_follows_redirects_and_records_chain(fetcher: Fetcher, router: respx.Router) -> None:
    router.get("http://shop.test/").respond(301, headers={"Location": "https://shop.test/"})
    router.get("https://shop.test/").respond(302, headers={"Location": "/home"})
    router.get("https://shop.test/home").respond(200, text="home")

    page = await fetcher.get("http://shop.test/")

    assert page.final_url == "https://shop.test/home"
    assert page.redirect_chain == ["http://shop.test/", "https://shop.test/"]
    assert page.text == "home"


async def test_redirect_to_private_address_is_blocked(
    fetcher: Fetcher, router: respx.Router
) -> None:
    router.get("https://shop.test/").respond(
        302, headers={"Location": "http://169.254.169.254/latest/meta-data/"}
    )
    with pytest.raises(BlockedURLError):
        await fetcher.get("https://shop.test/")


async def test_redirect_to_host_resolving_privately_is_blocked(
    fetcher: Fetcher, router: respx.Router
) -> None:
    router.get("https://shop.test/").respond(302, headers={"Location": "https://evil.test/"})
    with pytest.raises(BlockedURLError):
        await fetcher.get("https://shop.test/")


async def test_too_many_redirects(fetcher: Fetcher, router: respx.Router) -> None:
    router.get("https://shop.test/loop").respond(302, headers={"Location": "/loop"})
    with pytest.raises(FetchError, match="Too many redirects"):
        await fetcher.get("https://shop.test/loop")


async def test_large_body_is_truncated(fetcher: Fetcher, router: respx.Router) -> None:
    router.get("https://shop.test/big").respond(200, content=b"x" * 5000)

    page = await fetcher.get("https://shop.test/big")

    assert page.truncated
    assert page.size_bytes == 1000  # max_page_bytes in the test config


async def test_retries_temporary_errors(fetcher: Fetcher, router: respx.Router) -> None:
    route = router.get("https://shop.test/").mock(
        side_effect=[httpx.Response(503), httpx.Response(200, text="ok")]
    )

    page = await fetcher.get("https://shop.test/")

    assert page.text == "ok"
    assert route.call_count == 2


async def test_gives_up_after_retries_on_connection_errors(
    fetcher: Fetcher, router: respx.Router
) -> None:
    route = router.get("https://shop.test/").mock(side_effect=httpx.ConnectTimeout("slow"))

    with pytest.raises(FetchError):
        await fetcher.get("https://shop.test/")
    assert route.call_count == 2  # first try + 1 retry


async def test_returns_error_status_after_retries(fetcher: Fetcher, router: respx.Router) -> None:
    router.get("https://shop.test/").respond(503)
    page = await fetcher.get("https://shop.test/")
    assert page.status_code == 503


async def test_must_be_used_inside_async_with(config: EngineConfig) -> None:
    with pytest.raises(RuntimeError):
        await Fetcher(config).get("https://shop.test/")
