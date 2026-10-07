"""Best-practice checks, tested against local HTML and headers only (no network)."""

import pytest

from bizzcheckup.engine.checks import best_practices as bp
from bizzcheckup.engine.checks.base import Check
from bizzcheckup.engine.context import PROBES, AuditContext
from bizzcheckup.engine.types import Severity

from ..factories import fixture_html, make_context, make_page

HOME = "https://shop.test/"
SECURE_HEADERS = {
    "content-type": "text/html; charset=utf-8",
    "strict-transport-security": "max-age=31536000; includeSubDomains",
    "content-security-policy": "default-src 'self'; frame-ancestors 'self'",
    "x-content-type-options": "nosniff",
    "x-frame-options": "SAMEORIGIN",
    "referrer-policy": "strict-origin-when-cross-origin",
}

BP_CHECKS: list[type[Check]] = [
    bp.Https,
    bp.HttpRedirect,
    bp.MixedContent,
    bp.Hsts,
    bp.ContentSecurityPolicy,
    bp.NoSniff,
    bp.FrameProtection,
    bp.ReferrerPolicy,
    bp.OutdatedLibraries,
    bp.Doctype,
    bp.Charset,
    bp.Viewport,
]


def severities(check: type[Check], ctx: AuditContext) -> list[Severity]:
    return [finding.severity for finding in check().run(ctx)]


def healthy_context() -> AuditContext:
    page = make_page(fixture_html("healthy"), headers=SECURE_HEADERS)
    ctx = make_context(page, capabilities={PROBES})
    ctx.probes.http_final_url = HOME
    return ctx


def neglected_context() -> AuditContext:
    # Served over https but without any security headers or charset.
    page = make_page(fixture_html("neglected"), headers={"content-type": "text/html"})
    ctx = make_context(page, capabilities={PROBES})
    ctx.probes.http_final_url = "http://shop.test/"  # http:// does NOT redirect
    return ctx


@pytest.mark.parametrize("check", BP_CHECKS, ids=lambda c: c.id)
def test_healthy_page_passes(check: type[Check]) -> None:
    assert severities(check, healthy_context()) == [Severity.PASS]


@pytest.mark.parametrize(
    ("check", "expected"),
    [
        (bp.Https, [Severity.PASS]),  # it IS served over https
        (bp.HttpRedirect, [Severity.WARN]),
        (bp.MixedContent, [Severity.FAIL]),  # http:// script + stylesheet
        (bp.Hsts, [Severity.WARN]),
        (bp.ContentSecurityPolicy, [Severity.WARN]),
        (bp.NoSniff, [Severity.WARN]),
        (bp.FrameProtection, [Severity.WARN]),
        (bp.ReferrerPolicy, [Severity.WARN]),
        (bp.OutdatedLibraries, [Severity.FAIL]),
        (bp.Doctype, [Severity.WARN]),
        (bp.Charset, [Severity.WARN]),
        (bp.Viewport, [Severity.FAIL]),
    ],
    ids=lambda value: getattr(value, "id", ""),
)
def test_neglected_page_has_problems(check: type[Check], expected: list[Severity]) -> None:
    assert severities(check, neglected_context()) == expected


# --- HTTPS -------------------------------------------------------------------


def test_plain_http_site_fails_https_and_skips_https_only_checks() -> None:
    page = make_page("<p>hi</p>", url="http://shop.test/")
    ctx = make_context(page, capabilities={PROBES})

    assert severities(bp.Https, ctx) == [Severity.FAIL]
    assert bp.HttpRedirect().run(ctx) == []
    assert bp.Hsts().run(ctx) == []
    assert bp.MixedContent().run(ctx) == []


def test_http_version_not_served_is_info() -> None:
    ctx = make_context(capabilities={PROBES})
    ctx.probes.http_error = "Could not connect"
    assert severities(bp.HttpRedirect, ctx) == [Severity.INFO]


# --- mixed content -----------------------------------------------------------


