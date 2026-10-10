"""Technical SEO checks (headings, images, addresses, meta tags), on local HTML only."""

import pytest

from bizzcheckup.engine.checks import technical_seo as tech
from bizzcheckup.engine.checks.base import Check
from bizzcheckup.engine.context import PROBES, AuditContext
from bizzcheckup.engine.types import Finding, Severity

from ..factories import fixture_html, make_context, make_page

HOME = "https://shop.test/"
CHECKS: list[type[Check]] = [
    tech.HeadingStructure,
    tech.ImageSeo,
    tech.UrlStructure,
    tech.MetaTags,
]


def run(check: type[Check], *pages_html: str | tuple[str, str]) -> list[Finding]:
    pages = []
    for index, item in enumerate(pages_html):
        html, url = item if isinstance(item, tuple) else (item, HOME if index == 0 else "")
        pages.append(make_page(html, url=url or f"{HOME}p{index}"))
    return check().run(make_context(*pages))


def body(html: str, head: str = "<title>Shop | Brand</title>") -> str:
    return f"<!doctype html><html lang='en'><head>{head}</head><body>{html}</body></html>"


def healthy() -> AuditContext:
    return make_context(make_page(fixture_html("healthy")))


@pytest.mark.parametrize("check", CHECKS, ids=lambda c: c.id)
def test_healthy_page_passes(check: type[Check]) -> None:
    assert [f.severity for f in check().run(healthy())] == [Severity.PASS]


@pytest.mark.parametrize(
    ("check", "severity"),
    [
        (tech.HeadingStructure, Severity.INFO),  # two H1s, a skipped level: notes only
        (tech.ImageSeo, Severity.WARN),
        (tech.MetaTags, Severity.WARN),
    ],
    ids=lambda value: getattr(value, "id", ""),
)
def test_neglected_page_has_problems(check: type[Check], severity: Severity) -> None:
    findings = check().run(make_context(make_page(fixture_html("neglected"))))
    assert findings[0].severity is severity
    assert findings[0].snippets  # a page-by-page breakdown to act on


# --- headings ------------------------------------------------------------------------------


def test_heading_outline_marks_the_problems() -> None:
    [finding] = run(tech.HeadingStructure, body("<h2>Intro</h2><h1>Shop</h1><h4></h4>"))
    assert finding.severity is Severity.WARN
    [snippet] = finding.snippets
    assert snippet.language == "text"
    assert "1 empty heading" in snippet.title
    assert "H1 isn't the first heading" in snippet.title
    assert snippet.code.splitlines() == [
        "  H2  Intro",
        "H1  Shop   <-- should come first",
        "      H4  (no text)   <-- empty, skips H2",
    ]


def test_same_h1_on_two_pages_is_flagged() -> None:
    page = body("<h1>Welcome</h1><h2>More</h2>")
    [finding] = run(tech.HeadingStructure, page, page)
    assert len(finding.affected_urls) == 2
    assert "also the H1 of another page" in finding.snippets[0].code


def test_heading_with_only_an_image_uses_its_alt() -> None:
    [finding] = run(tech.HeadingStructure, body('<h1><img src="l.png" alt="Sweet Moments"></h1>'))
    assert finding.severity is Severity.PASS


def test_long_page_without_sections_is_only_info() -> None:
    words = " ".join(["word"] * 320)
    [finding] = run(tech.HeadingStructure, body(f"<h1>Shop</h1><p>{words}</p>"))
    assert finding.severity is Severity.INFO
    assert "long page without H2 sections" in finding.snippets[0].title


def test_no_headings_is_left_to_the_main_heading_check() -> None:
    assert run(tech.HeadingStructure, body("<p>Hi</p>")) == []


# --- images --------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("alt", "problem"),
    [
        (None, "no alt text"),
        ("", ""),  # decorative: correct
        ("IMG_4821.jpg", "alt text is a file name"),
        ("DSC 0042", "alt text is a file name"),
        ("Image", 'alt text "Image" says nothing'),
        ("Chocolate cake with strawberries", ""),
    ],
)
def test_alt_problem(alt: str | None, problem: str) -> None:
    assert tech.alt_problem(alt) == problem


def test_image_breakdown_lists_each_image() -> None:
    html = body(
        '<img src="/IMG_4821.jpg" alt="photo">'
        '<img src="/cake.jpg" alt="Chocolate cake">'
        '<img src="data:image/png;base64,xx">'  # inline pixels are ignored
    )
    [finding] = run(tech.ImageSeo, html)
    assert finding.severity is Severity.WARN
    assert finding.message.startswith("1 of your 2 images")
    code = finding.snippets[0].code
    assert '/IMG_4821.jpg\n    alt: "photo"' in code
    assert "file name doesn't describe the image" in code
    assert "cake.jpg" not in code


def test_camera_file_names_alone_are_info() -> None:
    [finding] = run(tech.ImageSeo, body('<img src="/uploads/IMG_20240101.jpg" alt="Our shop">'))
    assert finding.severity is Severity.INFO


def test_no_images_not_applicable() -> None:
    assert run(tech.ImageSeo, body("<p>No pictures</p>")) == []


# --- addresses -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("url", "problems", "notes"),
    [
        (f"{HOME}wedding-cakes", [], []),
        (f"{HOME}Wedding_Cakes", ["capital letters", "underscores instead of hyphens"], []),
        (f"{HOME}our%20cakes", ["spaces"], []),
        (f"{HOME}shop?PHPSESSID=abc", ["session id in the address"], []),
        ("http://shop.test/about", ["links to the insecure http:// version"], []),
        (f"{HOME}a/b/c/d/e", [], ["more than 4 folders deep"]),
        (f"{HOME}page.php", [], ["technical ending (php)"]),
        (f"{HOME}x?utm_source=a&utm_medium=b&utm_campaign=c", [], []),  # tracking is fine
    ],
)
def test_url_problems(url: str, problems: list[str], notes: list[str]) -> None:
    assert tech.url_problems(url, https_site=True) == (problems, notes)


