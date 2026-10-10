"""Best-practice checks: is the site secure, modern and built to current standards?"""

import re
from dataclasses import dataclass

from ..context import PROBES, RENDER, AuditContext
from ..types import Category, Finding, Level, Page, Severity, Shot
from ._helpers import meta_content, meta_http_equiv, on_pages, shot_of, version_tuple
from .base import Check

HSTS_MIN_SECONDS = 180 * 24 * 60 * 60  # 180 days


def is_https(url: str) -> bool:
    return url.startswith("https://")


class Https(Check):
    id = "best_practices.https"
    category = Category.BEST_PRACTICES
    title = "Secure connection (HTTPS)"
    weight = 10

    WHY = (
        'Without HTTPS, browsers show "Not secure" next to your address, scaring visitors away, '
        "and anything they type (like contact details) can be read by others on their network."
    )

    def run(self, ctx: AuditContext) -> list[Finding]:
        if is_https(ctx.homepage.final_url):
            return [self.passed("Your website uses a secure HTTPS connection.", self.WHY)]
        return [
            self.finding(
                Severity.FAIL,
                'Your website isn\'t secure: browsers mark it "Not secure".',
                self.WHY,
                "Install a free TLS certificate (most hosts offer Let's Encrypt in one click) "
                "and redirect every http:// address to https://.",
                effort=Level.MEDIUM,
                impact=Level.HIGH,
                urls=[ctx.homepage.final_url],
            )
        ]


class HttpRedirect(Check):
    id = "best_practices.http_redirect"
    category = Category.BEST_PRACTICES
    title = "http:// sends visitors to https://"
    weight = 6
    requires = frozenset({PROBES})

    WHY = (
        "People who type your address without https:// or follow old links should "
        "automatically land on the secure version, not on an unprotected copy."
    )

    def run(self, ctx: AuditContext) -> list[Finding]:
        if not is_https(ctx.homepage.final_url):
            return []  # the Https check already reports this
        final = ctx.probes.http_final_url
        if final is None:
            return [
                self.finding(
                    Severity.INFO,
                    "Your website doesn't answer on http:// at all.",
                    self.WHY,
                    "Optionally answer on port 80 with a permanent (301) redirect to https:// "
                    "so old links and typed addresses still work.",
                    impact=Level.LOW,
                )
            ]
        if is_https(final):
            return [self.passed("Visitors to http:// are sent to the secure version.", self.WHY)]
        return [
            self.finding(
                Severity.WARN,
                "Visitors who type http:// stay on the insecure version of your site.",
                self.WHY,
                "Add a permanent (301) redirect from http:// to https:// in your hosting panel "
                "or web server settings.",
                impact=Level.MEDIUM,
                urls=[final],
            )
        ]


@dataclass(frozen=True)
class _Resource:
    selector: str
    attribute: str
    active: bool  # scripts/styles/frames can change the page; images can't


MIXED_CONTENT_RESOURCES = [
    _Resource("script[src]", "src", active=True),
    _Resource("iframe[src]", "src", active=True),
    _Resource("object[data]", "data", active=True),
    _Resource("embed[src]", "src", active=True),
    _Resource("img[src]", "src", active=False),
    _Resource("source[src]", "src", active=False),
    _Resource("video[src]", "src", active=False),
    _Resource("audio[src]", "src", active=False),
]


