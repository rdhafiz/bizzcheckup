"""Technical SEO checks: headings, images, page addresses and meta tags, page by page.

They go deeper than the basic SEO checks in seo.py: each one reviews every page we
crawled and, where it helps, adds a page-by-page breakdown (a Snippet) to the report.
"""

import re
from collections import defaultdict
from html import escape
from itertools import pairwise
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from selectolax.lexbor import LexborHTMLParser, LexborNode

from ..context import AuditContext
from ..crawler import extract_links
from ..types import Category, Finding, Level, Page, Severity, Snippet
from ..urls import same_origin
from ._helpers import (
    links_with_rel,
    meta_content,
    meta_http_equiv,
    on_pages,
    share_score,
    title_text,
)
from .base import Check

MAX_LISTED = 20  # rows shown in one page-by-page breakdown
EM_DASH = chr(0x2014)


def heading_text(node: LexborNode) -> str:
    """A heading's text; an image inside it counts with its alt text."""
    text = node.text(strip=True)
    if not text:
        image = node.css_first("img[alt]")
        text = (image.attributes.get("alt") or "").strip() if image else ""
    return " ".join(text.split())


# --- headings -----------------------------------------------------------------------------


class HeadingStructure(Check):
    """Reviews each page's outline: empty, duplicate, out-of-order or overlong headings."""

    id = "seo.heading_structure"
    category = Category.SEO
    title = "Heading structure"
    weight = 4

    WHY = (
        "Headings are the outline of a page. Google reads them to understand what each "
        "section is about, and visitors skim them to find what they came for. Empty, "
        "repeated or jumbled headings hide your best content from both."
    )
    FIX = (
        "Below is the outline of each page as Google sees it, with the problems marked. "
        "Give every page one H1 that states its topic (different on every page), then H2 "
        "for each section and H3 inside those. Every heading needs real words."
    )
    H1_MAX = 70  # characters
    LONG_PAGE_WORDS = 300  # a page this long needs sections

    def run(self, ctx: AuditContext) -> list[Finding]:
        outlines: dict[str, list[tuple[int, str]]] = {}
        words: dict[str, int] = {}
        for page in ctx.html_pages:
            tree = ctx.dom(page)
            nodes = tree.css("h1, h2, h3, h4, h5, h6")
            outlines[page.final_url] = [(int((n.tag or "h0")[1]), heading_text(n)) for n in nodes]
            body = tree.body
            words[page.final_url] = len(body.text(separator=" ").split()) if body else 0

        h1_pages: dict[str, list[str]] = defaultdict(list)
        for url, outline in outlines.items():
            for level, text in outline:
                if level == 1 and text:
                    h1_pages[text.lower()].append(url)
        shared_h1 = {text for text, urls in h1_pages.items() if len(urls) > 1}

        problems: dict[str, list[str]] = {}  # url -> problems (serious ones)
        notes: dict[str, list[str]] = {}  # url -> minor notes
        for url, outline in outlines.items():
            serious, minor = self.review(outline, words[url], shared_h1)
            if serious:
                problems[url] = serious
            if minor:
                notes[url] = minor

        reviewed = [url for url, outline in outlines.items() if outline]
        if not reviewed:
            return []  # no headings at all: seo.single_h1 already reports that
        self.partial = share_score(len(reviewed), 0, len(problems))
        flagged = [url for url in outlines if url in problems or url in notes]
        snippets = [
            Snippet(
                title=f"{url} {EM_DASH} {', '.join(problems.get(url, []) + notes.get(url, []))}",
                code=self.outline_text(outlines[url], shared_h1),
                language="text",
            )
            for url in flagged[:MAX_LISTED]
        ]
        total = len(outlines)
        if problems:
            return [
                self.finding(
                    Severity.WARN,
                    on_pages(
                        len(problems),
                        total,
                        "has headings that confuse its structure (empty, repeated or out of "
                        "order).",
                        "have headings that confuse their structure (empty, repeated or out of "
                        "order).",
                    ),
                    self.WHY,
                    self.FIX,
                    impact=Level.MEDIUM if ctx.homepage.final_url in problems else Level.LOW,
                    urls=list(problems),
                    snippets=snippets,
                )
            ]
        if notes:
            return [
                self.finding(
                    Severity.INFO,
                    on_pages(
                        len(notes),
                        total,
                        "has a heading structure that could be clearer.",
                        "have a heading structure that could be clearer.",
                    ),
                    self.WHY,
                    self.FIX,
                    impact=Level.LOW,
                    urls=list(notes),
                    snippets=snippets,
                )
            ]
        return [self.passed("Every page has a clear, well-ordered heading outline.", self.WHY)]

    def review(
        self, outline: list[tuple[int, str]], words: int, shared_h1: set[str]
    ) -> tuple[list[str], list[str]]:
        serious: list[str] = []
        minor: list[str] = []
        if not outline:
            return serious, minor
        empty = sum(1 for _, text in outline if not text)
        if empty:
            serious.append(f"{empty} empty heading{'s' if empty > 1 else ''}")
        h1s = [text for level, text in outline if level == 1]
        if any(text.lower() in shared_h1 for text in h1s):
            serious.append("same H1 as another page")
        if h1s and outline[0][0] != 1:
            serious.append("H1 isn't the first heading")
        # Reported in detail by seo.single_h1 and accessibility.heading_order, so here
        # they're only notes that explain the outline.
        if not h1s:
            minor.append("no H1")
        elif len(h1s) > 1:
            minor.append(f"{len(h1s)} H1s")
        if any(current > previous + 1 for (previous, _), (current, _) in pairwise(outline)):
            minor.append("skipped heading levels")
        if any(len(text) > self.H1_MAX for text in h1s):
            minor.append(f"H1 longer than {self.H1_MAX} characters")
        if words >= self.LONG_PAGE_WORDS and not any(level == 2 for level, _ in outline):
            minor.append("long page without H2 sections")
        return serious, minor

    @staticmethod
    def outline_text(outline: list[tuple[int, str]], shared_h1: set[str]) -> str:
        lines: list[str] = []
        previous = 0
        h1_count = sum(1 for level, _ in outline if level == 1)
        for index, (level, text) in enumerate(outline):
            marks: list[str] = []
            if not text:
                marks.append("empty")
            if level == 1 and h1_count > 1:
                marks.append(f"one of {h1_count} H1s")
            if level == 1 and text.lower() in shared_h1:
                marks.append("also the H1 of another page")
            if level == 1 and index > 0 and outline[0][0] != 1 and h1_count == 1:
                marks.append("should come first")
            if previous and level > previous + 1:
                marks.append(f"skips H{previous + 1}")
            previous = level
            shown = text if len(text) <= 80 else text[:77] + "..."
            line = f"{'  ' * (level - 1)}H{level}  {shown or '(no text)'}"
            lines.append(f"{line}   <-- {', '.join(marks)}" if marks else line)
        return "\n".join(lines)