def test_clean_url_suggestion() -> None:
    assert tech.clean_url(f"{HOME}Our_Cakes//Big%20Ones?sid=9&size=2") == (
        f"{HOME}our-cakes/big-ones?size=2"
    )


def test_url_breakdown_suggests_clean_addresses() -> None:
    html = body('<a href="/About_Us">About</a> <a href="https://other.test/X_Y">Out</a>')
    [finding] = run(tech.UrlStructure, html)
    assert finding.severity is Severity.WARN
    assert finding.affected_urls == [f"{HOME}About_Us"]  # other sites aren't ours to judge
    assert f"suggested: {HOME}about-us" in finding.snippets[0].code


# --- meta tags -----------------------------------------------------------------------------


def test_missing_meta_tags_get_a_complete_head_block() -> None:
    html = "<html><head><title>Cakes | Sweet Moments</title></head><body></body></html>"
    [finding] = run(tech.MetaTags, html)
    assert finding.severity is Severity.WARN
    [snippet] = finding.snippets
    assert "missing description, viewport, charset, canonical, lang" in snippet.title
    assert "<title>Cakes | Sweet Moments</title>" in snippet.code  # kept
    assert f'<link rel="canonical" href="{HOME}">' in snippet.code
    assert 'content="REPLACE: 140-160 characters' in snippet.code
    assert '<html lang="REPLACE: language code, e.g. en">' in snippet.code


def test_existing_values_are_escaped_in_the_suggestion() -> None:
    head = '<title>A "quoted" & title</title><meta name="description" content="Tom &amp; Jerry">'
    [finding] = run(tech.MetaTags, f"<html><head>{head}</head></html>")
    code = finding.snippets[0].code
    assert '<meta name="description" content="Tom &amp; Jerry">' in code
    assert '<title>A "quoted" &amp; title</title>' in code


def test_only_language_missing_is_info() -> None:
    head = (
        '<meta charset="utf-8"><meta name="viewport" content="width=device-width">'
        '<title>Shop | Brand</title><meta name="description" content="d">'
        f'<link rel="canonical" href="{HOME}">'
    )
    [finding] = run(tech.MetaTags, f"<html><head>{head}</head></html>")
    assert finding.severity is Severity.INFO


def test_meta_refresh_warns() -> None:
    html = fixture_html("healthy").replace(
        "<head>", '<head><meta http-equiv="refresh" content="5; url=/new">'
    )
    findings = run(tech.MetaTags, html)
    assert [f.severity for f in findings] == [Severity.WARN]
    assert "meta refresh" in findings[0].message


# --- links to other websites and images ------------------------------------------------------


def probed(**statuses: object) -> AuditContext:
    ctx = make_context(make_page(fixture_html("healthy")), capabilities={PROBES})
    for name, value in statuses.items():
        setattr(ctx.probes, name, value)
    return ctx


def test_external_links_blocked_by_bot_protection_are_not_broken() -> None:
    ctx = probed(
        external_status={
            "https://partner.test/": 200,
            "https://linkedin.com/in/x": 999,  # LinkedIn refuses robots
            "https://gone.test/": 404,
            "https://dead.test/": 0,
        },
        external_sources={"https://gone.test/": [HOME]},
    )
    [finding] = tech.BrokenExternalLinks().run(ctx)
    assert finding.severity is Severity.WARN
    assert finding.affected_urls == ["https://dead.test/", "https://gone.test/"]
    code = finding.snippets[0].code
    assert (
        "https://gone.test/\n    answer: error 404\n    found on:\n      https://shop.test/" in code
    )
    assert "answer: can't be reached" in code


def test_broken_images_fail() -> None:
    ctx = probed(image_status={f"{HOME}a.jpg": 200, f"{HOME}b.jpg": 404})
    [finding] = tech.BrokenImages().run(ctx)
    assert finding.severity is Severity.FAIL
    assert finding.affected_urls == [f"{HOME}b.jpg"]


def test_nothing_probed_is_not_applicable() -> None:
    assert tech.BrokenExternalLinks().run(probed()) == []
    assert tech.BrokenImages().run(probed()) == []
    assert [
        f.severity for f in tech.BrokenImages().run(probed(image_status={f"{HOME}a": 200}))
    ] == [Severity.PASS]


@pytest.mark.parametrize(
    ("code", "broken", "verified"),
    [
        (200, False, True),
        (301, False, True),
        (404, True, True),
        (410, True, True),
        (503, True, True),
        (0, True, True),  # no answer at all
        (400, False, False),  # Facebook's answer to robots
        (403, False, False),
        (429, False, False),
        (999, False, False),  # LinkedIn's
    ],
)
def test_only_clear_answers_count(code: int, broken: bool, verified: bool) -> None:
    assert tech.is_broken(code) is broken
    assert tech.is_verified(code) is verified


def test_social_network_links_are_skipped_and_explained() -> None:
    ctx = probed(
        external_status={"https://partner.test/": 200, "https://other.test/x": 403},
        external_skipped=[
            "https://www.facebook.com/bizzacquire",
            "https://www.instagram.com/bizzacquire",
        ],
    )
    [finding] = tech.BrokenExternalLinks().run(ctx)
    assert finding.severity is Severity.PASS
    assert finding.message == (
        "All 1 links to other websites we checked work. Links to facebook.com, instagram.com "
        "can't be checked by a robot, so we skipped them."
    )
