"""Local business checks: can customers call, message and find the business?

Small businesses win most customers by phone, WhatsApp and walk-ins, so these checks look
at what a customer on a phone needs: a visible phone number or email, a number they can tap
to call, a WhatsApp chat, and directions. They belong to the "Google visibility" vital sign:
Google's local results rely on the same contact details.
"""

import re

from selectolax.lexbor import LexborHTMLParser

from ..context import AuditContext
from ..types import Category, Finding, Level, Page, Severity, Snippet
from .base import Check

# A phone number as written on a page: "+880 1717-863320", "(555) 123-4567", "01717863320".
PHONE = re.compile(r"(?<![\w/.-])(?:\+|00)?\(?\d[\d\s().-]{7,16}\d(?![\w/-])")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+(?:\.[\w-]+)+")
WHATSAPP_HOSTS = ("wa.me/", "api.whatsapp.com/", "whatsapp://", "web.whatsapp.com/")
MAP_SIGNS = (
    "google.com/maps",
    "maps.google.",
    "goo.gl/maps",
    "maps.app.goo.gl",
    "maps.apple.com",
    "bing.com/maps",
    "openstreetmap.org",
)


def digits(text: str) -> str:
    return re.sub(r"\D", "", text)


def same_number(a: str, b: str) -> bool:
    """+8801717863320 and 01717-863320 are the same number: compare the last 9 digits."""
    return len(a) >= 9 and len(b) >= 9 and a[-9:] == b[-9:]


def visible_text(page: Page, tree: LexborHTMLParser) -> str:
    """The page's words, without scripts and styles (parsed again: the shared tree stays as is)."""
    copy = LexborHTMLParser(tree.html or page.text)
    for node in copy.css("script, style, noscript, template"):
        node.decompose()
    body = copy.body
    return body.text(separator=" ") if body is not None else ""


def phones_in(text: str) -> list[str]:
    """Phone numbers in the text: 9 to 15 digits, not dates, prices or version numbers."""
    found: list[str] = []
    for match in PHONE.finditer(text):
        raw = match.group(0).strip()
        number = digits(raw)
        looks_like_phone = raw.startswith(("+", "0", "(")) or " " in raw or "-" in raw
        is_new = not any(same_number(number, digits(f)) for f in found)
        is_date = re.fullmatch(r"(19|20)\d{6,}", number) is not None  # e.g. 20261014
        if 9 <= len(number) <= 15 and looks_like_phone and not is_date and is_new:
            found.append(raw)
    return found


def link_targets(tree: LexborHTMLParser, prefix: str) -> list[str]:
    return [
        (node.attributes.get("href") or "")[len(prefix) :]
        for node in tree.css("a[href]")
        if (node.attributes.get("href") or "").lower().startswith(prefix)
    ]


def has_link_to(tree: LexborHTMLParser, signs: tuple[str, ...]) -> bool:
    for node in tree.css("a[href], iframe[src]"):
        target = (node.attributes.get("href") or node.attributes.get("src") or "").lower()
        if any(sign in target for sign in signs):
            return True
    return False


class ContactDetails(Check):
    id = "seo.contact_details"
    category = Category.SEO
    title = "Contact details customers can find"
    weight = 4

    WHY = (
        "Most customers who are ready to buy want to call or write first. If they can't find a "
        "phone number or email in a few seconds, they contact a competitor instead. Google "
        "also uses these details for local results."
    )

    def run(self, ctx: AuditContext) -> list[Finding]:
        home = ctx.homepage
        home_tree = ctx.dom(home)
        on_home = bool(
            link_targets(home_tree, "tel:")
            or link_targets(home_tree, "mailto:")
            or phones_in(visible_text(home, home_tree))
            or EMAIL.search(visible_text(home, home_tree))
        )
        if on_home:
            return [self.passed("Your homepage shows how to contact you.", self.WHY)]
        elsewhere = [
            page.final_url
            for page in ctx.html_pages[1:]
            if link_targets(ctx.tree(page), "tel:")
            or link_targets(ctx.tree(page), "mailto:")
            or phones_in(visible_text(page, ctx.tree(page)))
        ]
        if elsewhere:
            return [
                self.finding(
                    Severity.INFO,
                    "Your phone number or email is only on other pages, not on the homepage.",
                    self.WHY,
                    "Put your phone number and email in the footer, so every page shows them.",
                    impact=Level.LOW,
                    urls=elsewhere[:3],
                )
            ]
        return [
            self.finding(
                Severity.WARN,
                "We couldn't find a phone number or email address on your website.",
                self.WHY,
                "Show a phone number and an email address in the footer of every page, and on "
                "a Contact page. Make the phone number a tap-to-call link.",
                impact=Level.HIGH,
                urls=[home.final_url],
            )
        ]


