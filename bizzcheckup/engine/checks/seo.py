"""SEO checks: can Google find, understand and show your website?"""

from collections import defaultdict

from .. import preview, schema
from ..context import PROBES, AuditContext
from ..types import Category, Finding, Level, Severity, Snippet
from ..urls import domain, origin
from ._helpers import links_with_rel, meta_content, on_pages, share_score, title_text
from .base import Check

TITLE_MIN, TITLE_MAX = 10, 60
DESCRIPTION_MIN, DESCRIPTION_MAX = 50, 160
MAX_SNIPPETS = 20  # pages shown with a ready-made fix


class Title(Check):
    id = "seo.title"
    category = Category.SEO
    title = "Page titles"
    weight = 8

    WHY = (
        "The title is the blue headline people click in Google results and the name on the "
        "browser tab. A clear title brings more visitors from search."
    )

    def run(self, ctx: AuditContext) -> list[Finding]:
        pages = ctx.html_pages
        missing, too_long, too_short = [], [], []
        for page in pages:
            text = title_text(ctx.tree(page))
            if not text:
                missing.append(page.final_url)
            elif len(text) > TITLE_MAX:
                too_long.append(page.final_url)
            elif len(text) < TITLE_MIN:
                too_short.append(page.final_url)

        total = len(pages)
        self.partial = share_score(total, len(missing), len(too_long) + len(too_short))
        findings: list[Finding] = []
        if missing:
            findings.append(
                self.finding(
                    Severity.FAIL,
                    on_pages(len(missing), total, "has no title.", "have no title."),
                    self.WHY,
                    "Add a unique <title> of 30-60 characters to every page: what the page "
                    'offers first, your business name last, e.g. "Wedding Cakes in Dhaka | '
                    'Sweet Moments Bakery".',
                    impact=Level.HIGH,
                    urls=missing,
                )
            )
        if too_long:
            findings.append(
                self.finding(
                    Severity.WARN,
                    on_pages(
                        len(too_long),
                        total,
                        f"has a title longer than {TITLE_MAX} characters, so Google cuts it off.",
                        f"have titles longer than {TITLE_MAX} characters, so Google cuts them off.",
                    ),
                    self.WHY,
                    f"Shorten titles to {TITLE_MAX} characters or fewer and put the most "
                    "important words first.",
                    impact=Level.LOW,
                    urls=too_long,
                )
            )
        if too_short:
            findings.append(
                self.finding(
                    Severity.WARN,
                    on_pages(
                        len(too_short),
                        total,
                        "has a very short title that doesn't say what the page offers.",
                        "have very short titles that don't say what the pages offer.",
                    ),
                    self.WHY,
                    'Describe each page in its title, e.g. "Home" becomes "Handmade Leather '
                    'Bags | Your Brand".',
                    urls=too_short,
                )
            )
        return findings or [self.passed("Every page has a clear title of a good length.", self.WHY)]


class MetaDescription(Check):
    id = "seo.meta_description"
    category = Category.SEO
    title = "Search result descriptions"
    weight = 6

    WHY = (
        "The description is the short text under your title in Google. A good one works like "
        "a mini advert and convinces people to click your result instead of a competitor's."
    )
    FIX = (
        f'Add <meta name="description" content="..."> with {DESCRIPTION_MIN}-{DESCRIPTION_MAX} '
        "characters that sum up the page and end with a reason to visit."
    )

    def run(self, ctx: AuditContext) -> list[Finding]:
        pages = ctx.html_pages
        missing, bad_length = [], []
        for page in pages:
            text = meta_content(ctx.tree(page), "description")
            if not text:
                missing.append(page.final_url)
            elif not DESCRIPTION_MIN <= len(text) <= DESCRIPTION_MAX:
                bad_length.append(page.final_url)

        total = len(pages)
        self.partial = share_score(total, 0, len(missing) * 2 + len(bad_length))
        findings: list[Finding] = []
        if missing:
            findings.append(
                self.finding(
                    Severity.WARN,
                    on_pages(
                        len(missing),
                        total,
                        "has no search description, so Google picks random text from it.",
                        "have no search description, so Google picks random text from them.",
                    ),
                    self.WHY,
                    self.FIX,
                    impact=Level.MEDIUM,
                    urls=missing,
                )
            )
        if bad_length:
            findings.append(
                self.finding(
                    Severity.WARN,
                    on_pages(
                        len(bad_length),
                        total,
                        "has a description that is too short or too long.",
                        "have descriptions that are too short or too long.",
                    ),
                    self.WHY,
                    self.FIX,
                    impact=Level.LOW,
                    urls=bad_length,
                )
            )
        return findings or [self.passed("Every page has a good search description.", self.WHY)]


