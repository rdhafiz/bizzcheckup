"""Accessibility checks: can everyone use your website, including people with disabilities?

Five checks read the HTML of every crawled page (the browser-rendered version
for the homepage when available). One more runs the axe-core scanner in a real
browser and reports everything the others don't already cover.
"""

import re
from itertools import pairwise

from selectolax.lexbor import LexborNode

from ..context import RENDER, AuditContext
from ..types import AxeNode, AxeRule, Category, Finding, Level, Severity, Snippet
from ._helpers import on_pages, share_score
from .base import Check

WHO = (
    "About 1 in 6 people live with a disability. Many use screen readers, keyboards or "
    "zoom, and accessibility is a legal requirement in more and more countries."
)


def accessible_text(node: LexborNode) -> str:
    """The name a screen reader would announce for a link or button (simplified)."""
    for attribute in ("aria-label", "title"):
        value = (node.attributes.get(attribute) or "").strip()
        if value:
            return value
    if (node.attributes.get("aria-labelledby") or "").strip():
        return "labelled"  # points at other text; assume it's fine
    text = node.text(strip=True)
    if text:
        return text
    for image in node.css("img[alt], svg[aria-label]"):
        alt = (image.attributes.get("alt") or image.attributes.get("aria-label") or "").strip()
        if alt:
            return alt
    return ""


class ImageAlt(Check):
    id = "accessibility.image_alt"
    category = Category.ACCESSIBILITY
    title = "Image descriptions (alt text)"
    weight = 8

    WHY = (
        "Blind visitors hear the alt text instead of seeing the image, and Google uses it to "
        "understand your pictures. Without it, product photos and buttons made of images "
        f"mean nothing to them. {WHO}"
    )

    def run(self, ctx: AuditContext) -> list[Finding]:
        total = 0
        missing_pages: list[str] = []
        missing = 0
        for page in ctx.html_pages:
            images = ctx.dom(page).css("img")
            bad = [img for img in images if "alt" not in img.attributes]
            total += len(images)
            missing += len(bad)
            if bad:
                missing_pages.append(page.final_url)
        if total == 0:
            return []
        self.partial = share_score(total, missing)
        if not missing:
            return [self.passed(f"All {total} images have a description.", self.WHY)]
        return [
            self.finding(
                Severity.FAIL,
                f"{missing} of your {total} images have no description for blind visitors.",
                self.WHY,
                'Add an alt attribute to every <img>: describe what it shows, e.g. alt="Red '
                'leather handbag with gold clasp". Use alt="" for purely decorative images.',
                effort=Level.LOW if missing <= 10 else Level.MEDIUM,
                impact=Level.HIGH,
                urls=missing_pages,
            )
        ]


class HtmlLang(Check):
    id = "accessibility.html_lang"
    category = Category.ACCESSIBILITY
    title = "Page language"
    weight = 5

    WHY = (
        "Screen readers use the page language to pronounce words correctly. Without it, an "
        "English page may be read out with the wrong accent and become hard to understand. "
        "Translation tools and Google also use it."
    )
    VALID = re.compile(r"^[a-z]{2,3}(-[a-z0-9]{2,8})*$", re.IGNORECASE)

    def run(self, ctx: AuditContext) -> list[Finding]:
        html = ctx.dom(ctx.homepage).css_first("html")
        lang = (html.attributes.get("lang") or "").strip() if html else ""
        if not lang:
            return [
                self.finding(
                    Severity.FAIL,
                    "Your homepage doesn't say which language it is written in.",
                    self.WHY,
                    'Add the language to the first tag of the page, e.g. <html lang="en"> '
                    '(or "bn" for Bangla, "ar" for Arabic).',
                    impact=Level.MEDIUM,
                    urls=[ctx.homepage.final_url],
                )
            ]
        if not self.VALID.match(lang):
            return [
                self.finding(
                    Severity.WARN,
                    f"Your homepage's language code \"{lang}\" isn't a valid code.",
                    self.WHY,
                    'Use a standard code such as "en", "en-GB", "bn" or "ar".',
                    impact=Level.LOW,
                    urls=[ctx.homepage.final_url],
                )
            ]
        return [self.passed(f'Your homepage declares its language ("{lang}").', self.WHY)]


class HeadingOrder(Check):
    id = "accessibility.heading_order"
    category = Category.ACCESSIBILITY
    title = "Heading structure"
    weight = 3

    WHY = (
        "Screen-reader users jump between headings to skim a page, like reading a table of "
        "contents. Skipped levels (a main heading followed directly by a sub-sub-heading) "
        "make the page structure confusing."
    )

    def run(self, ctx: AuditContext) -> list[Finding]:
        pages = ctx.html_pages
        skipped: list[str] = []
        with_headings = 0
        for page in pages:
            levels = [
                int((node.tag or "h0")[1]) for node in ctx.dom(page).css("h1, h2, h3, h4, h5, h6")
            ]
            if not levels:
                continue
            with_headings += 1
            if any(current > previous + 1 for previous, current in pairwise(levels)):
                skipped.append(page.final_url)
        if with_headings == 0:
            return []
        self.partial = share_score(with_headings, 0, len(skipped))
        if not skipped:
            return [self.passed("Your headings follow a logical order.", self.WHY)]
        return [
            self.finding(
                Severity.WARN,
                on_pages(
                    len(skipped),
                    len(pages),
                    "skips heading levels (for example from H2 straight to H4).",
                    "skip heading levels (for example from H2 straight to H4).",
                ),
                self.WHY,
                "Use headings in order: one H1, then H2 for sections, H3 inside those. Change "
                "the look with CSS instead of picking a smaller heading level.",
                impact=Level.LOW,
                urls=skipped,
            )
        ]


