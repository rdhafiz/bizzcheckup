"""PROBES collector: small extra requests that some checks need.

- http:// version of the homepage: does it redirect to https://?
- status of internal links found on the crawled pages (broken links)
- status of links to other websites, and of images
- /llms.txt
- the homepage requested as an AI agent and as a normal browser, to spot
  firewalls or CDNs that turn AI assistants away
- the homepage's link preview picture (og:image): does it load?
"""

import asyncio
from urllib.parse import urlsplit, urlunsplit

from .. import preview
from ..config import (
    AI_AGENT_USER_AGENT,
    BROWSER_USER_AGENT,
    ROBOTS_AGENT_NAME,
    WALLED_SITES,
    EngineConfig,
)
from ..context import PROBES, AuditContext
from ..crawler import extract_links
from ..fetcher import Fetcher, FetchError
from ..firewall import checkpoint_provider
from ..netguard import BlockedURLError
from ..types import AgentProbe
from ..urls import absolute, domain, same_origin, same_site, site_domain


async def collect_probes(ctx: AuditContext, fetcher: Fetcher, config: EngineConfig) -> None:
    await probe_http_version(ctx, fetcher)
    await asyncio.gather(
        probe_internal_links(ctx, fetcher, config.max_link_checks),
        probe_external_links(ctx, fetcher, config),
        probe_images(ctx, fetcher, config),
    )
    await probe_llms_txt(ctx, fetcher)
    await probe_og_image(ctx, fetcher)
    ctx.probes.as_ai_agent, ctx.probes.as_browser = await asyncio.gather(
        probe_as(fetcher, ctx.homepage.final_url, AI_AGENT_USER_AGENT),
        probe_as(fetcher, ctx.homepage.final_url, BROWSER_USER_AGENT),
    )
    ctx.capabilities.add(PROBES)


LLMS_TXT_KEEP = 4000  # characters kept for the report
OG_IMAGE_MAX_BYTES = 5 * 1024 * 1024  # bigger previews are skipped by most platforms


def sniff_image(data: bytes) -> str:
    """The image type from the file's first bytes ("" if it isn't a picture we can show).

    The server's Content-Type header can't be trusted for this; SVG is left out on
    purpose because it can carry scripts.
    """
    if data.startswith(bytes([0xFF, 0xD8, 0xFF])):
        return "image/jpeg"
    if data.startswith(bytes([0x89]) + b"PNG" + bytes([0x0D, 0x0A, 0x1A, 0x0A])):
        return "image/png"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "image/gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return ""


async def probe_og_image(ctx: AuditContext, fetcher: Fetcher) -> None:
    home = ctx.homepage
    url = preview.image_url(home.final_url, preview.read_tags(ctx.tree(home)))
    if not url:
        return
    ctx.probes.og_image_url = url
    try:
        page = await fetcher.get(url, keep_body=True)
    except (FetchError, BlockedURLError):
        return
    ctx.probes.og_image_status = page.status_code
    if not page.ok or page.body is None:
        return
    ctx.probes.og_image_type = sniff_image(page.body)
    ctx.probes.og_image_too_big = page.truncated or len(page.body) > OG_IMAGE_MAX_BYTES
    if ctx.probes.og_image_type and not ctx.probes.og_image_too_big:
        ctx.probes.og_image = page.body


async def probe_llms_txt(ctx: AuditContext, fetcher: Fetcher) -> None:
    parts = urlsplit(ctx.homepage.final_url)
    url = urlunsplit((parts.scheme, parts.netloc, "/llms.txt", "", ""))
    try:
        page = await fetcher.get(url)
    except (FetchError, BlockedURLError):
        return
    ctx.probes.llms_txt_status = page.status_code
    looks_like_text = not page.is_html and not page.text.lstrip().startswith("<")
    if page.ok and looks_like_text:
        ctx.probes.llms_txt_text = page.text[:LLMS_TXT_KEEP]


async def probe_as(fetcher: Fetcher, url: str, user_agent: str) -> AgentProbe:
    try:
        page = await fetcher.get(url, user_agent=user_agent)
    except (FetchError, BlockedURLError):
        return AgentProbe()
    challenge = checkpoint_provider(page.status_code, page.headers, page.text) is not None
    return AgentProbe(status_code=page.status_code, text_length=len(page.text), challenge=challenge)