# --- images -------------------------------------------------------------------------------

IMAGE_FILE = re.compile(r"\.(jpe?g|png|gif|webp|avif|svg|bmp|tiff?)$", re.IGNORECASE)
GENERIC_ALT = {
    "image", "img", "photo", "picture", "pic", "banner", "icon", "graphic", "untitled",
    "placeholder", "thumbnail", "slide", "slider", "hero", "background", "default",
}  # fmt: skip
CAMERA_NAME = re.compile(
    r"^(img|dsc|dscn|dcim|pxl|photo|image|screenshot|screen shot|whatsapp image|untitled)"
    r"[\s_-]*\d|^[0-9a-f]{16,}$|^\d+$|^(image|img|pic|photo)\d*$",
    re.IGNORECASE,
)
ALT_MAX = 125  # screen readers read longer text in one breath; keep it short


def file_stem(src: str) -> str:
    name = urlsplit(src).path.rsplit("/", 1)[-1]
    return IMAGE_FILE.sub("", name)


def alt_problem(alt: str | None) -> str:
    """What's wrong with an image's alt text ("" = nothing). None means no alt attribute."""
    if alt is None:
        return "no alt text"
    text = alt.strip()
    if not text:
        return ""  # alt="" marks a decorative image: correct
    if text.lower().strip(" .") in GENERIC_ALT:
        return f'alt text "{text}" says nothing'
    if IMAGE_FILE.search(text) or CAMERA_NAME.search(text):
        return "alt text is a file name"
    return ""


