"""Tiny helpers that build engine objects for tests with sensible defaults."""

from pathlib import Path

from bizzcheckup.engine.context import AuditContext
from bizzcheckup.engine.types import (
    Category,
    CheckResult,
    CheckStatus,
    CrawlResult,
    Finding,
    Level,
    Page,
    RobotsInfo,
    Severity,
    SitemapInfo,
)


def make_page(
    html: str = "<html><head><title>Shop</title></head><body></body></html>",
    *,
    url: str = "https://shop.test/",
    status_code: int = 200,
    headers: dict[str, str] | None = None,
) -> Page:
    return Page(
        url=url,
        final_url=url,
        status_code=status_code,
        headers={"content-type": "text/html; charset=utf-8", **(headers or {})},
        text=html,
        size_bytes=len(html.encode()),
    )


FIXTURES = Path(__file__).resolve().parent.parent / "fixtures" / "html"


def fixture_html(name: str) -> str:
    """Read tests/fixtures/html/<name>.html"""
    return (FIXTURES / f"{name}.html").read_text(encoding="utf-8")


def make_context(
    *pages: Page,
    robots: RobotsInfo | None = None,
    sitemap: SitemapInfo | None = None,
    capabilities: set[str] | None = None,
) -> AuditContext:
    """An AuditContext built from local pages: no network involved."""
    all_pages = list(pages) or [make_page()]
    crawl = CrawlResult(
        start_url=all_pages[0].url,
        final_url=all_pages[0].final_url,
        pages=all_pages,
        robots=robots or RobotsInfo(url="https://shop.test/robots.txt", exists=False),
        sitemap=sitemap or SitemapInfo(),
    )
    return AuditContext(crawl=crawl, capabilities=capabilities or set())


def make_finding(
    severity: Severity = Severity.FAIL,
    *,
    category: Category = Category.SEO,
    impact: Level = Level.MEDIUM,
    effort: Level = Level.LOW,
    check_id: str = "seo.example",
    message: str = "Something is wrong.",
) -> Finding:
    return Finding(
        check_id=check_id,
        category=category,
        severity=severity,
        message=message,
        why_it_matters="It costs you customers.",
        how_to_fix="Fix it.",
        effort=effort,
        impact=impact,
    )


def make_result(
    score: float | None,
    *,
    category: Category = Category.SEO,
    weight: int = 5,
    status: CheckStatus = CheckStatus.RAN,
    findings: list[Finding] | None = None,
    note: str = "",
) -> CheckResult:
    return CheckResult(
        check_id=f"{category}.check{weight}",
        category=category,
        title="Example",
        weight=weight,
        status=status,
        score=score,
        findings=findings or [],
        note=note,
    )
