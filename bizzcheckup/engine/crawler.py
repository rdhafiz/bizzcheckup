"""Find and fetch the pages to analyse.

1. Fetch the homepage (the URL the visitor gave us), following redirects.
2. Read /robots.txt and the sitemap(s) it lists (or /sitemap.xml).
3. Pick up to `max_pages` same-origin pages: sitemap URLs first, then links
   found on the homepage.
4. Skip pages robots.txt forbids for BizzCheckup, then fetch the rest.

The homepage itself is always fetched because the site owner asked for it,
like opening it in a browser. Discovering *more* pages respects robots.txt.
"""

import asyncio
import xml.etree.ElementTree as ET

from selectolax.lexbor import LexborHTMLParser

from .config import ROBOTS_AGENT_NAME
from .fetcher import Fetcher, FetchError
from .netguard import BlockedURLError
from .types import CrawlResult, Page, RobotsInfo, SitemapInfo
from .urls import absolute, normalize_url, origin, same_origin

MAX_SITEMAP_FILES = 3
# Links to files like these are not web pages, so they aren't crawled.
NON_PAGE_EXTENSIONS = (
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".ico", ".zip", ".rar",
    ".mp3", ".mp4", ".mov", ".avi", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".css", ".js", ".json", ".xml", ".txt", ".csv",
)  # fmt: skip


async def crawl(fetcher: Fetcher, start_url: str) -> CrawlResult:
    """Crawl the site. Raises BlockedURLError/FetchError if the homepage fails."""
    homepage = await fetcher.get(start_url)
    base = origin(homepage.final_url)

    robots = await fetch_robots(fetcher, base)
    sitemap = await fetch_sitemaps(fetcher, robots.sitemaps or [f"{base}/sitemap.xml"])

    candidates = sitemap.urls + extract_links(homepage)
    wanted, skipped = choose_pages(
        candidates,
        base=base,
        exclude={normalize_url(homepage.final_url)},
        robots=robots,
        limit=fetcher.config.max_pages - 1,
    )

    errors: dict[str, str] = {}
    results = await asyncio.gather(*(fetch_page(fetcher, url, errors) for url in wanted))
    pages = [homepage] + [page for page in results if page is not None]

    return CrawlResult(
        start_url=start_url,
        final_url=homepage.final_url,
        pages=pages,
        robots=robots,
        sitemap=sitemap,
        skipped_by_robots=skipped,
        errors=errors,
    )


async def fetch_robots(fetcher: Fetcher, base: str) -> RobotsInfo:
    url = f"{base}/robots.txt"
    try:
        page = await fetcher.get(url)
    except (FetchError, BlockedURLError):
        return RobotsInfo(url=url, exists=False)

    # Some sites answer every unknown address with their HTML homepage ("soft 404").
    exists = page.ok and not page.is_html and not page.text.lstrip().startswith("<")
    if not exists:
        return RobotsInfo(url=url, exists=False, status_code=page.status_code)

    sitemaps = [
        line.split(":", 1)[1].strip()
        for line in page.text.splitlines()
        if line.lower().startswith("sitemap:")
    ]
    return RobotsInfo(
        url=url, exists=True, status_code=page.status_code, text=page.text, sitemaps=sitemaps
    )


async def fetch_sitemaps(fetcher: Fetcher, start: list[str]) -> SitemapInfo:
    """Read sitemaps, following one level of <sitemapindex>. Reads at most 3 files."""
    info = SitemapInfo()
    queue = list(start)
    while queue and len(info.checked) < MAX_SITEMAP_FILES:
        url = queue.pop(0)
        info.checked.append(url)
        try:
            page = await fetcher.get(url)
        except (FetchError, BlockedURLError):
            continue
        if not page.ok:
            continue
        parsed = parse_sitemap(page.text)
        if parsed is None:
            continue
        is_index, locations = parsed
        info.found = True
        if is_index:
            queue.extend(locations)
        else:
            info.urls.extend(locations)
    return info


def parse_sitemap(text: str) -> tuple[bool, list[str]] | None:
    """Return (is_index, <loc> URLs), or None if this isn't a valid sitemap."""
    try:
        root = ET.fromstring(text.encode())  # noqa: S314 (size-limited by the fetcher; no DTDs/entities used)
    except ET.ParseError:
        return None
    tag = root.tag.rsplit("}", 1)[-1]  # drop the XML namespace: "{...}urlset" -> "urlset"
    if tag not in ("urlset", "sitemapindex"):
        return None
    locations = [
        element.text.strip()
        for element in root.iter()
        if element.tag.rsplit("}", 1)[-1] == "loc" and element.text
    ]
    return tag == "sitemapindex", locations


def extract_links(page: Page) -> list[str]:
    """All http(s) links on the page, as absolute URLs, in page order."""
    if not page.is_html:
        return []
    tree = LexborHTMLParser(page.text)
    links: list[str] = []
    for node in tree.css("a[href]"):
        href = node.attributes.get("href") or ""
        url = absolute(page.final_url, href)
        if url is not None:
            links.append(url)
    return links


def choose_pages(
    candidates: list[str],
    *,
    base: str,
    exclude: set[str],
    robots: RobotsInfo,
    limit: int,
) -> tuple[list[str], list[str]]:
    """Pick up to `limit` same-origin, robots-allowed pages. Returns (wanted, skipped)."""
    wanted: list[str] = []
    skipped: list[str] = []
    seen = set(exclude)
    for raw in candidates:
        if len(wanted) >= limit:
            break
        try:
            url = normalize_url(raw)
        except ValueError:
            continue
        if url in seen or not same_origin(url, base):
            continue
        seen.add(url)
        if url.split("?")[0].lower().endswith(NON_PAGE_EXTENSIONS):
            continue
        if not robots.allows(ROBOTS_AGENT_NAME, url):
            skipped.append(url)
            continue
        wanted.append(url)
    return wanted, skipped


async def fetch_page(fetcher: Fetcher, url: str, errors: dict[str, str]) -> Page | None:
    """Fetch one extra page. Problems are recorded instead of stopping the crawl."""
    try:
        page = await fetcher.get(url)
    except (FetchError, BlockedURLError) as error:
        errors[url] = str(error)
        return None
    if not page.is_html:
        return None
    if not same_origin(page.final_url, url):  # redirected off-site
        return None
    return page