class ImageSeo(Check):
    """Alt text that actually describes the picture, and descriptive image file names."""

    id = "seo.image_seo"
    category = Category.SEO
    title = "Image descriptions and file names"
    weight = 4

    WHY = (
        "Google can't see pictures: it reads the alt text and the file name to know what "
        'an image shows. "IMG_4821.jpg" with alt="image" tells it nothing, so your photos '
        "never appear in Google Images and the page loses relevance."
    )
    FIX = (
        "For each image listed below, write alt text that describes what it shows in a few "
        'words, e.g. alt="Chocolate birthday cake with strawberries" (alt="" only for pure '
        "decoration), and give image files descriptive names before uploading, e.g. "
        '"chocolate-birthday-cake.jpg".'
    )

    def run(self, ctx: AuditContext) -> list[Finding]:
        bad: dict[str, list[str]] = {}  # url -> lines for the breakdown (alt problems)
        minor: dict[str, list[str]] = {}  # url -> lines (file names, long alt)
        total = flagged = 0
        for page in ctx.html_pages:
            for img in ctx.dom(page).css("img"):
                src = (img.attributes.get("src") or img.attributes.get("data-src") or "").strip()
                if not src or src.startswith("data:"):
                    continue
                total += 1
                alt = img.attributes.get("alt")
                problem = alt_problem(alt)
                notes: list[str] = []
                if alt and len(alt.strip()) > ALT_MAX:
                    notes.append(f"alt text longer than {ALT_MAX} characters")
                if CAMERA_NAME.search(file_stem(src)):
                    notes.append("file name doesn't describe the image")
                if problem:
                    flagged += 1
                    bad.setdefault(page.final_url, []).append(self.row(src, alt, [problem, *notes]))
                elif notes:
                    minor.setdefault(page.final_url, []).append(self.row(src, alt, notes))
        if total == 0:
            return []
        self.partial = share_score(total, 0, flagged)
        pages = len(ctx.html_pages)
        snippets = self.breakdown(bad, minor)
        if bad:
            return [
                self.finding(
                    Severity.WARN,
                    f"{flagged} of your {total} images have no useful description for Google "
                    '(missing, a file name, or a word like "image").',
                    self.WHY,
                    self.FIX,
                    effort=Level.LOW if flagged <= 10 else Level.MEDIUM,
                    impact=Level.MEDIUM,
                    urls=list(bad),
                    snippets=snippets,
                )
            ]
        if minor:
            count = sum(len(rows) for rows in minor.values())
            return [
                self.finding(
                    Severity.INFO,
                    f"{count} of your {total} images could be easier for Google to understand "
                    "(file names or very long descriptions).",
                    self.WHY,
                    self.FIX,
                    impact=Level.LOW,
                    urls=list(minor),
                    snippets=snippets,
                )
            ]
        where = "on your homepage" if pages == 1 else f"on the {pages} pages we checked"
        return [self.passed(f"All {total} images {where} are well described.", self.WHY)]

    @staticmethod
    def row(src: str, alt: str | None, problems: list[str]) -> str:
        shown_alt = "(none)" if alt is None else f'"{alt.strip()}"'
        return f"{src}\n    alt: {shown_alt}\n    fix: {'; '.join(problems)}"

    @staticmethod
    def breakdown(bad: dict[str, list[str]], minor: dict[str, list[str]]) -> list[Snippet]:
        snippets: list[Snippet] = []
        for url in list(dict.fromkeys([*bad, *minor]))[:MAX_LISTED]:
            rows = bad.get(url, []) + minor.get(url, [])
            more = f"\n... and {len(rows) - MAX_LISTED} more" if len(rows) > MAX_LISTED else ""
            noun = "image" if len(rows) == 1 else "images"
            snippets.append(
                Snippet(
                    title=f"{url} {EM_DASH} {len(rows)} {noun} to improve",
                    code="\n\n".join(rows[:MAX_LISTED]) + more,
                    language="text",
                )
            )
        return snippets


# --- page addresses -----------------------------------------------------------------------

SESSION_PARAMS = {"sid", "sessionid", "session_id", "phpsessid", "jsessionid", "aspsessionid"}
TRACKING_PREFIXES = ("utm_", "fbclid", "gclid", "mc_")
URL_MAX = 115  # characters; longer addresses get cut off in search results
DEPTH_MAX = 4  # folders
OLD_EXTENSIONS = (".php", ".asp", ".aspx", ".jsp", ".cfm", ".html", ".htm")


def url_problems(url: str, *, https_site: bool) -> tuple[list[str], list[str]]:
    """(problems, notes) for one internal address."""
    parts = urlsplit(url)
    path = parts.path
    problems: list[str] = []
    notes: list[str] = []
    if any(c.isupper() for c in path):
        problems.append("capital letters")
    if "_" in path:
        problems.append("underscores instead of hyphens")
    if "%20" in path or " " in path or "+" in path:
        problems.append("spaces")
    if "//" in path:
        problems.append("double slash")
    query = parse_qsl(parts.query, keep_blank_values=True)
    if any(key.lower() in SESSION_PARAMS for key, _ in query):
        problems.append("session id in the address")
    if https_site and parts.scheme == "http":
        problems.append("links to the insecure http:// version")
    if len(url) > URL_MAX:
        notes.append(f"longer than {URL_MAX} characters")
    if len([part for part in path.split("/") if part]) > DEPTH_MAX:
        notes.append(f"more than {DEPTH_MAX} folders deep")
    if len([key for key, _ in query if not key.lower().startswith(TRACKING_PREFIXES)]) > 2:
        notes.append("many ? parameters")
    if path.lower().endswith(OLD_EXTENSIONS):
        notes.append(f"technical ending ({path.rsplit('.', 1)[-1].lower()})")
    return problems, notes


