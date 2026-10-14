"""Trust and conversion: does the website give visitors the confidence and the way to act?

A website can be fast and secure and still lose customers because nothing tells them what
to do next, nobody vouches for the business, or there's no privacy policy where they're
asked for their details. These belong to "Best practices", the vital sign about the
visitor's trust in the business.
"""

import re

from ..context import RENDER, AuditContext
from ..schema import read_json_ld, types_of
from ..types import Category, Finding, Level, Severity, Snippet
from .base import Check
from .local import visible_text

# Words of a call to action, in English and Bangla ("contact", "call", "order", "book").
ACTION_WORDS = re.compile(
    r"\b(contact|call|book|buy|order|shop|quote|get started|start|sign ?up|subscribe|request|"
    r"schedule|appointment|enquir|inquir|talk|chat|whatsapp|demo|hire|apply|donate|reserve|"
    r"consult|free trial|try|join|register|get in touch|message)"
    r"|যোগাযোগ|কল|অর্ডার|বুক|কিনুন",
    re.IGNORECASE,
)
ACTION_LINKS = ("tel:", "mailto:", "wa.me/", "api.whatsapp.com", "#contact", "/contact")

PRIVACY = re.compile(r"privacy|data protection|gdpr|গোপনীয়তা", re.IGNORECASE)
SOCIAL_PROOF = re.compile(
    r"testimonial|reviews?\b|what (our )?(clients|customers|people) say|trusted by|"
    r"our clients|happy (clients|customers)|case stud|rated \d|★|google reviews|trustpilot|"
    r"clutch|success stor|পর্যালোচনা",
    re.IGNORECASE,
)
REVIEW_TYPES = {"Review", "AggregateRating"}


class CallToAction(Check):
    id = "best_practices.call_to_action"
    category = Category.BEST_PRACTICES
    title = "A clear next step on a phone"
    weight = 4
    requires = frozenset({RENDER})

    WHY = (
        "Most visitors arrive on a phone and decide in seconds. If the first screen has no "
        'button like "Call us", "Book now" or "Get a quote", many leave without knowing what '
        "to do next."
    )

    def run(self, ctx: AuditContext) -> list[Finding]:
        phone = ctx.render.device("mobile") if ctx.render else None
        if phone is None:
            return []  # the phone view wasn't measured (MobileLayout reports why)
        actions = [
            label.strip()
            for label, _, href in (link.partition(" | ") for link in phone.first_screen_links)
            if ACTION_WORDS.search(label) or any(sign in href.lower() for sign in ACTION_LINKS)
        ]
        if actions:
            shown = ", ".join(f'"{a}"' for a in actions[:2] if a)
            message = "On a phone, the first screen shows a next step"
            return [self.passed(f"{message}: {shown}." if shown else f"{message}.", self.WHY)]
        return [
            self.finding(
                Severity.WARN,
                "On a phone, the first screen has no button to contact you, book or buy.",
                self.WHY,
                "Put one clear button in the top part of your homepage, visible without "
                'scrolling on a phone: "Call now", "Book a visit", "Get a free quote" or '
                '"Chat on WhatsApp", whichever is your main way of getting customers.',
                impact=Level.HIGH,
                urls=[ctx.homepage.final_url],
            )
        ]


class PrivacyPolicy(Check):
    id = "best_practices.privacy_policy"
    category = Category.BEST_PRACTICES
    title = "Privacy policy"
    weight = 3

    WHY = (
        "A privacy policy tells visitors what you do with their details. Most countries "
        "require one as soon as a website collects names, emails or phone numbers, and "
        "visitors trust a form more when it's there."
    )

    def run(self, ctx: AuditContext) -> list[Finding]:
        home = ctx.dom(ctx.homepage)
        for node in home.css("a[href]"):
            text = f"{node.text(strip=True)} {node.attributes.get('href') or ''}"
            if PRIVACY.search(text):
                return [self.passed("Your website links to a privacy policy.", self.WHY)]
        with_forms = [
            page.final_url
            for page in ctx.html_pages
            if any(
                form.css_first(
                    'input[type="email"], input[type="tel"], input[type="text"], textarea'
                )
                for form in (ctx.dom(page) if page is ctx.homepage else ctx.tree(page)).css("form")
            )
        ]
        fix = (
            "Write a short privacy policy (what you collect, why, how long you keep it, how to "
            "ask for it to be deleted), publish it as a page and link to it in the footer."
        )
        if with_forms:
            return [
                self.finding(
                    Severity.WARN,
                    "Your website asks visitors for their details, but has no privacy policy link.",
                    self.WHY,
                    fix + " Also link to it next to each form.",
                    impact=Level.MEDIUM,
                    urls=with_forms[:3],
                )
            ]
        return [
            self.finding(
                Severity.INFO,
                "Your homepage has no link to a privacy policy.",
                self.WHY,
                fix,
                impact=Level.LOW,
            )
        ]


class SocialProof(Check):
    id = "best_practices.social_proof"
    category = Category.BEST_PRACTICES
    title = "Reviews and testimonials"
    weight = 2

    WHY = (
        "People trust other customers more than any advert. Reviews, testimonials and "
        "well-known clients on the homepage turn a first visit into a phone call."
    )

    def run(self, ctx: AuditContext) -> list[Finding]:
        home = ctx.homepage
        tree = ctx.dom(home)
        items, _ = read_json_ld(tree)
        has_review_schema = any(REVIEW_TYPES & set(types_of(item)) for item in items) or any(
            "aggregateRating" in item or "review" in item for item in items
        )
        if has_review_schema or SOCIAL_PROOF.search(visible_text(home, tree)):
            return [self.passed("Your homepage shows what customers say about you.", self.WHY)]
        return [
            self.finding(
                Severity.INFO,
                "Your homepage doesn't show reviews, testimonials or clients.",
                self.WHY,
                "Add three short quotes from happy customers (with their name and business), "
                "your Google rating, or the logos of clients you've worked with.",
                impact=Level.MEDIUM,
                snippets=[
                    Snippet(
                        title="A testimonial, ready to style",
                        code='<figure class="testimonial">\n'
                        "  <blockquote>REPLACE: what the customer said, in one or two "
                        "sentences.</blockquote>\n"
                        "  <figcaption>REPLACE: Name, Business name</figcaption>\n"
                        "</figure>",
                    )
                ],
            )
        ]