class ClickToCall(Check):
    id = "seo.click_to_call"
    category = Category.SEO
    title = "Phone numbers you can tap to call"
    weight = 3

    WHY = (
        "On a phone, people expect to tap a number to call it. A number that's just text has "
        "to be copied or typed, and many people give up."
    )

    def run(self, ctx: AuditContext) -> list[Finding]:
        home = ctx.homepage
        tree = ctx.dom(home)
        linked = [digits(target) for target in link_targets(tree, "tel:")]
        shown = phones_in(visible_text(home, tree))
        not_linked = [
            phone for phone in shown if not any(same_number(digits(phone), n) for n in linked)
        ]
        if not shown and not linked:
            return []  # no phone number: ContactDetails reports that
        if not not_linked:
            return [self.passed("Your phone number can be tapped to call.", self.WHY)]
        phone = not_linked[0]
        return [
            self.finding(
                Severity.WARN,
                f"Your phone number {phone} can't be tapped to call: it's plain text.",
                self.WHY,
                "Wrap the number in a tel: link, like below. It looks the same, and phones "
                "start the call when it's tapped.",
                impact=Level.MEDIUM,
                urls=[home.final_url],
                snippets=[
                    Snippet(
                        title="A tap-to-call link",
                        code=f'<a href="tel:+{digits(phone).lstrip("0")}">{phone}</a>'
                        if phone.startswith("+")
                        else f'<a href="tel:{digits(phone)}">{phone}</a>',
                    )
                ],
            )
        ]


class WhatsAppChat(Check):
    id = "seo.whatsapp_chat"
    category = Category.SEO
    title = "Chat on WhatsApp"
    weight = 1

    WHY = (
        "Many customers prefer a quick message to a call. A WhatsApp button lets them ask a "
        "question in one tap, from the page they're on."
    )

    def run(self, ctx: AuditContext) -> list[Finding]:
        home = ctx.homepage
        tree = ctx.dom(home)
        if has_link_to(tree, WHATSAPP_HOSTS):
            return [self.passed("Customers can message you on WhatsApp.", self.WHY)]
        phones = link_targets(tree, "tel:") or phones_in(visible_text(home, tree))
        number = digits(phones[0]) if phones else "8801XXXXXXXXX"
        return [
            self.finding(
                Severity.INFO,
                "There's no WhatsApp chat link on your homepage.",
                self.WHY,
                "If you answer customers on WhatsApp, add a link like the one below (your "
                "number with the country code, no + or spaces).",
                impact=Level.LOW,
                snippets=[
                    Snippet(
                        title="A WhatsApp chat link",
                        code=f'<a href="https://wa.me/{number}?text=Hi%2C%20I%20have%20a%20question">'
                        "Chat on WhatsApp</a>",
                        note="Check the number: it must include your country code."
                        if phones
                        else "Replace the X's with your number, starting with the country code.",
                    )
                ],
            )
        ]


class Directions(Check):
    id = "seo.directions"
    category = Category.SEO
    title = "Directions to your business"
    weight = 1

    WHY = (
        "If customers can visit you, a map or a directions link gets them to your door, and "
        "links your website to your Google Business Profile."
    )

    def run(self, ctx: AuditContext) -> list[Finding]:
        pages = ctx.html_pages
        with_map = [
            page.final_url
            for page in pages
            if has_link_to(ctx.dom(page) if page is ctx.homepage else ctx.tree(page), MAP_SIGNS)
        ]
        if with_map:
            return [
                self.passed("Your website shows how to find you on a map.", self.WHY, with_map[:3])
            ]
        return [
            self.finding(
                Severity.INFO,
                "Your website has no map or directions link.",
                self.WHY,
                'If customers can visit you, add a "Get directions" link to your Google Maps '
                "listing (Share > Copy link in Google Maps) on your Contact page and footer.",
                impact=Level.LOW,
            )
        ]
