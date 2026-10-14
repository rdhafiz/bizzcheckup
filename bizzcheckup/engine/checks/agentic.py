"""Agentic browsing checks: can AI assistants find, read and recommend your business?

People increasingly ask ChatGPT, Claude, Perplexity or Google's AI answers
instead of searching. These checks look at what those systems need: being
allowed in, getting real content without JavaScript, and machine-readable facts.
"""

import json
import re
from datetime import UTC, datetime
from typing import ClassVar

from selectolax.lexbor import LexborHTMLParser

from ..config import AI_CRAWLERS
from ..context import PROBES, RENDER, AuditContext
from ..schema import question_answers, read_json_ld, site_facts, types_of
from ..types import AgentProbe, Category, Finding, Level, Severity, Snippet
from ..urls import origin
from .accessibility import accessible_text
from .base import Check
from .local import visible_text

AI_WHY = (
    "More and more customers ask AI assistants like ChatGPT, Claude or Perplexity for "
    "recommendations instead of searching Google. If those assistants can't read your site, "
    "they recommend your competitors."
)


class LlmsTxt(Check):
    id = "agentic.llms_txt"
    category = Category.AGENTIC
    title = "AI guide (llms.txt)"
    weight = 5
    requires = frozenset({PROBES})

    WHY = (
        "llms.txt is a new, simple standard: a short plain-text guide to your business and its "
        "most important pages, written for AI assistants. It helps them describe you "
        "correctly instead of guessing."
    )
    FIX = (
        'Create /llms.txt in Markdown: a first line "# Your Business Name", a one-sentence '
        'summary starting with ">", then links to your key pages (services, prices, contact). '
        "Format: https://llmstxt.org"
    )

    def run(self, ctx: AuditContext) -> list[Finding]:
        text = ctx.probes.llms_txt_text.strip()
        if not text:
            return [
                self.finding(
                    Severity.WARN,
                    "Your website has no llms.txt guide for AI assistants.",
                    self.WHY,
                    self.FIX,
                    impact=Level.MEDIUM,
                    urls=[f"{origin(ctx.homepage.final_url)}/llms.txt"],
                )
            ]
        findings = [self.passed("Your website has an llms.txt guide for AI assistants.", self.WHY)]
        if not text.startswith("# "):
            findings.append(
                self.finding(
                    Severity.INFO,
                    'Your llms.txt doesn\'t start with a "# Business Name" heading.',
                    self.WHY,
                    self.FIX,
                    impact=Level.LOW,
                )
            )
        return findings


class AiCrawlers(Check):
    id = "agentic.ai_crawlers"
    category = Category.AGENTIC
    title = "AI crawlers allowed"
    weight = 8

    def run(self, ctx: AuditContext) -> list[Finding]:
        url = ctx.homepage.final_url
        if not ctx.robots.exists:
            return [
                self.passed(
                    "You have no robots.txt, so all AI crawlers are allowed to read your site.",
                    AI_WHY,
                )
            ]
        blocked = [bot for bot in AI_CRAWLERS if not ctx.robots.allows(bot, url)]
        search = [bot for bot in blocked if AI_CRAWLERS[bot] == "search"]
        training = [bot for bot in blocked if AI_CRAWLERS[bot] == "training"]

        findings = []
        if search:
            findings.append(
                self.finding(
                    Severity.FAIL,
                    f"Your robots.txt blocks AI search assistants ({', '.join(search)}), so "
                    "they can't show your business in their answers.",
                    AI_WHY,
                    f'Remove the "Disallow" rules for {", ".join(search)} in robots.txt. These '
                    "bots fetch pages to answer questions live; they don't train AI models.",
                    impact=Level.HIGH,
                    urls=[ctx.robots.url],
                )
            )
        if training:
            findings.append(
                self.finding(
                    Severity.INFO,
                    f"Your robots.txt blocks AI training crawlers ({', '.join(training)}).",
                    "That's a valid choice if you don't want your content used to train AI "
                    "models, but it can make AI assistants know less about your business.",
                    "Keep the block if it's intentional. Otherwise remove those rules from "
                    "robots.txt.",
                    impact=Level.LOW,
                    urls=[ctx.robots.url],
                )
            )
        if not findings:
            names = ", ".join(AI_CRAWLERS)
            return [self.passed(f"Your robots.txt lets AI crawlers in ({names}).", AI_WHY)]
        return findings


def _blocked(probe: AgentProbe) -> bool:
    return probe.status_code == 0 or probe.status_code >= 400 or probe.challenge