class MixedContent(Check):
    id = "best_practices.mixed_content"
    category = Category.BEST_PRACTICES
    title = "Mixed content"
    weight = 7

    WHY = (
        "A secure page that loads files over insecure http:// is only partly protected. "
        "Browsers block those files (breaking your design) or show a warning."
    )

    def run(self, ctx: AuditContext) -> list[Finding]:
        secure_pages = [p for p in ctx.html_pages if is_https(p.final_url)]
        if not secure_pages:
            return []
        active: set[str] = set()
        passive: set[str] = set()
        shots: list[Shot] = []  # only visible things (images, media, frames) can be shown
        for page in secure_pages:
            tree = ctx.tree(page)
            stylesheets = [
                n
                for n in tree.css("link[href]")
                if "stylesheet" in (n.attributes.get("rel") or "").lower()
            ]
            for node in stylesheets:
                if (node.attributes.get("href") or "").startswith("http://"):
                    active.add(page.final_url)
            for resource in MIXED_CONTENT_RESOURCES:
                for node in tree.css(resource.selector):
                    if (node.attributes.get(resource.attribute) or "").startswith("http://"):
                        (active if resource.active else passive).add(page.final_url)
                        if node.tag in ("img", "iframe", "video", "audio") and len(shots) < 3:
                            shots.append(shot_of(node, page.final_url))

        total = len(secure_pages)
        fix = (
            "Change every http:// file address on your pages to https:// (or to a relative /path)."
        )
        if active:
            return [
                self.finding(
                    Severity.FAIL,
                    on_pages(
                        len(active),
                        total,
                        "loads scripts or styles over insecure http://.",
                        "load scripts or styles over insecure http://.",
                    ),
                    self.WHY,
                    fix,
                    impact=Level.HIGH,
                    urls=sorted(active | passive),
                    shots=shots,
                )
            ]
        if passive:
            return [
                self.finding(
                    Severity.WARN,
                    on_pages(
                        len(passive),
                        total,
                        "loads images or media over insecure http://.",
                        "load images or media over insecure http://.",
                    ),
                    self.WHY,
                    fix,
                    impact=Level.MEDIUM,
                    urls=sorted(passive),
                    shots=shots,
                )
            ]
        return [self.passed("All files on your secure pages are loaded securely.", self.WHY)]


class _SecurityHeader(Check):
    """Shared logic for "is this response header set?" checks (not registered: abstract)."""

    category = Category.BEST_PRACTICES
    weight = 2

    def header(self, page: Page, name: str) -> str:
        return page.headers.get(name, "").strip()


class Hsts(_SecurityHeader):
    id = "best_practices.hsts"
    title = "Always-secure setting (HSTS)"
    weight = 4

    WHY = (
        "HSTS tells browsers to always use the secure version of your site, even if someone "
        "types http:// or clicks an old link, closing a gap attackers can use."
    )
    FIX = (
        "Send the header Strict-Transport-Security: max-age=31536000; includeSubDomains "
        "from your web server or CDN."
    )

    def run(self, ctx: AuditContext) -> list[Finding]:
        page = ctx.homepage
        if not is_https(page.final_url):
            return []
        value = self.header(page, "strict-transport-security")
        if not value:
            return [
                self.finding(
                    Severity.WARN,
                    "Browsers aren't told to always use the secure version of your site.",
                    self.WHY,
                    self.FIX,
                    impact=Level.MEDIUM,
                    urls=[page.final_url],
                )
            ]
        match = re.search(r"max-age\s*=\s*\"?(\d+)", value, re.IGNORECASE)
        if not match or int(match.group(1)) < HSTS_MIN_SECONDS:
            return [
                self.finding(
                    Severity.WARN,
                    "Your always-secure (HSTS) setting expires too quickly to be useful.",
                    self.WHY,
                    self.FIX,
                    impact=Level.LOW,
                    urls=[page.final_url],
                )
            ]
        return [self.passed("Browsers are told to always use your secure site.", self.WHY)]


class ContentSecurityPolicy(_SecurityHeader):
    id = "best_practices.csp"
    title = "Content Security Policy"
    weight = 3

    WHY = (
        "A Content Security Policy lists which sources may run code on your pages. If an "
        "attacker manages to inject a script, the browser refuses to run it."
    )

    def run(self, ctx: AuditContext) -> list[Finding]:
        page = ctx.homepage
        policy = self.header(page, "content-security-policy") or meta_http_equiv(
            ctx.tree(page), "content-security-policy"
        )
        if policy:
            return [self.passed("Your site has a Content Security Policy.", self.WHY)]
        if self.header(page, "content-security-policy-report-only"):
            return [
                self.finding(
                    Severity.INFO,
                    "Your Content Security Policy is in test mode: it reports problems but "
                    "doesn't block anything yet.",
                    self.WHY,
                    "Once the reports look clean, switch the header to "
                    "Content-Security-Policy to start protecting visitors.",
                    impact=Level.LOW,
                )
            ]
        return [
            self.finding(
                Severity.WARN,
                "Your site has no Content Security Policy to block injected scripts.",
                self.WHY,
                "Add a Content-Security-Policy header. Start in report-only mode, e.g. "
                "\"default-src 'self'\" plus the services you use, then enforce it.",
                effort=Level.MEDIUM,
                impact=Level.MEDIUM,
                urls=[page.final_url],
            )
        ]