def clean_url(url: str) -> str:
    """The same address following the usual rules: lowercase, hyphens, no session ids."""
    parts = urlsplit(url)
    path = parts.path.lower().replace("%20", "-").replace("+", "-").replace(" ", "-")
    path = re.sub(r"_+", "-", path)
    path = re.sub(r"/{2,}", "/", path)
    path = re.sub(r"-{2,}", "-", path)
    query = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in SESSION_PARAMS
    ]
    return urlunsplit(("https", parts.netloc, path or "/", urlencode(query), ""))


class UrlStructure(Check):
    """Short, lowercase, hyphenated addresses without session ids."""

    id = "seo.url_structure"
    category = Category.SEO
    title = "Clean page addresses (URLs)"
    weight = 3

    WHY = (
        "A clean address like /wedding-cakes is easy to read, share and trust, and its words "
        "help Google understand the page. Capital letters, underscores, spaces and session "
        "ids create duplicate copies of pages and look broken when shared."
    )
    FIX = (
        "Use short addresses in lowercase with hyphens between words, e.g. /wedding-cakes. "
        "Below is each address with a suggested clean version. When you change an address, "
        "redirect the old one to the new one (301) so links and rankings carry over."
    )

    def run(self, ctx: AuditContext) -> list[Finding]:
        home = ctx.homepage.final_url
        https_site = home.startswith("https://")
        found: dict[str, None] = {page.final_url: None for page in ctx.html_pages}
        for page in ctx.html_pages:
            for link in extract_links(page):
                link = link.split("#")[0]
                if same_origin(link, home) or same_origin(link.replace("http:", "https:", 1), home):
                    found.setdefault(link, None)
        urls = list(found)

        rows: dict[str, tuple[list[str], list[str]]] = {}
        for url in urls:
            problems, notes = url_problems(url, https_site=https_site)
            if problems or notes:
                rows[url] = (problems, notes)
        bad = [url for url, (problems, _) in rows.items() if problems]
        self.partial = share_score(len(urls), 0, len(bad))
        if not rows:
            return [self.passed(f"All {len(urls)} page addresses we found are clean.", self.WHY)]
        lines = [self.row(url, *rows[url]) for url in [*bad, *(u for u in rows if u not in bad)]]
        snippet = Snippet(
            title=f"{len(rows)} of {len(urls)} addresses {EM_DASH} with a suggested clean version",
            code="\n\n".join(lines[:MAX_LISTED])
            + (f"\n\n... and {len(lines) - MAX_LISTED} more" if len(lines) > MAX_LISTED else ""),
            language="text",
        )
        if bad:
            return [
                self.finding(
                    Severity.WARN,
                    f"{len(bad)} of the {len(urls)} page addresses we found break the usual "
                    "rules (capital letters, underscores, spaces, session ids or http://).",
                    self.WHY,
                    self.FIX,
                    effort=Level.MEDIUM,
                    impact=Level.LOW,
                    urls=bad,
                    snippets=[snippet],
                )
            ]
        return [
            self.finding(
                Severity.INFO,
                f"{len(rows)} of the {len(urls)} page addresses we found could be shorter "
                "or simpler.",
                self.WHY,
                self.FIX,
                impact=Level.LOW,
                urls=list(rows),
                snippets=[snippet],
            )
        ]

    @staticmethod
    def row(url: str, problems: list[str], notes: list[str]) -> str:
        line = f"{url}\n    issue: {', '.join(problems + notes)}"
        suggestion = clean_url(url)
        if problems and suggestion != url:
            line += f"\n    suggested: {suggestion}"
        return line


# --- meta tags ----------------------------------------------------------------------------


