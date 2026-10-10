"""SEO checks, tested against local HTML only (no network)."""

import json

import pytest

from bizzcheckup.engine.checks import seo
from bizzcheckup.engine.checks.base import Check
from bizzcheckup.engine.context import PROBES, AuditContext
from bizzcheckup.engine.types import RobotsInfo, Severity, SitemapInfo

from ..factories import fixture_html, make_context, make_page

HOME = "https://shop.test/"
GOOD_ROBOTS = RobotsInfo(
    url=f"{HOME}robots.txt",
    exists=True,
    text=f"User-agent: *\nAllow: /\nSitemap: {HOME}sitemap.xml\n",
    sitemaps=[f"{HOME}sitemap.xml"],
)
GOOD_SITEMAP = SitemapInfo(checked=[f"{HOME}sitemap.xml"], found=True, urls=[HOME])


def severities(check: type[Check], ctx: AuditContext) -> list[Severity]:
    return [finding.severity for finding in check().run(ctx)]


def healthy_context() -> AuditContext:
    ctx = make_context(
        make_page(fixture_html("healthy")),
        robots=GOOD_ROBOTS,
        sitemap=GOOD_SITEMAP,
        capabilities={PROBES},
    )
    ctx.probes.link_status = {HOME: 200, f"{HOME}about": 200, f"{HOME}order": 200}
    return ctx


def neglected_context() -> AuditContext:
    ctx = make_context(make_page(fixture_html("neglected")), capabilities={PROBES})
    ctx.probes.link_status = {HOME: 200, f"{HOME}old-offer": 404, f"{HOME}contact": 200}
    ctx.probes.link_sources = {f"{HOME}old-offer": [HOME]}
    return ctx


SEO_CHECKS: list[type[Check]] = [
    seo.Title,
    seo.MetaDescription,
    seo.SingleH1,
    seo.Canonical,
    seo.RobotsTxt,
    seo.Sitemap,
    seo.Indexable,
    seo.SocialTags,
    seo.PageSchema,
    seo.BrokenLinks,
]


@pytest.mark.parametrize("check", SEO_CHECKS, ids=lambda c: c.id)
def test_healthy_page_passes(check: type[Check]) -> None:
    assert severities(check, healthy_context()) == [Severity.PASS]


@pytest.mark.parametrize(
    ("check", "expected"),
    [
        (seo.Title, [Severity.FAIL]),
        (seo.MetaDescription, [Severity.WARN]),
        (seo.SingleH1, [Severity.WARN]),
        (seo.Canonical, [Severity.WARN]),
        (seo.RobotsTxt, [Severity.WARN]),
        (seo.Sitemap, [Severity.WARN]),
        (seo.Indexable, [Severity.FAIL]),
        (seo.SocialTags, [Severity.WARN]),
        (seo.PageSchema, [Severity.FAIL]),
        (seo.BrokenLinks, [Severity.FAIL]),
    ],
    ids=lambda value: getattr(value, "id", ""),
)
def test_neglected_page_has_problems(check: type[Check], expected: list[Severity]) -> None:
    assert severities(check, neglected_context()) == expected


def test_every_finding_explains_business_impact_and_fix() -> None:
    for ctx in (healthy_context(), neglected_context()):
        for check in SEO_CHECKS:
            for finding in check().run(ctx):
                assert finding.why_it_matters
                assert finding.how_to_fix
                assert finding.check_id == check.id


# --- edge cases --------------------------------------------------------------


def page_with_head(head: str, body: str = "<h1>x</h1>") -> str:
    return f"<!doctype html><html><head>{head}</head><body>{body}</body></html>"


@pytest.mark.parametrize(
    ("title", "expected"),
    [
        ("Sweet Moments Bakery | Cakes", Severity.PASS),
        ("Home", Severity.WARN),  # too short
        ("A" * 61, Severity.WARN),  # too long
        ("", Severity.FAIL),
    ],
)
def test_title_lengths(title: str, expected: Severity) -> None:
    ctx = make_context(make_page(page_with_head(f"<title>{title}</title>")))
    assert severities(seo.Title, ctx) == [expected]


def test_title_gives_partial_credit_across_pages() -> None:
    good = page_with_head("<title>Sweet Moments Bakery | Cakes</title>")
    pages = [make_page(good, url=f"{HOME}p{i}") for i in range(3)]
    pages.append(make_page(page_with_head(""), url=f"{HOME}missing"))
    check = seo.Title()
    findings = check.run(make_context(*pages))

    assert findings[0].message == "1 of the 4 pages we checked has no title."
    assert findings[0].affected_urls == [f"{HOME}missing"]
    assert check.score(findings) == 0.75


def test_canonical_pointing_to_another_site_fails() -> None:
    html = page_with_head('<link rel="canonical" href="https://competitor.test/">')
    findings = seo.Canonical().run(make_context(make_page(html)))
    assert findings[0].severity is Severity.FAIL
    assert "competitor.test" in findings[0].message