class NoSniff(_SecurityHeader):
    id = "best_practices.nosniff"
    title = "File type protection"

    WHY = (
        "This header stops browsers from guessing what a file is, which blocks a trick where "
        "an uploaded file is run as a script."
    )

    def run(self, ctx: AuditContext) -> list[Finding]:
        page = ctx.homepage
        if self.header(page, "x-content-type-options").lower() == "nosniff":
            return [self.passed("Browsers are told not to guess file types.", self.WHY)]
        return [
            self.finding(
                Severity.WARN,
                "Browsers aren't told to stop guessing file types.",
                self.WHY,
                "Send the header X-Content-Type-Options: nosniff.",
                impact=Level.LOW,
                urls=[page.final_url],
            )
        ]


class FrameProtection(_SecurityHeader):
    id = "best_practices.frame_protection"
    title = "Protection from being framed"
    weight = 3

    WHY = (
        "Without it, another website can show your pages inside an invisible frame and trick "
        'visitors into clicking buttons they can\'t see ("clickjacking").'
    )

    def run(self, ctx: AuditContext) -> list[Finding]:
        page = ctx.homepage
        frame_options = self.header(page, "x-frame-options").upper()
        policy = self.header(page, "content-security-policy").lower()
        if frame_options in ("DENY", "SAMEORIGIN") or "frame-ancestors" in policy:
            return [self.passed("Other websites can't embed your pages in a frame.", self.WHY)]
        return [
            self.finding(
                Severity.WARN,
                "Other websites could embed your pages in a hidden frame.",
                self.WHY,
                "Send X-Frame-Options: SAMEORIGIN, or add frame-ancestors 'self' to your "
                "Content-Security-Policy.",
                impact=Level.MEDIUM,
                urls=[page.final_url],
            )
        ]


class ReferrerPolicy(_SecurityHeader):
    id = "best_practices.referrer_policy"
    title = "Referrer privacy"

    WHY = (
        "When visitors click a link to another site, browsers can pass along the full address "
        "they came from. A referrer policy keeps private details in your addresses private."
    )
    UNSAFE = frozenset({"unsafe-url", "no-referrer-when-downgrade"})

    def run(self, ctx: AuditContext) -> list[Finding]:
        page = ctx.homepage
        value = (
            self.header(page, "referrer-policy") or meta_content(ctx.tree(page), "referrer") or ""
        ).lower()
        policies = {part.strip() for part in value.split(",") if part.strip()}
        if policies and not policies & self.UNSAFE:
            return [self.passed("Your site sets a privacy-friendly referrer policy.", self.WHY)]
        message = (
            "Your referrer policy shares full page addresses with other websites."
            if policies
            else "Your site doesn't set a referrer policy."
        )
        return [
            self.finding(
                Severity.WARN,
                message,
                self.WHY,
                "Send the header Referrer-Policy: strict-origin-when-cross-origin.",
                impact=Level.LOW,
                urls=[page.final_url],
            )
        ]


@dataclass(frozen=True)
class _Library:
    name: str
    patterns: tuple[str, ...]  # regexes; group 1 is the version
    safe_from: str  # first version without known security problems
    note: str


LIBRARIES = [
    _Library(
        "jQuery",
        (
            r"jquery[.-](\d+\.\d+(?:\.\d+)?)(?:\.slim)?(?:\.min)?\.js",
            r"/jquery/(\d+\.\d+\.\d+)/",
            r"jquery@(\d+\.\d+\.\d+)",
            r"jquery(?:\.min)?\.js\?ver=(\d+\.\d+(?:\.\d+)?)",
        ),
        "3.5.0",
        "versions before 3.5 have known cross-site scripting (XSS) flaws",
    ),
    _Library(
        "Bootstrap",
        (
            r"bootstrap[@/-](\d+\.\d+\.\d+)",
            r"bootstrap(?:\.bundle)?(?:\.min)?\.js\?ver=(\d+\.\d+(?:\.\d+)?)",
        ),
        "4.3.1",
        "older versions have known cross-site scripting (XSS) flaws",
    ),
    _Library(
        "AngularJS",
        (r"angular(?:js)?[@/-](1\.\d+\.\d+)", r"angular[.-](1\.\d+\.\d+)(?:\.min)?\.js"),
        "2.0.0",
        "AngularJS 1.x no longer receives security updates",
    ),
    _Library(
        "Lodash",
        (r"lodash[@/-](\d+\.\d+\.\d+)", r"lodash[.-](\d+\.\d+\.\d+)(?:\.min)?\.js"),
        "4.17.21",
        "older versions have known security flaws",
    ),
]