class SingleH1(Check):
    id = "seo.single_h1"
    category = Category.SEO
    title = "Main heading"
    weight = 5

    WHY = (
        "The main heading (H1) tells visitors and Google what a page is about at a glance. "
        "One clear heading per page helps you rank for the right searches."
    )

    def run(self, ctx: AuditContext) -> list[Finding]:
        pages = ctx.html_pages
        none, several = [], []
        for page in pages:
            count = len(ctx.tree(page).css("h1"))
            if count == 0:
                none.append(page.final_url)
            elif count > 1:
                several.append(page.final_url)

        total = len(pages)
        self.partial = share_score(total, 0, len(none) + len(several))
        findings: list[Finding] = []
        if none:
            findings.append(
                self.finding(
                    Severity.WARN,
                    on_pages(len(none), total, "has no main heading.", "have no main heading."),
                    self.WHY,
                    'Give each page one <h1> that states its topic, e.g. "Family Dentist in '
                    'Gulshan".',
                    impact=Level.MEDIUM,
                    urls=none,
                )
            )
        if several:
            findings.append(
                self.finding(
                    Severity.WARN,
                    on_pages(
                        len(several),
                        total,
                        "has more than one main heading.",
                        "have more than one main heading.",
                    ),
                    self.WHY,
                    "Keep one <h1> per page and turn the others into <h2> or <h3> section "
                    "headings.",
                    impact=Level.LOW,
                    urls=several,
                )
            )
        return findings or [self.passed("Every page has exactly one main heading.", self.WHY)]


class Canonical(Check):
    id = "seo.canonical"
    category = Category.SEO
    title = "Preferred page address"
    weight = 3

    WHY = (
        'A canonical tag tells Google which address is the "real" one when the same page '
        "can be reached in several ways, so your ranking isn't split between copies."
    )

    def run(self, ctx: AuditContext) -> list[Finding]:
        page = ctx.homepage
        tags = links_with_rel(ctx.tree(page), "canonical")
        hrefs = [(tag.attributes.get("href") or "").strip() for tag in tags]

        if not hrefs:
            return [
                self.finding(
                    Severity.WARN,
                    "Your homepage doesn't say which address is its preferred one.",
                    self.WHY,
                    f'Add <link rel="canonical" href="{page.final_url}"> inside <head>.',
                    impact=Level.LOW,
                    urls=[page.final_url],
                )
            ]
        if len(set(hrefs)) > 1:
            return [
                self.finding(
                    Severity.WARN,
                    "Your homepage names several different preferred addresses, which "
                    "confuses Google.",
                    self.WHY,
                    "Keep exactly one canonical tag.",
                    urls=[page.final_url],
                )
            ]
        href = hrefs[0]
        if not href.startswith(("http://", "https://")):
            return [
                self.finding(
                    Severity.WARN,
                    "Your homepage's preferred address is incomplete (it should be a full "
                    "web address).",
                    self.WHY,
                    f'Use the full address, e.g. <link rel="canonical" href="{page.final_url}">.',
                    impact=Level.LOW,
                    urls=[page.final_url],
                )
            ]
        if domain(href) != domain(page.final_url):
            return [
                self.finding(
                    Severity.FAIL,
                    "Your homepage tells Google that the real page is on another website "
                    f"({domain(href)}).",
                    "Google may show that other site in search results instead of yours.",
                    "Point the canonical tag at your own homepage address.",
                    impact=Level.HIGH,
                    urls=[page.final_url],
                )
            ]
        return [self.passed("Your homepage names its preferred address correctly.", self.WHY)]


class RobotsTxt(Check):
    id = "seo.robots_txt"
    category = Category.SEO
    title = "robots.txt"
    weight = 5

    WHY = (
        "robots.txt is a small file that tells search engines which parts of your site they may "
        "visit. Without it they guess; with a mistake in it they may skip your whole site."
    )

    def run(self, ctx: AuditContext) -> list[Finding]:
        robots = ctx.robots
        if not robots.exists:
            return [
                self.finding(
                    Severity.WARN,
                    "Your website has no robots.txt file.",
                    self.WHY,
                    'Create /robots.txt containing at least "User-agent: *", "Allow: /" and a '
                    '"Sitemap:" line with your sitemap address.',
                    impact=Level.LOW,
                    urls=[robots.url],
                )
            ]
        if not robots.allows("Googlebot", ctx.homepage.final_url):
            return [
                self.finding(
                    Severity.FAIL,
                    "Your robots.txt tells Google not to visit your homepage.",
                    "Google can't show pages it isn't allowed to read, so your site may vanish "
                    "from search results.",
                    'Remove the "Disallow: /" rule that applies to Googlebot or "*".',
                    impact=Level.HIGH,
                    urls=[robots.url],
                )
            ]
        return [self.passed("Your robots.txt lets search engines in.", self.WHY, [robots.url])]