class MetaTags(Check):
    """The core <head> tags every page needs, with a ready-made block per page."""

    id = "seo.meta_tags"
    category = Category.SEO
    title = "Essential meta tags"
    weight = 4

    WHY = (
        "Meta tags are the hidden labels in each page's <head>. They tell Google the page's "
        "title, summary, language and preferred address, and tell phones how to display it. "
        "A page missing them can be shown badly in search, or not at all."
    )
    FIX = (
        "Below is a complete set of tags for each page, with the values the page already has "
        "kept. Paste it inside <head> (or fill in the same fields in your website builder's "
        'SEO settings), replace every "REPLACE: ..." value, and remove the duplicates of any '
        "tag the page already had."
    )
    CORE = ("title", "description", "viewport", "charset", "canonical")

    def run(self, ctx: AuditContext) -> list[Finding]:
        site_name = title_text(ctx.tree(ctx.homepage)).split("|")[-1].strip()
        missing: dict[str, list[str]] = {}
        refresh: list[str] = []
        snippets: list[Snippet] = []
        for page in ctx.html_pages:
            tree = ctx.tree(page)
            tags = self.present(tree)
            gone = [name for name in (*self.CORE, "lang") if not tags[name]]
            if gone:
                missing[page.final_url] = gone
                snippets.append(
                    Snippet(
                        title=f"{page.final_url} {EM_DASH} missing {', '.join(gone)}",
                        code=self.suggestion(page, tree, site_name),
                    )
                )
            if meta_http_equiv(tree, "refresh") is not None:
                refresh.append(page.final_url)

        total = len(ctx.html_pages)
        core_missing = [url for url, gone in missing.items() if set(gone) & set(self.CORE)]
        self.partial = share_score(total, 0, len(core_missing) + len(refresh))
        findings: list[Finding] = []
        if core_missing:
            findings.append(
                self.finding(
                    Severity.WARN,
                    on_pages(
                        len(core_missing),
                        total,
                        "is missing essential meta tags.",
                        "are missing essential meta tags.",
                    ),
                    self.WHY,
                    self.FIX,
                    impact=Level.MEDIUM,
                    urls=core_missing,
                    snippets=snippets[:MAX_LISTED],
                )
            )
        elif missing:
            findings.append(
                self.finding(
                    Severity.INFO,
                    on_pages(
                        len(missing),
                        total,
                        "doesn't say which language it is in.",
                        "don't say which language they are in.",
                    ),
                    self.WHY,
                    'Add the language to the <html> tag, e.g. <html lang="en">.',
                    impact=Level.LOW,
                    urls=list(missing),
                )
            )
        if refresh:
            findings.append(
                self.finding(
                    Severity.WARN,
                    on_pages(
                        len(refresh),
                        total,
                        "reloads or redirects itself with a meta refresh tag.",
                        "reload or redirect themselves with a meta refresh tag.",
                    ),
                    "Pages that jump somewhere else after a few seconds confuse visitors and "
                    "Google, which may ignore the page.",
                    'Remove <meta http-equiv="refresh">. To move a page, use a 301 redirect on '
                    "the server instead.",
                    impact=Level.LOW,
                    urls=refresh,
                )
            )
        return findings or [self.passed("Every page has its essential meta tags.", self.WHY)]

    @staticmethod
    def present(tree: LexborHTMLParser) -> dict[str, bool]:
        html = tree.css_first("html")
        return {
            "title": bool(title_text(tree)),
            "description": bool(meta_content(tree, "description")),
            "viewport": bool(meta_content(tree, "viewport")),
            "charset": bool(tree.css_first("meta[charset]"))
            or "charset" in (meta_http_equiv(tree, "content-type") or "").lower(),
            "canonical": bool(links_with_rel(tree, "canonical")),
            "lang": bool(html and (html.attributes.get("lang") or "").strip()),
        }

    @staticmethod
    def suggestion(page: Page, tree: LexborHTMLParser, site_name: str) -> str:
        def attr(value: str) -> str:
            return escape(value, quote=True)

        title = title_text(tree) or f"REPLACE: what this page offers | {site_name or 'Your brand'}"
        description = meta_content(tree, "description") or (
            "REPLACE: 140-160 characters that sum up this page and give a reason to visit"
        )
        canonical = links_with_rel(tree, "canonical")
        href = (canonical[0].attributes.get("href") or "") if canonical else ""
        href = href if href.startswith(("http://", "https://")) else page.final_url
        html = tree.css_first("html")
        lang = (html.attributes.get("lang") or "").strip() if html else ""
        lines = [
            f'<html lang="{attr(lang or "REPLACE: language code, e.g. en")}">',
            "<head>",
            '  <meta charset="utf-8">',
            '  <meta name="viewport" content="width=device-width, initial-scale=1">',
            f"  <title>{escape(title, quote=False)}</title>",
            f'  <meta name="description" content="{attr(description)}">',
            f'  <link rel="canonical" href="{attr(href)}">',
        ]
        robots = meta_content(tree, "robots")
        if robots:
            lines.append(f'  <meta name="robots" content="{attr(robots)}">')
        lines.append("</head>")
        return "\n".join(lines)