class OutdatedLibraries(Check):
    id = "best_practices.outdated_libraries"
    category = Category.BEST_PRACTICES
    title = "Outdated code libraries"
    weight = 5

    WHY = (
        "Old versions of popular code libraries have publicly known security holes that "
        "attackers scan the web for. Updating them is one of the cheapest ways to stay safe."
    )

    def run(self, ctx: AuditContext) -> list[Finding]:
        found: dict[str, tuple[_Library, str, set[str]]] = {}
        for page in ctx.html_pages:
            for node in ctx.tree(page).css("script[src]"):
                src = (node.attributes.get("src") or "").lower()
                for library in LIBRARIES:
                    version = self.detect(library, src)
                    if version and version_tuple(version) < version_tuple(library.safe_from):
                        key = f"{library.name} {version}"
                        found.setdefault(key, (library, version, set()))[2].add(page.final_url)

        # The browser also reports versions of libraries bundled under other file names.
        if ctx.render is not None:
            by_name = {library.name: library for library in LIBRARIES}
            for name, version in ctx.render.libraries.items():
                known = by_name.get(name)
                if known and version_tuple(version) < version_tuple(known.safe_from):
                    key = f"{name} {version}"
                    found.setdefault(key, (known, version, set()))[2].add(ctx.homepage.final_url)

        if not found:
            return [
                self.passed(
                    "We found no outdated versions of common code libraries in your pages.",
                    self.WHY,
                )
            ]
        details = "; ".join(f"{name} ({lib.note})" for name, (lib, _, _) in sorted(found.items()))
        return [
            self.finding(
                Severity.FAIL,
                f"Your site uses outdated code with known security problems: {details}.",
                self.WHY,
                "Update these libraries to their latest versions (or update your theme and "
                "plugins), then test your forms and menus still work.",
                effort=Level.MEDIUM,
                impact=Level.MEDIUM,
                urls=sorted({url for _, _, urls in found.values() for url in urls}),
            )
        ]

    @staticmethod
    def detect(library: _Library, src: str) -> str | None:
        for pattern in library.patterns:
            match = re.search(pattern, src)
            if match:
                return match.group(1)
        return None


class Doctype(Check):
    id = "best_practices.doctype"
    category = Category.BEST_PRACTICES
    title = "Modern page standard (doctype)"
    weight = 2

    WHY = (
        "The <!doctype html> line tells browsers to use modern rules. Without it they switch "
        'to an old "quirks mode" where layouts can look different in each browser.'
    )

    def run(self, ctx: AuditContext) -> list[Finding]:
        missing = [
            p.final_url
            for p in ctx.html_pages
            if not re.match(r"\s*(<!--.*?-->\s*)*<!doctype html", p.text.lstrip("﻿"), re.I | re.S)
        ]
        if not missing:
            return [self.passed("Your pages use the modern HTML standard.", self.WHY)]
        return [
            self.finding(
                Severity.WARN,
                on_pages(
                    len(missing),
                    len(ctx.html_pages),
                    "is missing the modern <!doctype html> line.",
                    "are missing the modern <!doctype html> line.",
                ),
                self.WHY,
                "Make <!doctype html> the very first line of every page.",
                impact=Level.LOW,
                urls=missing,
            )
        ]


class Charset(Check):
    id = "best_practices.charset"
    category = Category.BEST_PRACTICES
    title = "Character encoding"
    weight = 2

    WHY = (
        "Declaring the character set makes sure letters like é, ü or ৳ show correctly instead "
        "of strange symbols."
    )

    def run(self, ctx: AuditContext) -> list[Finding]:
        missing = []
        for page in ctx.html_pages:
            in_header = "charset=" in page.headers.get("content-type", "").lower()
            head = page.text[:1024].lower()
            in_html = "<meta charset" in head or ("http-equiv" in head and "charset=" in head)
            if not (in_header or in_html):
                missing.append(page.final_url)
        if not missing:
            return [self.passed("Your pages declare their character set.", self.WHY)]
        return [
            self.finding(
                Severity.WARN,
                on_pages(
                    len(missing),
                    len(ctx.html_pages),
                    "doesn't declare its character set.",
                    "don't declare their character set.",
                ),
                self.WHY,
                'Add <meta charset="utf-8"> as the first line inside <head>.',
                impact=Level.LOW,
                urls=missing,
            )
        ]