class FormLabels(Check):
    id = "accessibility.form_labels"
    category = Category.ACCESSIBILITY
    title = "Form field labels"
    weight = 8

    WHY = (
        "If a contact or order form's fields have no labels, screen-reader users hear just "
        '"edit text" and can\'t tell where to type their name, phone or email: a lost '
        "customer. Labels also make fields easier to tap on phones."
    )
    NOT_FIELDS = frozenset({"hidden", "submit", "button", "image", "reset"})

    def run(self, ctx: AuditContext) -> list[Finding]:
        total = 0
        unlabelled = 0
        pages_with_problems: list[str] = []
        for page in ctx.html_pages:
            tree = ctx.dom(page)
            label_targets = {
                (label.attributes.get("for") or "").strip() for label in tree.css("label[for]")
            }
            fields = [
                field
                for field in tree.css("input, select, textarea")
                if (field.attributes.get("type") or "text").lower() not in self.NOT_FIELDS
            ]
            bad = [f for f in fields if not self.has_label(f, label_targets)]
            total += len(fields)
            unlabelled += len(bad)
            if bad:
                pages_with_problems.append(page.final_url)
        if total == 0:
            return []  # no forms: nothing to check
        self.partial = share_score(total, unlabelled)
        if not unlabelled:
            return [self.passed(f"All {total} form fields have labels.", self.WHY)]
        return [
            self.finding(
                Severity.FAIL,
                f"{unlabelled} of your {total} form fields have no label.",
                self.WHY,
                'Give every field a visible <label for="field-id">, e.g. <label for="email">'
                'Your email</label> <input id="email" type="email">. A placeholder alone is '
                "not a label.",
                impact=Level.HIGH,
                urls=pages_with_problems,
            )
        ]

    @staticmethod
    def has_label(field: LexborNode, label_targets: set[str]) -> bool:
        if (field.attributes.get("id") or "").strip() in label_targets - {""}:
            return True
        for attribute in ("aria-label", "aria-labelledby", "title"):
            if (field.attributes.get(attribute) or "").strip():
                return True
        parent = field.parent
        while parent is not None:  # <label>Name <input></label>
            if parent.tag == "label":
                return True
            parent = parent.parent
        return False


class AccessibleNames(Check):
    id = "accessibility.accessible_names"
    category = Category.ACCESSIBILITY
    title = "Link and button names"
    weight = 6

    WHY = (
        "Icon-only links and buttons (a magnifying glass, a cart, a social media logo) are "
        'announced to blind visitors as just "link" or "button", so they can\'t search, '
        "check out or follow you."
    )

    def run(self, ctx: AuditContext) -> list[Finding]:
        total = 0
        nameless = 0
        pages_with_problems: list[str] = []
        for page in ctx.html_pages:
            tree = ctx.dom(page)
            elements = tree.css("a[href], button")
            bad = [node for node in elements if not accessible_text(node)]
            buttons = tree.css('input[type="submit"], input[type="button"]')
            bad += [b for b in buttons if not (b.attributes.get("value") or "").strip()]
            total += len(elements) + len(buttons)
            nameless += len(bad)
            if bad:
                pages_with_problems.append(page.final_url)
        if total == 0:
            return []
        self.partial = share_score(total, 0, nameless)
        if not nameless:
            return [self.passed("All links and buttons have a readable name.", self.WHY)]
        return [
            self.finding(
                Severity.WARN,
                f"{nameless} links or buttons have no name that screen readers can announce.",
                self.WHY,
                'Add text or an aria-label, e.g. <a href="/cart" aria-label="Shopping cart">. '
                "For image links, give the image an alt text.",
                impact=Level.MEDIUM,
                urls=pages_with_problems,
            )
        ]


# axe rules already reported by the checks above (so they aren't counted twice).
EM_DASH = chr(0x2014)

# Plain advice for the rules sites fail most often (axe's guide link covers the rest).
RULE_FIX = {
    "color-contrast": (
        "Make the text darker or its background lighter (or the other way round) until the "
        "contrast reaches the ratio shown. A free checker: "
        "https://webaim.org/resources/contrastchecker/"
    ),
    "region": "Put all visible content inside <header>, <nav>, <main> or <footer>.",
    "landmark-one-main": "Wrap the page's main content in one <main> element.",
    "link-in-text-block": "Underline links inside text so they don't rely on colour alone.",
}

COVERED_BY_OTHER_CHECKS = {
    "image-alt",
    "html-has-lang",
    "html-lang-valid",
    "heading-order",
    "label",
    "select-name",
    "link-name",
    "button-name",
    "input-button-name",
}