def test_relative_canonical_warns() -> None:
    html = page_with_head('<link rel="canonical" href="/">')
    assert severities(seo.Canonical, make_context(make_page(html))) == [Severity.WARN]


def test_robots_blocking_google_fails() -> None:
    robots = RobotsInfo(url=f"{HOME}robots.txt", exists=True, text="User-agent: *\nDisallow: /\n")
    assert severities(seo.RobotsTxt, make_context(robots=robots)) == [Severity.FAIL]


def test_sitemap_without_robots_reference_adds_info() -> None:
    robots = RobotsInfo(url=f"{HOME}robots.txt", exists=True, text="User-agent: *\nAllow: /\n")
    ctx = make_context(robots=robots, sitemap=GOOD_SITEMAP)
    assert severities(seo.Sitemap, ctx) == [Severity.PASS, Severity.INFO]


def test_empty_sitemap_warns() -> None:
    sitemap = SitemapInfo(checked=[f"{HOME}sitemap.xml"], found=True, urls=[])
    assert severities(seo.Sitemap, make_context(sitemap=sitemap)) == [Severity.WARN]


def test_noindex_header_on_homepage_fails() -> None:
    page = make_page(page_with_head(""), headers={"x-robots-tag": "noindex"})
    assert severities(seo.Indexable, make_context(page)) == [Severity.FAIL]


def test_noindex_on_other_page_is_only_info() -> None:
    home = make_page(page_with_head(""))
    thanks = make_page(page_with_head('<meta name="robots" content="noindex">'), url=f"{HOME}t")
    assert severities(seo.Indexable, make_context(home, thanks)) == [Severity.INFO]


def test_partial_social_tags_lists_whats_missing() -> None:
    html = page_with_head('<meta property="og:title" content="Shop">')
    finding = seo.SocialTags().run(make_context(make_page(html)))[0]
    assert finding.severity is Severity.WARN
    assert "og:description" in finding.message
    assert "twitter:card" in finding.message


@pytest.mark.parametrize(
    ("json_ld", "expected"),
    [
        # Complete: a local business with its details, and the website.
        (
            json.dumps(
                {
                    "@context": "https://schema.org",
                    "@graph": [
                        {
                            "@type": "Bakery",
                            "name": "Sweet Moments",
                            "url": HOME,
                            "image": f"{HOME}cake.jpg",
                            "telephone": "+880 1700 000000",
                            "address": {"@type": "PostalAddress", "addressLocality": "Dhaka"},
                            "openingHoursSpecification": [{"opens": "08:00", "closes": "20:00"}],
                        },
                        {"@type": "WebSite", "name": "Sweet Moments", "url": HOME},
                    ],
                }
            ),
            [Severity.PASS],
        ),
        # Valid but thin: no WebSite, and the bakery lacks its required address.
        (json.dumps({"@context": "https://schema.org", "@type": "Bakery"}), [Severity.WARN]),
        # No @type: as good as nothing.
        (json.dumps({"@context": "https://schema.org"}), [Severity.WARN]),
        # Trailing comma: invalid JSON, so search engines ignore it.
        ('{"@type": "Bakery",}', [Severity.FAIL]),
    ],
)
def test_page_schema_variants(json_ld: str, expected: list[Severity]) -> None:
    html = page_with_head(f'<script type="application/ld+json">{json_ld}</script>')
    assert severities(seo.PageSchema, make_context(make_page(html))) == expected


def test_no_structured_data_gets_a_complete_suggestion() -> None:
    [finding] = seo.PageSchema().run(make_context())
    assert finding.severity is Severity.WARN
    assert finding.impact.value == "medium"  # it's the homepage
    [snippet] = finding.snippets
    assert snippet.title.startswith("Homepage")
    assert "missing Organization, WebSite" in snippet.title
    body = json.loads(
        snippet.code.removeprefix('<script type="application/ld+json">').removesuffix("</script>")
    )
    assert [item["@type"] for item in body["@graph"]] == ["Organization", "WebSite"]


def test_every_page_gets_its_own_suggestion() -> None:
    about = make_page(
        "<html><head><title>About us | Shop</title></head></html>", url=f"{HOME}about"
    )
    post = make_page(
        '<html><head><title>Cake care | Shop</title><meta property="og:type" content="article">'
        "</head></html>",
        url=f"{HOME}blog/cake-care",
    )
    ctx = make_context(make_page(fixture_html("healthy")), about, post)
    [finding] = seo.PageSchema().run(ctx)
    assert finding.severity is Severity.WARN
    assert finding.impact.value == "low"  # the homepage itself is fine
    assert finding.affected_urls == [f"{HOME}about", f"{HOME}blog/cake-care"]
    titles = [s.title for s in finding.snippets]
    assert titles[0].startswith("About page")
    assert "missing AboutPage" in titles[0]
    assert titles[1].startswith("Article")
    assert "missing Article, BreadcrumbList" in titles[1]