def test_only_insecure_images_is_a_warning() -> None:
    page = make_page('<img src="http://shop.test/a.jpg" alt="">')
    findings = bp.MixedContent().run(make_context(page))
    assert findings[0].severity is Severity.WARN


# --- headers -----------------------------------------------------------------


def test_short_hsts_warns() -> None:
    page = make_page(headers={"strict-transport-security": "max-age=300"})
    assert severities(bp.Hsts, make_context(page)) == [Severity.WARN]


def test_csp_in_meta_tag_counts() -> None:
    html = (
        """<head><meta http-equiv="Content-Security-Policy" content="default-src 'self'"></head>"""
    )
    assert severities(bp.ContentSecurityPolicy, make_context(make_page(html))) == [Severity.PASS]


def test_csp_report_only_is_info() -> None:
    page = make_page(headers={"content-security-policy-report-only": "default-src 'self'"})
    assert severities(bp.ContentSecurityPolicy, make_context(page)) == [Severity.INFO]


def test_frame_ancestors_in_csp_counts_as_frame_protection() -> None:
    page = make_page(headers={"content-security-policy": "frame-ancestors 'none'"})
    assert severities(bp.FrameProtection, make_context(page)) == [Severity.PASS]


def test_unsafe_referrer_policy_warns() -> None:
    page = make_page(headers={"referrer-policy": "unsafe-url"})
    finding = bp.ReferrerPolicy().run(make_context(page))[0]
    assert finding.severity is Severity.WARN
    assert "shares full page addresses" in finding.message


# --- outdated libraries ------------------------------------------------------


@pytest.mark.parametrize(
    ("src", "outdated"),
    [
        ("https://code.jquery.com/jquery-1.12.4.min.js", True),
        ("https://ajax.googleapis.com/ajax/libs/jquery/3.4.1/jquery.min.js", True),
        ("https://cdn.jsdelivr.net/npm/jquery@3.7.1/dist/jquery.min.js", False),
        ("/wp-includes/js/jquery/jquery.min.js?ver=3.7.1", False),
        ("/wp-includes/js/jquery/jquery.js?ver=1.12.4-wp", True),
        ("https://stackpath.bootstrapcdn.com/bootstrap/4.1.3/js/bootstrap.min.js", True),
        ("https://cdn.jsdelivr.net/npm/bootstrap@5.3.3/dist/js/bootstrap.bundle.min.js", False),
        ("https://ajax.googleapis.com/ajax/libs/angularjs/1.8.2/angular.min.js", True),
        ("https://cdn.jsdelivr.net/npm/lodash@4.17.15/lodash.min.js", True),
        ("https://cdn.jsdelivr.net/npm/lodash@4.17.21/lodash.min.js", False),
        ("/static/app.js", False),
    ],
)
def test_outdated_library_detection(src: str, outdated: bool) -> None:
    page = make_page(f'<script src="{src}"></script>')
    expected = Severity.FAIL if outdated else Severity.PASS
    assert severities(bp.OutdatedLibraries, make_context(page)) == [expected]


def test_outdated_library_message_names_the_version() -> None:
    finding = bp.OutdatedLibraries().run(neglected_context())[0]
    assert "jQuery 1.12.4" in finding.message
    assert "Bootstrap 3.3.7" in finding.message


# --- document basics ---------------------------------------------------------


@pytest.mark.parametrize(
    "start",
    ["<!doctype html>", "<!DOCTYPE html>", "﻿<!DOCTYPE HTML>", "<!-- built -->\n<!doctype html>"],
)
def test_doctype_variants_pass(start: str) -> None:
    page = make_page(f"{start}<html><body></body></html>")
    assert severities(bp.Doctype, make_context(page)) == [Severity.PASS]


def test_charset_from_header_counts() -> None:
    page = make_page("<html></html>", headers={"content-type": "text/html; charset=UTF-8"})
    assert severities(bp.Charset, make_context(page)) == [Severity.PASS]


def test_viewport_without_device_width_warns() -> None:
    page = make_page('<head><meta name="viewport" content="width=1024"></head>')
    assert severities(bp.Viewport, make_context(page)) == [Severity.WARN]
