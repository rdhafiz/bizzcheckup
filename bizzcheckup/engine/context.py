"""AuditContext: everything the collectors found, handed to every check.

Checks only READ from here. They never fetch anything themselves, which keeps
them fast and lets tests build a context from local HTML files.
"""

from dataclasses import dataclass, field

from selectolax.lexbor import LexborHTMLParser

from .types import CrawlResult, Page, ProbeResults, RobotsInfo, SitemapInfo

# Names of optional data sources. A check lists the ones it needs in `requires`;
# if a source is missing (e.g. no PageSpeed API key) the check is skipped.
RENDER = "render"  # Playwright: rendered HTML, screenshot, axe-core (phase 4)
PAGESPEED = "pagespeed"  # Google PageSpeed Insights (phase 5)
PROBES = "probes"  # extra requests: llms.txt, link statuses, AI user agents (phase 5)


@dataclass
class AuditContext:
    crawl: CrawlResult
    capabilities: set[str] = field(default_factory=set)
    probes: ProbeResults = field(default_factory=ProbeResults)  # filled by PROBES collector
    _trees: dict[str, LexborHTMLParser] = field(default_factory=dict, repr=False)

    @property
    def homepage(self) -> Page:
        return self.crawl.homepage

    @property
    def pages(self) -> list[Page]:
        return self.crawl.pages

    @property
    def robots(self) -> RobotsInfo:
        return self.crawl.robots

    @property
    def sitemap(self) -> SitemapInfo:
        return self.crawl.sitemap

    @property
    def html_pages(self) -> list[Page]:
        return [page for page in self.crawl.pages if page.is_html]

    def has(self, capability: str) -> bool:
        return capability in self.capabilities

    def tree(self, page: Page) -> LexborHTMLParser:
        """Parsed HTML of `page`. Parsed once, then reused by every check."""
        key = page.final_url
        if key not in self._trees:
            self._trees[key] = LexborHTMLParser(page.text)
        return self._trees[key]