def test_valid_schema_missing_only_optional_extras_is_info() -> None:
    org = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "Organization", "name": "Shop", "url": HOME},
            {"@type": "WebSite", "name": "Shop", "url": HOME},
        ],
    }
    html = page_with_head(f'<script type="application/ld+json">{json.dumps(org)}</script>')
    [finding] = seo.PageSchema().run(make_context(make_page(html)))
    assert finding.severity is Severity.INFO
    assert "could add logo, sameAs, contactPoint" in finding.snippets[0].title


def test_broken_links_not_applicable_without_links() -> None:
    ctx = make_context(capabilities={PROBES})
    ctx.probes.link_status = {HOME: 200}
    assert seo.BrokenLinks().run(ctx) == []


def test_broken_links_partial_score() -> None:
    ctx = neglected_context()
    check = seo.BrokenLinks()
    findings = check.run(ctx)
    assert findings[0].affected_urls == [f"{HOME}old-offer"]
    assert check.score(findings) == pytest.approx(2 / 3)


def test_duplicate_titles() -> None:
    same = page_with_head("<title>Sweet Moments Bakery</title>")
    pages = [make_page(same, url=f"{HOME}a"), make_page(same, url=f"{HOME}b")]
    unique = make_page(page_with_head("<title>Contact Sweet Moments</title>"), url=f"{HOME}c")

    findings = seo.DuplicateTitles().run(make_context(*pages, unique))

    assert findings[0].severity is Severity.WARN
    assert findings[0].affected_urls == [f"{HOME}a", f"{HOME}b"]


def test_duplicate_titles_not_applicable_for_single_page() -> None:
    assert seo.DuplicateTitles().run(make_context()) == []


def test_link_preview_reviews_every_page_with_a_ready_block() -> None:
    other = make_page("<html><head><title>About | Shop</title></head></html>", url=f"{HOME}about")
    [finding] = seo.SocialTags().run(make_context(make_page(fixture_html("healthy")), other))
    assert finding.severity is Severity.WARN
    assert finding.impact.value == "low"  # the homepage is fine
    assert finding.affected_urls == [f"{HOME}about"]
    [snippet] = finding.snippets
    assert '<meta property="og:title" content="About | Shop">' in snippet.code


def test_relative_preview_image_is_a_problem() -> None:
    html = fixture_html("healthy").replace(
        'content="https://shop.test/og.jpg"', 'content="/og.jpg"'
    )
    [finding] = seo.SocialTags().run(make_context(make_page(html)))
    assert "og:image is not a full address" in finding.message


@pytest.mark.parametrize(
    ("status", "kind", "too_big", "expected"),
    [
        (200, "image/jpeg", False, ""),
        (404, "", False, "is missing (error 404)"),
        (0, "", False, "can't be reached"),
        (200, "", False, "isn't a JPG, PNG, GIF or WebP picture"),
        (200, "image/png", True, "is larger than 5 MB"),
    ],
)
def test_broken_preview_picture(status: int, kind: str, too_big: bool, expected: str) -> None:
    ctx = make_context(make_page(fixture_html("healthy")), capabilities={PROBES})
    ctx.probes.og_image_url = f"{HOME}og.jpg"
    ctx.probes.og_image_status = status
    ctx.probes.og_image_type = kind
    ctx.probes.og_image_too_big = too_big
    findings = seo.SocialTags().run(ctx)
    if expected:
        assert findings[0].message == (
            f"Your homepage's preview picture {expected}, so shared links show no image."
        )
    else:
        assert [f.severity for f in findings] == [Severity.PASS]


def test_description_lengths_are_listed_page_by_page() -> None:
    long = "Strategy-led growth marketing for Bangladesh startups and SMEs. " * 3  # 192
    pages = [
        make_page(page_with_head(f'<meta name="description" content="{long}">'), url=f"{HOME}a"),
        make_page(page_with_head('<meta name="description" content="Too short.">'), url=f"{HOME}b"),
        make_page(
            page_with_head(f'<meta name="description" content="{"x" * 120}">'), url=f"{HOME}c"
        ),
    ]
    [finding] = seo.MetaDescription().run(make_context(*pages))
    assert finding.message == (
        "2 of the 3 pages we checked have descriptions of the wrong length: "
        "1 too long (over 160 characters) and 1 too short (under 50)."
    )
    [snippet] = finding.snippets
    rows = snippet.code.split("\n\n")
    assert rows[0].splitlines()[:2] == [
        f"{HOME}a",
        f"    {len(long.strip())} characters: too long by {len(long.strip()) - 160} "
        "(Google shows about 160)",
    ]
    assert rows[1].splitlines()[1] == "    10 characters: too short by 40 (aim for 50-160)"
    assert rows[1].splitlines()[2] == '    now: "Too short."'


def test_homepage_description_length_message() -> None:
    html = page_with_head('<meta name="description" content="Cakes.">')
    [finding] = seo.MetaDescription().run(make_context(make_page(html)))
    assert finding.message == (
        "Your homepage's search description is too short: 6 characters (aim for 50-160)."
    )