class BotBlocking(Check):
    id = "agentic.bot_blocking"
    category = Category.AGENTIC
    title = "AI assistants not blocked by firewall"
    weight = 8
    requires = frozenset({PROBES})

    WHY = (
        "Many firewalls and CDNs (such as Cloudflare's bot protection) block or challenge AI "
        "assistants by default, even if your robots.txt welcomes them. They then simply can't "
        "read your site."
    )
    FIX = (
        "In your CDN or firewall settings, allow verified AI crawlers (in Cloudflare: Security > "
        'Bots, and check "AI Crawl Control"), or add an exception for their user agents.'
    )

    def run(self, ctx: AuditContext) -> list[Finding]:
        ai, browser = ctx.probes.as_ai_agent, ctx.probes.as_browser
        if ai is None or browser is None:
            return []
        url = [ctx.homepage.final_url]
        if _blocked(ai) and not _blocked(browser):
            reason = (
                'shown a "prove you\'re human" check'
                if ai.challenge
                else f"refused (HTTP {ai.status_code})"
                if ai.status_code
                else "not answered"
            )
            return [
                self.finding(
                    Severity.FAIL,
                    f"When an AI assistant visits your homepage it is {reason}, while normal "
                    "visitors get the page.",
                    self.WHY,
                    self.FIX,
                    impact=Level.HIGH,
                    urls=url,
                )
            ]
        if _blocked(ai) and _blocked(browser):
            return [
                self.finding(
                    Severity.WARN,
                    "Your site turns away automated visitors in general, so AI assistants are "
                    "very likely blocked too.",
                    self.WHY,
                    self.FIX,
                    impact=Level.MEDIUM,
                    urls=url,
                )
            ]
        if browser.text_length and ai.text_length < browser.text_length * 0.5:
            return [
                self.finding(
                    Severity.WARN,
                    "AI assistants receive a much shorter version of your homepage than normal "
                    "visitors.",
                    self.WHY,
                    self.FIX,
                    impact=Level.MEDIUM,
                    urls=url,
                )
            ]
        return [self.passed("AI assistants get the same homepage as normal visitors.", self.WHY)]


class StructuredDataPresent(Check):
    id = "agentic.structured_data"
    category = Category.AGENTIC
    title = "Machine-readable business facts"
    weight = 5

    WHY = (
        "Structured data (JSON-LD) states facts like your business type, address, opening "
        "hours, prices and reviews in a format AI systems read reliably, so they quote your "
        "real details."
    )

    def run(self, ctx: AuditContext) -> list[Finding]:
        types: set[str] = set()
        for node in ctx.dom(ctx.homepage).css('script[type="application/ld+json"]'):
            try:
                data = json.loads(node.text())
            except ValueError:
                continue
            items = data if isinstance(data, list) else data.get("@graph", [data])
            for item in items:
                if isinstance(item, dict) and item.get("@type"):
                    found = item["@type"]
                    types.update(found if isinstance(found, list) else [str(found)])
        if types:
            return [
                self.passed(
                    "Your homepage describes itself in machine-readable form "
                    f"({', '.join(sorted(types))}).",
                    self.WHY,
                )
            ]
        return [
            self.finding(
                Severity.WARN,
                "Your homepage has no machine-readable description of your business.",
                self.WHY,
                'Add a JSON-LD block, e.g. {"@context": "https://schema.org", "@type": '
                '"LocalBusiness", "name": ..., "address": ..., "telephone": ..., '
                '"openingHours": ...}. Many SEO plugins can generate it.',
                effort=Level.MEDIUM,
                impact=Level.MEDIUM,
                urls=[ctx.homepage.final_url],
            )
        ]


class SemanticLandmarks(Check):
    id = "agentic.landmarks"
    category = Category.AGENTIC
    title = "Clear page structure"
    weight = 4

    WHY = (
        "Header, navigation, main content and footer areas tell AI agents (and screen readers) "
        "which part of the page is your actual content and which is menus or small print."
    )
    LANDMARKS: ClassVar[dict[str, str]] = {
        "main": 'main, [role="main"]',
        "nav": 'nav, [role="navigation"]',
        "header": 'header, [role="banner"]',
        "footer": 'footer, [role="contentinfo"]',
    }

    def run(self, ctx: AuditContext) -> list[Finding]:
        tree = ctx.dom(ctx.homepage)
        missing = [
            name for name, selector in self.LANDMARKS.items() if not tree.css_first(selector)
        ]
        self.partial = 1 - len(missing) / len(self.LANDMARKS)
        url = [ctx.homepage.final_url]
        if not missing:
            return [
                self.passed(
                    "Your homepage has a clear header, menu, main area and footer.", self.WHY
                )
            ]
        tags = ", ".join(f"<{name}>" for name in missing)
        return [
            self.finding(
                Severity.WARN,
                f"Your homepage is missing these structural areas: {tags}.",
                self.WHY,
                f"Wrap the matching parts of your page in {tags} elements. This doesn't change "
                "how the page looks.",
                impact=Level.MEDIUM if "main" in missing else Level.LOW,
                urls=url,
            )
        ]


