"""PROBES collector: small extra requests that some checks need.

- http:// version of the homepage: does it redirect to https://?
- status of internal links found on the crawled pages (broken links)
- /llms.txt
- the homepage requested as an AI agent and as a normal browser, to spot
  firewalls or CDNs that turn AI assistants away
"""

import asyncio
from urllib.parse import urlsplit, urlunsplit

from ..config import AI_AGENT_USER_AGENT, BROWSER_USER_AGENT, ROBOTS_AGENT_NAME, EngineConfig
from ..context import PROBES, AuditContext
from ..crawler import extract_links
from ..fetcher import Fetcher, FetchError
from ..firewall import checkpoint_provider
from ..netguard import BlockedURLError
from ..types import AgentProbe
from ..urls import same_origin


async def collect_probes(ctx: AuditContext, fetcher: Fetcher, config: EngineConfig) -> None:
    await probe_http_version(ctx, fetcher)
    await probe_internal_links(ctx, fetcher, config.max_link_checks)
    await probe_llms_txt(ctx, fetcher)
    ctx.probes.as_ai_agent, ctx.probes.as_browser = await asyncio.gather(
        probe_as(fetcher, ctx.homepage.final_url, AI_AGENT_USER_AGENT),
        probe_as(fetcher, ctx.homepage.final_url, BROWSER_USER_AGENT),
    )
    ctx.capabilities.add(PROBES)


LLMS_TXT_KEEP = 4000  # characters kept for the report


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