IMPACT_PENALTY = {"critical": 1.0, "serious": 0.7, "moderate": 0.3, "minor": 0.1}

# Plain-language business impact for the most common axe findings.
RULE_IMPACT = {
    "color-contrast": (
        "Text with too little contrast is hard to read for older visitors, people with low "
        "vision and anyone using a phone in bright sunlight."
    ),
    "landmark-one-main": (
        "Screen-reader users jump straight to the main content using landmarks; without "
        "them they have to listen through your whole menu on every page."
    ),
    "region": (
        "Content outside page landmarks is easy to miss for screen-reader users skimming the page."
    ),
    "meta-viewport": "Blocking zoom stops visitors with poor eyesight from enlarging text.",
    "document-title": (
        "Screen readers announce the page title first; without it, visitors are lost."
    ),
    "duplicate-id": "Duplicate element ids can make forms and menus behave unpredictably.",
    "aria-allowed-attr": "Incorrect ARIA attributes give assistive technology wrong information.",
    "label-content-name-mismatch": (
        "Voice-control users say the visible label to click a control; if the hidden name "
        "differs, the command doesn't work."
    ),
}


class AxeScan(Check):
    id = "accessibility.axe_scan"
    category = Category.ACCESSIBILITY
    title = "Automated accessibility scan"
    weight = 10
    requires = frozenset({RENDER})

    def run(self, ctx: AuditContext) -> list[Finding]:
        assert ctx.render is not None  # noqa: S101 (guaranteed by `requires`)
        violations = [v for v in ctx.render.axe_violations if v.id not in COVERED_BY_OTHER_CHECKS]
        passes = [p for p in ctx.render.axe_passes if p not in COVERED_BY_OTHER_CHECKS]

        total = len(passes) + len(violations)
        if total == 0:
            return []
        penalty = sum(IMPACT_PENALTY.get(v.impact, 0.3) for v in violations)
        self.partial = max(0.0, (total - penalty) / total)

        if not violations:
            return [
                self.passed(
                    f"An automated scan of your homepage passed all {len(passes)} rules we test.",
                    WHO,
                )
            ]
        order = list(IMPACT_PENALTY)
        violations.sort(key=lambda v: (order.index(v.impact) if v.impact in order else 9, v.id))
        return [self.rule_finding(v, ctx.homepage.final_url) for v in violations]

    def rule_finding(self, rule: AxeRule, url: str) -> Finding:
        # Serious problems count as high impact: they block real visitors, and a high-impact
        # failure keeps the category out of "Healthy" (see scoring.HIGH_IMPACT_FAIL_CAP).
        severity, impact = {
            "critical": (Severity.FAIL, Level.HIGH),
            "serious": (Severity.FAIL, Level.HIGH),
            "moderate": (Severity.WARN, Level.LOW),
        }.get(rule.impact, (Severity.INFO, Level.LOW))
        elements = "1 element" if rule.nodes == 1 else f"{rule.nodes} elements"
        advice = RULE_FIX.get(rule.id, "")
        if rule.details:
            shown = len(rule.details)
            if rule.nodes == 1:
                which = "Below you can see the element"
            elif shown < rule.nodes:
                which = f"Below you can see the first {shown}"
            else:
                which = "Below you can see each one"
            fix = (
                f"{which}: where it is on the page (outlined in red), what exactly is wrong, "
                f"and its HTML. {advice}"
            )
        else:  # reports made before element details were collected
            examples = ", ".join(f"`{target}`" for target in rule.targets[:3])
            fix = f"Fix the affected elements, for example {examples}. {advice}"
        return self.finding(
            severity,
            f"{rule.help} ({elements} on your homepage).",
            RULE_IMPACT.get(rule.id, WHO),
            f"{fix.strip()} Step-by-step guidance: {rule.help_url}",
            effort=Level.LOW if rule.nodes <= 5 else Level.MEDIUM,
            impact=impact,
            urls=[url],
            snippets=[element_snippet(index, node) for index, node in enumerate(rule.details, 1)],
        )


def problem_text(summary: str) -> str:
    """axe's explanation without its "Fix any of the following:" headings."""
    lines = [line.strip() for line in summary.splitlines()]
    return " ".join(line for line in lines if line and not line.lower().startswith("fix "))


def element_snippet(index: int, node: AxeNode) -> Snippet:
    """One flagged element, described so a non-developer can find it."""
    problem = problem_text(node.summary)
    short = problem.split(" (")[0].rstrip(".") if problem else "Doesn't pass this rule"
    text = " ".join(node.text.split())  # one line, however the page wraps it
    if len(text) > 60:
        text = text[:57].rstrip() + "..."
    name = f'"{text}"' if text else f"Element {index}"
    lines = [f"HTML: {node.html}"] if node.html else []
    lines.append(f"CSS selector: {node.target}")
    return Snippet(
        title=f"{name} {EM_DASH} {short}",
        code="\n\n".join(lines),
        language="element",
        image=node.image,
        note=problem,
    )