class AgentReadableControls(Check):
    id = "agentic.named_controls"
    category = Category.AGENTIC
    title = "Buttons AI agents can use"
    weight = 4

    WHY = (
        "AI agents that browse and act for people (booking, ordering, filling in forms) find "
        "buttons and links by their names, just like screen readers. Unnamed icon buttons are "
        "invisible to them."
    )

    def run(self, ctx: AuditContext) -> list[Finding]:
        tree = ctx.dom(ctx.homepage)
        controls = tree.css("a[href], button")
        if not controls:
            return []
        nameless = [node for node in controls if not accessible_text(node)]
        self.partial = 1 - len(nameless) / len(controls)
        if not nameless:
            return [
                self.passed("Every link and button on your homepage has a clear name.", self.WHY)
            ]
        return [
            self.finding(
                Severity.WARN,
                f"{len(nameless)} links or buttons on your homepage have no name an AI agent "
                "could use.",
                self.WHY,
                'Give icon-only links and buttons a name, e.g. <button aria-label="Add to cart">.',
                impact=Level.MEDIUM,
                urls=[ctx.homepage.final_url],
            )
        ]


def visible_text_length(html: str) -> int:
    """Characters of readable text in raw HTML (scripts and styles removed)."""
    tree = LexborHTMLParser(html)  # a fresh copy, because we remove nodes from it
    for node in tree.css("script, style, noscript, template"):
        node.decompose()
    body = tree.body
    return len(body.text(separator=" ", strip=True)) if body else 0


class ContentWithoutJs(Check):
    id = "agentic.content_without_js"
    category = Category.AGENTIC
    title = "Content readable without JavaScript"
    weight = 8
    requires = frozenset({RENDER})

    WHY = (
        "Most AI crawlers don't run JavaScript. If your text only appears after JavaScript "
        "runs, they see an almost empty page and can't describe or recommend you."
    )
    FIX = (
        "Make sure important text is in the HTML your server sends: use server-side rendering "
        "or static generation (e.g. Next.js or Nuxt SSR), or your CMS's normal page output, "
        "instead of building the page only in the browser."
    )
    MIN_TEXT = 200  # rendered pages shorter than this are too small to judge

    def run(self, ctx: AuditContext) -> list[Finding]:
        assert ctx.render is not None  # noqa: S101 (guaranteed by `requires`)
        rendered = ctx.render.text_length
        if rendered < self.MIN_TEXT:
            return []
        raw = visible_text_length(ctx.homepage.text)
        ratio = min(1.0, raw / rendered)
        self.partial = ratio
        share = f"{round(ratio * 100)}%"
        url = [ctx.homepage.final_url]
        if ratio >= 0.7:
            return [
                self.passed(
                    f"AI crawlers that don't run JavaScript still see {share} of your "
                    "homepage text.",
                    self.WHY,
                )
            ]
        return [
            self.finding(
                Severity.WARN if ratio >= 0.3 else Severity.FAIL,
                f"Without JavaScript, only {share} of your homepage text is visible, which is "
                "what most AI crawlers see.",
                self.WHY,
                self.FIX,
                effort=Level.HIGH,
                impact=Level.MEDIUM if ratio >= 0.3 else Level.HIGH,
                urls=url,
            )
        ]


# --- AI search visibility: is the content easy to quote, attribute and trust? ------------

QUESTION_HEADINGS_NEEDED = 2
# "© 2026", "© 2019-2026", "Copyright 2026", also with an en dash between years.
COPYRIGHT_YEAR = re.compile(
    r"(?:\u00a9|&copy;|copyright)\s*(?:\d{4}\s*[-\u2013]\s*)?((?:19|20)\d{2})", re.I
)
ABOUT_LINK = re.compile(r"\babout\b|who we are|our story|our team|আমাদের সম্পর্কে", re.I)