async def probe_http_version(ctx: AuditContext, fetcher: Fetcher) -> None:
    """Visit http://<host>/ and record where it ends up."""
    parts = urlsplit(ctx.homepage.final_url)
    if parts.scheme != "https":
        return  # the site is already plain http; the HTTPS check reports that
    http_url = urlunsplit(("http", parts.hostname or "", "/", "", ""))
    try:
        page = await fetcher.get(http_url, method="HEAD")
    except (FetchError, BlockedURLError) as error:
        ctx.probes.http_error = str(error)
        return
    ctx.probes.http_final_url = page.final_url


OUTSIDE_AT_ONCE = 4  # requests to other websites at the same time


async def check_all(fetcher: Fetcher, urls: list[str], config: EngineConfig) -> dict[str, int]:
    """Statuses of URLs that may be on other websites (a few at a time, short timeout).

    Slow websites must not hold up the check-up: whatever hasn't answered within
    `outside_budget` seconds is left out (not counted as broken).
    """
    gate = asyncio.Semaphore(OUTSIDE_AT_ONCE)

    async def one(url: str) -> tuple[str, int]:
        async with gate:
            return url, await fetcher.status(url, timeout=config.external_timeout, polite=False)

    if not urls:
        return {}
    tasks = [asyncio.create_task(one(url)) for url in urls]
    done, pending = await asyncio.wait(tasks, timeout=config.outside_budget)
    for task in pending:
        task.cancel()
    results = dict(task.result() for task in done)
    return {url: results[url] for url in urls if url in results}  # keep page order


async def probe_external_links(ctx: AuditContext, fetcher: Fetcher, config: EngineConfig) -> None:
    """Check links from the crawled pages to other websites."""
    base = ctx.homepage.final_url
    sources: dict[str, list[str]] = {}
    for page in ctx.html_pages:
        for link in extract_links(page):
            link = link.split("#")[0]
            if not same_site(domain(link), domain(base)):
                pages = sources.setdefault(link, [])
                if page.final_url not in pages:
                    pages.append(page.final_url)
    walled = [url for url in sources if site_domain(domain(url)) in WALLED_SITES]
    checkable = [url for url in sources if url not in walled]
    ctx.probes.external_status = await check_all(
        fetcher, checkable[: config.max_external_checks], config
    )
    ctx.probes.external_sources = sources
    ctx.probes.external_skipped = walled


async def probe_images(ctx: AuditContext, fetcher: Fetcher, config: EngineConfig) -> None:
    """Check that the images on the crawled pages load."""
    sources: dict[str, list[str]] = {}
    for page in ctx.html_pages:
        for img in ctx.tree(page).css("img"):
            src = img.attributes.get("src") or ""
            url = absolute(page.final_url, src)
            if url:
                pages = sources.setdefault(url, [])
                if page.final_url not in pages:
                    pages.append(page.final_url)
    ctx.probes.image_status = await check_all(
        fetcher, list(sources)[: config.max_image_checks], config
    )
    ctx.probes.image_sources = sources


async def probe_internal_links(ctx: AuditContext, fetcher: Fetcher, limit: int) -> None:
    """Check the status of up to `limit` same-origin links (that robots.txt allows)."""
    base = ctx.homepage.final_url
    crawled = {page.final_url for page in ctx.pages} | {page.url for page in ctx.pages}

    sources: dict[str, list[str]] = {}
    for page in ctx.html_pages:
        for link in extract_links(page):
            link = link.split("#")[0]
            if same_origin(link, base) and ctx.robots.allows(ROBOTS_AGENT_NAME, link):
                pages = sources.setdefault(link, [])
                if page.final_url not in pages:
                    pages.append(page.final_url)

    to_check = [link for link in sources if link not in crawled][:limit]
    statuses = await asyncio.gather(*(fetcher.status(link) for link in to_check))

    ctx.probes.link_status = {page.final_url: page.status_code for page in ctx.pages}
    ctx.probes.link_status.update(dict(zip(to_check, statuses, strict=True)))
    # Pages the crawler tried but couldn't load (e.g. HTTP 404) count too.
    for url, error in ctx.crawl.errors.items():
        code = error.removeprefix("HTTP ")
        ctx.probes.link_status[url] = int(code) if code.isdigit() else 0
    ctx.probes.link_sources = sources