class Sitemap(Check):
    id = "seo.sitemap"
    category = Category.SEO
    title = "Sitemap"
    weight = 4

    WHY = (
        "A sitemap is a list of all your pages for search engines. It helps Google find new "
        "and updated pages faster, especially ones that few other pages link to."
    )

    def run(self, ctx: AuditContext) -> list[Finding]:
        sitemap = ctx.sitemap
        if not sitemap.found:
            return [
                self.finding(
                    Severity.WARN,
                    "We couldn't find a sitemap for your website.",
                    self.WHY,
                    "Create /sitemap.xml (most website builders and SEO plugins can do this "
                    'automatically) and add a "Sitemap:" line to robots.txt.',
                    impact=Level.MEDIUM,
                    urls=sitemap.checked or [f"{origin(ctx.homepage.final_url)}/sitemap.xml"],
                )
            ]
        if not sitemap.urls:
            return [
                self.finding(
                    Severity.WARN,
                    "Your sitemap exists but lists no pages.",
                    self.WHY,
                    "Make sure your sitemap lists every page you want people to find on Google.",
                    impact=Level.MEDIUM,
                    urls=sitemap.checked,
                )
            ]
        findings = [
            self.passed(f"Your sitemap lists {len(sitemap.urls)} pages.", self.WHY, sitemap.checked)
        ]
        if ctx.robots.exists and not ctx.robots.sitemaps:
            findings.append(
                self.finding(
                    Severity.INFO,
                    "Your robots.txt doesn't mention your sitemap.",
                    self.WHY,
                    f'Add the line "Sitemap: {sitemap.checked[0]}" to robots.txt.',
                    impact=Level.LOW,
                    urls=[ctx.robots.url],
                )
            )
        return findings


class Indexable(Check):
    id = "seo.indexable"
    category = Category.SEO
    title = "Visible to Google"
    weight = 9

    WHY = (
        'A "noindex" instruction tells Google to keep a page out of search results completely. '
        "It's useful for thank-you pages, but a disaster on your homepage."
    )

    @staticmethod
    def has_noindex(robots_value: str | None) -> bool:
        return robots_value is not None and "noindex" in robots_value.lower()

    def run(self, ctx: AuditContext) -> list[Finding]:
        hidden = []
        for page in ctx.html_pages:
            tree = ctx.tree(page)
            if (
                self.has_noindex(meta_content(tree, "robots"))
                or self.has_noindex(meta_content(tree, "googlebot"))
                or self.has_noindex(page.headers.get("x-robots-tag"))
            ):
                hidden.append(page.final_url)

        if ctx.homepage.final_url in hidden:
            return [
                self.finding(
                    Severity.FAIL,
                    "Your homepage tells Google not to show it in search results.",
                    self.WHY,
                    'Remove "noindex" from the robots meta tag or the X-Robots-Tag header. On '
                    'WordPress, untick "Discourage search engines" under Settings > Reading.',
                    impact=Level.HIGH,
                    urls=hidden,
                )
            ]
        if hidden:
            return [
                self.finding(
                    Severity.INFO,
                    f'{len(hidden)} page(s) are hidden from Google with "noindex". '
                    "Check this is intentional.",
                    self.WHY,
                    'If these pages should appear in Google, remove "noindex" from them.',
                    impact=Level.LOW,
                    urls=hidden,
                )
            ]
        return [self.passed("Google is allowed to show all the pages we checked.", self.WHY)]