class AnswerReady(Check):
    id = "agentic.answer_ready"
    category = Category.AGENTIC
    title = "Answers AI assistants can quote"
    weight = 4

    WHY = (
        "AI assistants answer people's questions by quoting websites that answer them clearly. "
        'Questions as headings ("How much does a website cost?") with a short answer below, '
        "or an FAQ, are the easiest content for them to quote and link to."
    )

    def run(self, ctx: AuditContext) -> list[Finding]:
        best_url, best = "", 0
        for page in ctx.html_pages:
            tree = ctx.dom(page) if page is ctx.homepage else ctx.tree(page)
            found = len(question_answers(tree))
            items, _ = read_json_ld(tree)
            if any("FAQPage" in types_of(item) for item in items):
                found = max(found, QUESTION_HEADINGS_NEEDED)
            if found > best:
                best_url, best = page.final_url, found
        if best >= QUESTION_HEADINGS_NEEDED:
            return [
                self.passed(
                    "Your website answers questions in a way AI assistants can quote.",
                    self.WHY,
                    [best_url],
                )
            ]
        return [
            self.finding(
                Severity.WARN,
                "Your website has no questions and answers (FAQ) for AI assistants to quote.",
                self.WHY,
                "Add a short FAQ to your homepage or main service page: the 5 questions "
                "customers ask you most, each as a heading with a 2-3 sentence answer. The "
                "page schema suggestions in this report then include the matching FAQ markup.",
                impact=Level.MEDIUM,
                urls=[ctx.homepage.final_url],
                snippets=[
                    Snippet(
                        title="An FAQ that AI assistants (and visitors) can read",
                        code="<section>\n  <h2>Frequently asked questions</h2>\n"
                        "  <details>\n    <summary>REPLACE: How much does it cost?</summary>\n"
                        "    <p>REPLACE: A short, direct answer in 2-3 sentences.</p>\n"
                        "  </details>\n</section>",
                    )
                ],
            )
        ]


class BusinessIdentity(Check):
    id = "agentic.business_identity"
    category = Category.AGENTIC
    title = "Who you are, confirmed elsewhere"
    weight = 3

    WHY = (
        "Before recommending a business, AI assistants check who it is: an About page, and "
        "the same business on LinkedIn, Facebook or Google. Linking them tells the AI these "
        "are all you, so it can recommend you with confidence."
    )

    def run(self, ctx: AuditContext) -> list[Finding]:
        home = ctx.homepage
        tree = ctx.dom(home)
        facts = site_facts(home.final_url, tree)
        about = any(
            ABOUT_LINK.search(f"{node.text(strip=True)} {node.attributes.get('href') or ''}")
            for node in tree.css("a[href]")
        )
        missing = []
        if not about:
            missing.append("link to an About page")
        if not facts.same_as:
            missing.append("links to your business profiles (LinkedIn, Facebook, ...)")
        if not missing:
            return [
                self.passed(
                    f"Your homepage links to an About page and {len(facts.same_as)} of your "
                    "profiles elsewhere.",
                    self.WHY,
                )
            ]
        return [
            self.finding(
                Severity.WARN if len(missing) == 2 else Severity.INFO,
                f"Your homepage has no {' and no '.join(missing)}.",
                self.WHY,
                "Link to an About page (who you are, since when, where, what you do) from "
                "the menu, and to your business profiles from the footer. List the same "
                "profiles in your Organization schema's sameAs.",
                impact=Level.MEDIUM,
                urls=[home.final_url],
            )
        ]


class UpToDate(Check):
    id = "agentic.up_to_date"
    category = Category.AGENTIC
    title = "Looks up to date"
    weight = 2

    WHY = (
        "AI assistants and visitors both prefer recent information. A copyright year from "
        'years ago makes a business look closed or neglected, even when it isn\'t: "© 2021" '
        "is the first thing many people notice."
    )

    def run(self, ctx: AuditContext) -> list[Finding]:
        home = ctx.homepage
        years = [int(y) for y in COPYRIGHT_YEAR.findall(visible_text(home, ctx.dom(home)))]
        if not years:
            return []  # no date shown: nothing to judge
        latest = max(years)
        this_year = datetime.now(UTC).year
        if latest >= this_year - 1:
            return [self.passed(f"Your website shows a current year (© {latest}).", self.WHY)]
        return [
            self.finding(
                Severity.WARN,
                f"Your website still says © {latest}: it looks like it hasn't been updated "
                f"since then.",
                self.WHY,
                f"Update the year in your footer to {this_year} (or make it update itself), and "
                "refresh your main pages with recent work, prices or news.",
                urls=[home.final_url],
            )
        ]