class Viewport(Check):
    id = "best_practices.viewport"
    category = Category.BEST_PRACTICES
    title = "Mobile-friendly setup"
    weight = 7

    WHY = (
        "Most visitors use a phone. Without a viewport tag, phones show a tiny zoomed-out "
        "desktop page, and Google ranks sites that aren't mobile-friendly lower."
    )

    def run(self, ctx: AuditContext) -> list[Finding]:
        content = meta_content(ctx.tree(ctx.homepage), "viewport")
        if content is None:
            return [
                self.finding(
                    Severity.FAIL,
                    "Your homepage isn't set up for phones, so it appears tiny and zoomed out.",
                    self.WHY,
                    'Add <meta name="viewport" content="width=device-width, initial-scale=1"> '
                    "inside <head>, then check the layout on a phone.",
                    impact=Level.HIGH,
                    urls=[ctx.homepage.final_url],
                )
            ]
        if "width=device-width" not in content.replace(" ", "").lower():
            return [
                self.finding(
                    Severity.WARN,
                    "Your homepage's phone setting doesn't adapt to the screen width.",
                    self.WHY,
                    'Use content="width=device-width, initial-scale=1" in the viewport tag.',
                    impact=Level.MEDIUM,
                    urls=[ctx.homepage.final_url],
                )
            ]
        return [self.passed("Your homepage adapts to phone screens.", self.WHY)]


class ConsoleErrors(Check):
    id = "best_practices.console_errors"
    category = Category.BEST_PRACTICES
    title = "JavaScript errors"
    weight = 4
    requires = frozenset({RENDER})

    WHY = (
        "JavaScript errors are signs that something on the page is broken. They often mean a "
        "menu, form, chat widget or checkout button silently doesn't work for some visitors."
    )
    MAX_SHOWN = 3

    def run(self, ctx: AuditContext) -> list[Finding]:
        assert ctx.render is not None  # noqa: S101 (guaranteed by `requires`)
        errors = list(dict.fromkeys(ctx.render.console_errors))  # unique, in order
        if not errors:
            return [self.passed("Your homepage ran without JavaScript errors.", self.WHY)]
        examples = "; ".join(e[:160] for e in errors[: self.MAX_SHOWN])
        return [
            self.finding(
                Severity.WARN,
                f"Your homepage shows {len(errors)} JavaScript error(s) in the browser, "
                f"for example: {examples}",
                self.WHY,
                "Open the page, press F12 and look at the Console tab. Fix or remove the "
                "scripts that cause these errors (often an outdated plugin or a removed "
                "third-party service).",
                effort=Level.MEDIUM,
                impact=Level.MEDIUM,
                urls=[ctx.homepage.final_url],
            )
        ]


class ThirdPartyCookies(Check):
    id = "best_practices.third_party_cookies"
    category = Category.BEST_PRACTICES
    title = "Third-party cookies"
    weight = 3
    requires = frozenset({RENDER})

    WHY = (
        "Cookies from other companies (ad networks, trackers) follow your visitors around the "
        "web. Privacy laws such as GDPR require consent first, and browsers increasingly "
        "block them, which can break the features that rely on them."
    )

    def run(self, ctx: AuditContext) -> list[Finding]:
        assert ctx.render is not None  # noqa: S101 (guaranteed by `requires`)
        domains = sorted({c.domain for c in ctx.render.cookies if c.third_party})
        if not domains:
            return [
                self.passed("No other companies set cookies when your homepage loads.", self.WHY)
            ]
        return [
            self.finding(
                Severity.WARN,
                f"{len(domains)} other compan{'y sets' if len(domains) == 1 else 'ies set'} "
                f"cookies as soon as your homepage loads: {', '.join(domains)}.",
                self.WHY,
                "Load trackers and ads only after visitors agree in a cookie banner, and "
                "remove services you no longer use.",
                effort=Level.MEDIUM,
                impact=Level.MEDIUM,
                urls=[ctx.homepage.final_url],
            )
        ]