class SocialTags(Check):
    """Link previews on every page: the picture, title and text shown when it's shared."""

    id = "seo.social_tags"  # kept from the first version so old reports still match
    category = Category.SEO
    title = "Link previews"
    weight = 4

    WHY = (
        "When someone shares your website on Facebook, WhatsApp, LinkedIn or X, these tags "
        "decide the picture, title and text in the preview. A big picture and a clear title "
        "get far more clicks than a plain grey link."
    )
    FIX = (
        "Below is the complete set of preview tags for each page, with what the page already "
        'has kept. Paste it inside <head> (or fill in your website builder\'s "social sharing" '
        f'settings), replace every "REPLACE: ..." value, and use a {preview.IMAGE_SIZE_HINT} '
        "picture. Then check the result with a link preview tester such as "
        "https://www.opengraph.xyz"
    )

    def run(self, ctx: AuditContext) -> list[Finding]:
        home = ctx.homepage.final_url
        site = schema.site_facts(home, ctx.tree(ctx.homepage))
        lacking: dict[str, list[str]] = {}
        snippets: list[Snippet] = []
        for page in ctx.html_pages:
            tree = ctx.tree(page)
            tags = preview.read_tags(tree)
            problems = tags.missing()
            if tags.image_is_relative:
                problems.append("og:image is not a full address")
            if not problems:
                continue
            lacking[page.final_url] = problems
            is_article = schema.classify(page.final_url, tree, homepage_url=home) == "article"
            snippets.append(
                Snippet(
                    title=f"{page.final_url} {schema.EM_DASH} {', '.join(problems)}",
                    code=preview.suggestion(
                        page.final_url, tags, site_name=site.name, is_article=is_article
                    ),
                )
            )

        total = len(ctx.html_pages)
        self.partial = share_score(total, 0, len(lacking))
        findings: list[Finding] = []
        home_missing = lacking.get(home, [])
        if len(home_missing) == len(preview.REQUIRED):
            message = "Your homepage has no link preview tags, so shared links look plain."
        elif total == 1 and home_missing:
            message = (
                f"Your homepage's link preview is incomplete (missing: {', '.join(home_missing)})."
            )
        else:
            message = on_pages(
                len(lacking),
                total,
                "has an incomplete link preview.",
                "have incomplete link previews.",
            )
        if lacking:
            findings.append(
                self.finding(
                    Severity.WARN,
                    message,
                    self.WHY,
                    self.FIX,
                    impact=Level.MEDIUM if home in lacking else Level.LOW,
                    urls=list(lacking),
                    snippets=snippets[:MAX_SNIPPETS],
                )
            )
        broken = self.broken_image(ctx)
        if broken:
            findings.append(
                self.finding(
                    Severity.WARN,
                    f"Your homepage's preview picture {broken}, so shared links show no image.",
                    self.WHY,
                    f"Upload a JPG or PNG picture of {preview.IMAGE_SIZE_HINT} (under 5 MB), "
                    "check that its address opens in a browser, and put that full address in "
                    "the og:image tag.",
                    impact=Level.MEDIUM,
                    urls=[ctx.probes.og_image_url],
                )
            )
        return findings or [self.passed("Every page has a complete link preview.", self.WHY)]

    @staticmethod
    def broken_image(ctx: AuditContext) -> str:
        """Why the homepage's preview picture can't be shown ("" if it's fine or unknown)."""
        probes = ctx.probes
        if not ctx.has(PROBES) or not probes.og_image_url:
            return ""
        if probes.og_image_status == 0:
            return "can't be reached"
        if probes.og_image_status >= 400:
            return f"is missing (error {probes.og_image_status})"
        if not probes.og_image_type:
            return "isn't a JPG, PNG, GIF or WebP picture"
        if probes.og_image_too_big:
            return "is larger than 5 MB"
        return ""


