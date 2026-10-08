"""Shared helpers for check-up tests: a ready-made engine report."""

from datetime import UTC, datetime

import pytest

from bizzcheckup.engine.scoring import band_for
from bizzcheckup.engine.types import (
    AuditReport,
    Category,
    CategoryScore,
    CheckResult,
    CheckStatus,
    Finding,
    Level,
    Severity,
    Snippet,
)

SCORES = {
    Category.PERFORMANCE: None,  # e.g. no PageSpeed key
    Category.ACCESSIBILITY: 72,
    Category.BEST_PRACTICES: 95,
    Category.SEO: 48,
    Category.AGENTIC: 60,
}


def make_report(url: str = "https://shop.test/") -> AuditReport:
    finding = Finding(
        check_id="seo.title",
        category=Category.SEO,
        severity=Severity.FAIL,
        message="Your homepage has no title.",
        why_it_matters="Google shows it.",
        how_to_fix="Add one.",
        effort=Level.LOW,
        impact=Level.HIGH,
        affected_urls=[url],
        snippets=[Snippet(title="Homepage: a title", code="<title>Shop | Fresh cakes</title>")],
    )
    passed = finding.model_copy(update={"check_id": "seo.sitemap", "severity": Severity.PASS})
    now = datetime.now(UTC)
    return AuditReport(
        url=url,
        final_url=url,
        started_at=now,
        finished_at=now,
        pages=[url],
        categories=[
            CategoryScore(
                category=c, score=s, band=band_for(s), checks_run=1 if s else 0, checks_skipped=0
            )
            for c, s in SCORES.items()
        ],
        health_score=66,
        health_band=band_for(66),
        results=[
            CheckResult(
                check_id="seo.title",
                category=Category.SEO,
                title="Page titles",
                weight=8,
                status=CheckStatus.RAN,
                score=0.0,
                findings=[finding, passed],
            )
        ],
        screenshot_jpeg=b"\xff\xd8fake-jpeg",
    )


@pytest.fixture
def report() -> AuditReport:
    return make_report()


@pytest.fixture(autouse=True)
def no_pdf_rendering(monkeypatch: pytest.MonkeyPatch) -> None:
    """Check-up tests don't need a real PDF (Chromium is slow); reports tests cover it."""
    from bizzcheckup.reports import pdf

    monkeypatch.setattr(pdf, "ensure_pdf", lambda checkup: b"%PDF-fake")
