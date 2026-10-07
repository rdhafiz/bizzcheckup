"""PAGESPEED collector: Google PageSpeed Insights (a Lighthouse test run by Google).

Runs the mobile and desktop tests at the same time. Without an API key
(config.psi_api_key, env PSI_API_KEY) it does nothing, and the performance
checks that need it are skipped with a clear note in the report.
"""

import asyncio
import json
from typing import Any
from urllib.parse import urlencode

from ..config import EngineConfig
from ..context import PAGESPEED, AuditContext
from ..fetcher import Fetcher
from ..types import FieldData, PageSpeedResult, SpeedTest

API_URL = "https://www.googleapis.com/pagespeedonline/v5/runPagespeed"


class PageSpeedError(Exception):
    """Google's API answered with an error (bad key, quota used up, site unreachable)."""


async def collect_pagespeed(ctx: AuditContext, fetcher: Fetcher, config: EngineConfig) -> None:
    if not config.psi_api_key:
        return
    url = ctx.homepage.final_url
    mobile, desktop = await asyncio.gather(
        run_test(fetcher, config, url, "mobile"),
        run_test(fetcher, config, url, "desktop"),
        return_exceptions=True,
    )
    result = PageSpeedResult(
        mobile=mobile if isinstance(mobile, SpeedTest) else None,
        desktop=desktop if isinstance(desktop, SpeedTest) else None,
    )
    if result.mobile is None and result.desktop is None:
        raise mobile if isinstance(mobile, BaseException) else PageSpeedError("No results.")
    ctx.pagespeed = result
    ctx.capabilities.add(PAGESPEED)


async def run_test(fetcher: Fetcher, config: EngineConfig, url: str, strategy: str) -> SpeedTest:
    query = urlencode({"url": url, "strategy": strategy, "category": "performance"})
    page = await fetcher.get(
        f"{API_URL}?{query}",
        # The key goes in a header, never in the URL, so it can't leak into logs.
        headers={"X-Goog-Api-Key": config.psi_api_key},
        timeout=config.psi_timeout,
        polite=False,  # this request goes to Google, not to the audited site
    )
    if not page.ok:
        raise PageSpeedError(f"PageSpeed {strategy} test failed (HTTP {page.status_code}).")
    return parse_speed_test(json.loads(page.text), strategy)


def parse_speed_test(data: dict[str, Any], strategy: str) -> SpeedTest:
    """Pick the numbers we use out of Google's (very large) answer."""
    lighthouse = data.get("lighthouseResult", {})
    audits: dict[str, Any] = lighthouse.get("audits", {})

    def value(audit_id: str) -> float | None:
        number = audits.get(audit_id, {}).get("numericValue")
        return float(number) if number is not None else None

    def item_urls(audit_id: str) -> list[str]:
        items = audits.get(audit_id, {}).get("details", {}).get("items", []) or []
        return [str(item["url"]) for item in items if isinstance(item, dict) and item.get("url")]

    total_bytes = value("total-byte-weight")
    return SpeedTest(
        strategy=strategy,
        score=float(lighthouse.get("categories", {}).get("performance", {}).get("score") or 0),
        lcp_ms=value("largest-contentful-paint"),
        cls=value("cumulative-layout-shift"),
        tbt_ms=value("total-blocking-time"),
        fcp_ms=value("first-contentful-paint"),
        speed_index_ms=value("speed-index"),
        total_bytes=int(total_bytes) if total_bytes is not None else None,
        render_blocking=item_urls("render-blocking-resources"),
        render_blocking_savings_ms=float(
            audits.get("render-blocking-resources", {}).get("details", {}).get("overallSavingsMs")
            or 0
        ),
        offscreen_images=item_urls("offscreen-images"),
        unsized_images=item_urls("unsized-images"),
        field=parse_field_data(data),
    )


def parse_field_data(data: dict[str, Any]) -> FieldData | None:
    """Real-user data for this page, or for the whole site if the page has too little."""
    for key, origin_wide in (("loadingExperience", False), ("originLoadingExperience", True)):
        metrics: dict[str, Any] = (data.get(key) or {}).get("metrics") or {}
        if not metrics:
            continue

        def percentile(name: str, metrics: dict[str, Any] = metrics) -> float | None:
            number = metrics.get(name, {}).get("percentile")
            return float(number) if number is not None else None

        cls = percentile("CUMULATIVE_LAYOUT_SHIFT_SCORE")
        return FieldData(
            lcp_ms=percentile("LARGEST_CONTENTFUL_PAINT_MS"),
            cls=cls / 100 if cls is not None else None,  # Google sends CLS x 100
            inp_ms=percentile("INTERACTION_TO_NEXT_PAINT"),
            fcp_ms=percentile("FIRST_CONTENTFUL_PAINT_MS"),
            origin_wide=origin_wide,
        )
    return None