class PageSchema(Check):
    """Does every page carry the right, complete structured data? Suggests it when not."""

    id = "seo.page_schema"
    category = Category.SEO
    title = "Page schema"
    weight = 4

    WHY = (
        "Structured data (schema.org JSON-LD) tells Google and AI assistants exactly what each "
        "page is: your business and its contact details, an article and its author, a product "
        "and its price. It earns richer search results (stars, prices, FAQs, breadcrumbs) and "
        "makes AI answers quote your real details."
    )
    FIX = (
        "Below is a complete JSON-LD block for each page. Paste it into that page's <head> (or "
        "ask your developer, or use your website builder's SEO settings), replace every "
        '"REPLACE: ..." value with your real details, then test the page with '
        "Google's Rich Results Test: https://search.google.com/test/rich-results"
    )

    def run(self, ctx: AuditContext) -> list[Finding]:
        home_url = ctx.homepage.final_url
        site = schema.site_facts(home_url, ctx.tree(ctx.homepage))
        results = [
            schema.analyse(page.final_url, ctx.tree(page), homepage_url=home_url, site=site)
            for page in ctx.html_pages
        ]
        broken = [r for r in results if r.status == "broken"]
        lacking = [r for r in results if r.status in ("missing", "incomplete")]
        richer = [r for r in results if r.status == "could be richer"]
        findings: list[Finding] = []

        if broken:
            findings.append(
                self.finding(
                    Severity.FAIL,
                    on_pages(
                        len(broken),
                        len(results),
                        "has broken structured data (invalid JSON), so Google ignores it.",
                        "have broken structured data (invalid JSON), so Google ignores it.",
                    ),
                    self.WHY,
                    "Fix the JSON syntax (a missing comma or quote is typical), or replace it with "
                    "the complete block below. " + self.FIX,
                    effort=Level.LOW,
                    impact=Level.MEDIUM,
                    urls=[r.url for r in broken],
                    snippets=self.snippets(broken),
                )
            )
        if lacking:
            home_lacking = any(r.kind == "home" for r in lacking)
            findings.append(
                self.finding(
                    Severity.WARN,
                    on_pages(
                        len(lacking),
                        len(results),
                        "is missing the structured data it should have, or has it incomplete.",
                        "are missing the structured data they should have, or have it incomplete.",
                    ),
                    self.WHY,
                    self.FIX,
                    effort=Level.LOW,
                    impact=Level.MEDIUM if home_lacking else Level.LOW,
                    urls=[r.url for r in lacking],
                    snippets=self.snippets(lacking),
                )
            )
        if richer:
            findings.append(
                self.finding(
                    Severity.INFO,
                    on_pages(
                        len(richer),
                        len(results),
                        "has valid structured data that could be richer.",
                        "have valid structured data that could be richer.",
                    ),
                    self.WHY,
                    "Optional extras Google can use. " + self.FIX,
                    effort=Level.LOW,
                    impact=Level.LOW,
                    urls=[r.url for r in richer],
                    snippets=self.snippets(richer),
                )
            )
        if findings:
            return findings
        types = sorted({t for r in results for t in r.found})
        return [
            self.passed(
                f"Every page has complete structured data ({', '.join(types)}).",
                self.WHY,
                urls=[r.url for r in results],
            )
        ]

    @staticmethod
    def snippets(results: list[schema.PageSchema]) -> list[Snippet]:
        return [
            Snippet(
                title=f"{r.kind_label} {schema.MIDDLE_DOT} {r.url} {schema.EM_DASH} {r.summary()}",
                code=r.suggestion,
            )
            for r in results
            if r.suggestion
        ]


class BrokenLinks(Check):
    id = "seo.broken_links"
    category = Category.SEO
    title = "Broken links"
    weight = 6
    requires = frozenset({PROBES})

    WHY = (
        'Links that lead to "page not found" frustrate visitors, make your business look '
        "neglected and waste the attention Google gives your site."
    )

    def run(self, ctx: AuditContext) -> list[Finding]:
        statuses = ctx.probes.link_status
        if len(statuses) <= 1:  # only the homepage itself: nothing to judge
            return []
        broken = sorted(url for url, code in statuses.items() if code == 0 or code >= 400)
        self.partial = share_score(len(statuses), len(broken))
        if not broken:
            return [self.passed(f"All {len(statuses)} internal links we checked work.", self.WHY)]

        on = sorted({p for url in broken for p in ctx.probes.link_sources.get(url, [])})
        where = f" They appear on {len(on)} page(s)." if on else ""
        return [
            self.finding(
                Severity.FAIL,
                f"{len(broken)} of the {len(statuses)} internal links we checked are "
                f"broken.{where}",
                self.WHY,
                "Update each link to the right page, or redirect the old address (301) to its "
                "new location.",
                effort=Level.LOW if len(broken) <= 5 else Level.MEDIUM,
                impact=Level.MEDIUM,
                urls=broken,
            )
        ]


class DuplicateTitles(Check):
    id = "seo.duplicate_titles"
    category = Category.SEO
    title = "Unique page titles"
    weight = 4

    WHY = (
        "When several pages share the same title, Google can't tell them apart and may show "
        "the wrong one, or none, for a search."
    )

    def run(self, ctx: AuditContext) -> list[Finding]:
        pages = ctx.html_pages
        if len(pages) < 2:
            return []
        by_title: dict[str, list[str]] = defaultdict(list)
        for page in pages:
            text = title_text(ctx.tree(page)).strip().lower()
            if text:
                by_title[text].append(page.final_url)
        duplicates = [urls for urls in by_title.values() if len(urls) > 1]
        if not duplicates:
            return [self.passed("Every page we checked has its own title.", self.WHY)]
        affected = sorted(url for urls in duplicates for url in urls)
        return [
            self.finding(
                Severity.WARN,
                f"{len(affected)} pages share the same title with another page.",
                self.WHY,
                "Give each page a title that describes what is different about it.",
                impact=Level.MEDIUM,
                urls=affected,
            )
        ]
