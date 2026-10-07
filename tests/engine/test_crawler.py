import httpx
import pytest
import respx

from bizzcheckup.engine.config import EngineConfig
from bizzcheckup.engine.crawler import crawl, parse_sitemap
from bizzcheckup.engine.fetcher import Fetcher
from bizzcheckup.engine.netguard import NetGuard

from .conftest import fake_resolver


def html(body: str) -> httpx.Response:
    return httpx.Response(200, html=f"<!doctype html><html><body>{body}</body></html>")


ROBOTS = """User-agent: *
Disallow: /private/

Sitemap: https://shop.test/sitemap.xml
"""

SITEMAP = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://shop.test/</loc></url>
  <url><loc>https://shop.test/about</loc></url>
  <url><loc>https://shop.test/private/secret</loc></url>
  <url><loc>https://other.test/elsewhere</loc></url>
</urlset>
"""


async def test_crawl_uses_robots_sitemap_and_links(fetcher: Fetcher, router: respx.Router) -> None:
    router.get("http://shop.test/").respond(301, headers={"Location": "https://shop.test/"})
    router.get("https://shop.test/").mock(
        return_value=html(
            '<a href="/contact">Contact</a> <a href="/brochure.pdf">PDF</a>'
            ' <a href="https://other.test/">Partner</a> <a href="mailto:x@shop.test">Mail</a>'
        )
    )
    router.get("https://shop.test/robots.txt").respond(200, text=ROBOTS)
    router.get("https://shop.test/sitemap.xml").respond(200, text=SITEMAP)
    router.get("https://shop.test/about").mock(return_value=html("About us"))
    router.get("https://shop.test/contact").mock(return_value=html("Contact us"))

    result = await crawl(fetcher, "http://shop.test/")

    assert result.final_url == "https://shop.test/"
    assert [p.final_url for p in result.pages] == [
        "https://shop.test/",
        "https://shop.test/about",
        "https://shop.test/contact",
    ]
    assert result.robots.exists
    assert result.sitemap.found
    assert result.skipped_by_robots == ["https://shop.test/private/secret"]


async def test_crawl_respects_max_pages(router: respx.Router) -> None:
    links = "".join(f'<a href="/p{i}">{i}</a>' for i in range(20))
    router.get("https://shop.test/").mock(return_value=html(links))
    router.get("https://shop.test/robots.txt").respond(404)
    router.get("https://shop.test/sitemap.xml").respond(404)
    router.get(url__regex=r"https://shop\.test/p\d+").mock(return_value=html("page"))

    config = EngineConfig(max_pages=4)
    transport = httpx.MockTransport(router.async_handler)
    async with Fetcher(config, NetGuard(fake_resolver), transport, retry_backoff=0) as f:
        result = await crawl(f, "https://shop.test/")

    assert len(result.pages) == 4
    assert not result.robots.exists
    assert not result.sitemap.found


async def test_soft_404_robots_is_treated_as_missing(
    fetcher: Fetcher, router: respx.Router
) -> None:
    router.get("https://shop.test/").mock(return_value=html("home"))
    router.get("https://shop.test/robots.txt").mock(return_value=html("Not here, but 200"))
    router.get("https://shop.test/sitemap.xml").respond(404)

    result = await crawl(fetcher, "https://shop.test/")

    assert not result.robots.exists


async def test_failed_extra_page_is_recorded_not_fatal(
    fetcher: Fetcher, router: respx.Router
) -> None:
    router.get("https://shop.test/").mock(return_value=html('<a href="/broken">x</a>'))
    router.get("https://shop.test/robots.txt").respond(404)
    router.get("https://shop.test/sitemap.xml").respond(404)
    router.get("https://shop.test/broken").mock(side_effect=httpx.ConnectError("down"))

    result = await crawl(fetcher, "https://shop.test/")

    assert len(result.pages) == 1
    assert "https://shop.test/broken" in result.errors


def test_parse_sitemap_index() -> None:
    text = """<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
      <sitemap><loc>https://shop.test/sitemap-pages.xml</loc></sitemap>
    </sitemapindex>"""
    assert parse_sitemap(text) == (True, ["https://shop.test/sitemap-pages.xml"])


def test_parse_sitemap_rejects_non_sitemaps() -> None:
    assert parse_sitemap("<html><body>hi</body></html>") is None
    assert parse_sitemap("not xml at all") is None


def test_robots_allows() -> None:
    from bizzcheckup.engine.types import RobotsInfo

    robots = RobotsInfo(
        url="https://shop.test/robots.txt",
        exists=True,
        text="User-agent: GPTBot\nDisallow: /\n\nUser-agent: *\nAllow: /\n",
    )
    assert not robots.allows("GPTBot", "https://shop.test/")
    assert robots.allows("BizzCheckup", "https://shop.test/")


def test_parse_sitemap_survives_billion_laughs() -> None:
    """XML "entity expansion" bombs must not eat the worker's memory.

    Python's XML parser (expat >= 2.4.1) refuses huge entity expansion, so the
    stdlib parser is safe here; this test proves it on our Python version.
    """
    entities = "".join(f'<!ENTITY lol{i} "{f"&lol{i - 1};" * 10}">' for i in range(1, 10))
    bomb = (
        f'<?xml version="1.0"?><!DOCTYPE l [<!ENTITY lol0 "lol">{entities}]><urlset>&lol9;</urlset>'
    )
    assert parse_sitemap(bomb) is None


async def test_extra_page_with_error_status_is_left_out(
    fetcher: Fetcher, router: respx.Router
) -> None:
    router.get("https://shop.test/").mock(return_value=html('<a href="/old">x</a>'))
    router.get("https://shop.test/robots.txt").respond(404)
    router.get("https://shop.test/sitemap.xml").respond(404)
    router.get("https://shop.test/old").respond(404, html="<h1>Not found</h1>")

    result = await crawl(fetcher, "https://shop.test/")

    assert len(result.pages) == 1
    assert result.errors == {"https://shop.test/old": "HTTP 404"}


async def test_firewall_challenge_gives_a_clear_message(
    fetcher: Fetcher, router: respx.Router
) -> None:
    from bizzcheckup.engine.crawler import UnusableHomepageError

    router.get("https://shop.test/").respond(
        429, headers={"x-vercel-mitigated": "challenge"}, html="<p>Vercel Security Checkpoint</p>"
    )
    with pytest.raises(UnusableHomepageError, match=r"security firewall \(Vercel\)"):
        await crawl(fetcher, "https://shop.test/")


@pytest.mark.parametrize(
    ("status", "headers", "html", "expected"),
    [
        (429, {"x-vercel-mitigated": "challenge"}, "", "Vercel"),
        (403, {"cf-mitigated": "challenge"}, "", "Cloudflare"),
        (503, {}, "<script src='/cdn-cgi/challenge-platform/x.js'></script>", "Cloudflare"),
        (403, {}, "<title>sgcaptcha</title>", "SiteGround"),
        (429, {}, "<h1>Please verify you are human</h1>", ""),
        (500, {}, "<h1>Internal error</h1>", None),  # a real error, not a firewall
        (200, {}, "<p>captcha on a contact form</p>", None),  # normal page
    ],
)
def test_firewall_name(
    status: int, headers: dict[str, str], html: str, expected: str | None
) -> None:
    from bizzcheckup.engine.crawler import firewall_name

    from .factories import make_page

    assert firewall_name(make_page(html, status_code=status, headers=headers)) == expected
