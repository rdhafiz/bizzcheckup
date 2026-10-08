"""Phone and tablet checks: does the homepage fit the screen, and can people tap and read it?

They use the browser collector's phone (390 px) and tablet (820 px) views of the homepage.
"""

from ..context import RENDER, AuditContext
from ..types import Category, DeviceView, Finding, Level, Severity, Snippet
from ._helpers import share_score
from .base import Check

SMALL_TEXT_PX = 12
TAP_PX = 24  # WCAG 2.5.8: targets at least 24 x 24 CSS pixels


def device(ctx: AuditContext, name: str) -> DeviceView | None:
    return ctx.render.device(name) if ctx.render else None


def shrink_percent(view: DeviceView) -> int:
    """How big things look when the desktop page is squeezed onto the screen."""
    return round(100 * view.width / view.layout_width) if view.layout_width else 100


def examples(title: str, items: list[str]) -> list[Snippet]:
    if not items:
        return []
    return [Snippet(title=title, code="\n".join(items), language="text")]


class MobileLayout(Check):
    """No shrunken desktop page, no sideways scrolling, on phones and tablets."""

    id = "best_practices.mobile_layout"
    category = Category.BEST_PRACTICES
    title = "Fits phone and tablet screens"
    weight = 7
    requires = frozenset({RENDER})

    WHY = (
        "Most visitors arrive on a phone. A page that has to be pinched, zoomed or scrolled "
        "sideways feels broken, and Google ranks pages that work well on phones higher."
    )

    def run(self, ctx: AuditContext) -> list[Finding]:
        views = [view for view in (device(ctx, "mobile"), device(ctx, "tablet")) if view]
        if not views:
            return []
        url = [ctx.homepage.final_url]
        findings: list[Finding] = []
        for view in views:
            serious = view.name == "mobile"
            if view.zoomed_out:
                findings.append(
                    self.finding(
                        Severity.FAIL if serious else Severity.WARN,
                        f"On a {view.label}, your homepage shows the desktop version shrunk to "
                        f"about {shrink_percent(view)}% of its size, so text and buttons are tiny.",
                        self.WHY,
                        'Add <meta name="viewport" content="width=device-width, initial-scale=1">'
                        " to <head>, then make the layout responsive (CSS media queries or a "
                        "mobile-friendly theme) so it rearranges itself for small screens.",
                        effort=Level.MEDIUM,
                        impact=Level.HIGH if serious else Level.MEDIUM,
                        urls=url,
                    )
                )
            elif not view.fits:
                findings.append(
                    self.finding(
                        Severity.FAIL if serious else Severity.WARN,
                        f"On a {view.label}, your homepage is wider than the screen "
                        f"({view.scroll_width} px on a {view.width} px screen), so visitors "
                        "have to scroll sideways.",
                        self.WHY,
                        "Find the elements listed below and stop them being wider than the "
                        "screen: use max-width: 100% on images, videos and tables, let long "
                        "words and links wrap, and avoid fixed widths in pixels.",
                        effort=Level.MEDIUM,
                        impact=Level.HIGH if serious else Level.MEDIUM,
                        urls=url,
                        snippets=examples(f"Wider than the {view.label} screen", view.overflowing),
                    )
                )
        if findings:
            return findings
        sizes = " and ".join(f"a {view.width} px {view.label}" for view in views)
        return [self.passed(f"Your homepage fits {sizes} without sideways scrolling.", self.WHY)]


class TapTargets(Check):
    """Links and buttons big enough for a finger."""

    id = "best_practices.tap_targets"
    category = Category.BEST_PRACTICES
    title = "Easy to tap on phones"
    weight = 4
    requires = frozenset({RENDER})

    WHY = (
        "Fingers are much bigger than a mouse pointer. Tiny links and buttons make people "
        "tap the wrong thing, or give up on ordering or contacting you."
    )
    FIX = (
        f"Make every link and button at least {TAP_PX} x {TAP_PX} pixels on phones (44 x 44 is "
        "more comfortable), for example with padding, and leave space between neighbours. "
        "The ones below are too small."
    )

    def run(self, ctx: AuditContext) -> list[Finding]:
        view = device(ctx, "mobile")
        if view is None or view.tap_targets == 0:
            return []
        url = [ctx.homepage.final_url]
        if view.zoomed_out:
            return [
                self.finding(
                    Severity.WARN,
                    "On phones, every link and button on your homepage is shown at about "
                    f"{shrink_percent(view)}% of its size, because the page isn't laid out for "
                    "phones.",
                    self.WHY,
                    'Fix the phone layout first (see "Fits phone and tablet screens"); the '
                    "links and buttons then get their normal size.",
                    impact=Level.MEDIUM,
                    urls=url,
                )
            ]
        small, total = view.small_tap_targets, view.tap_targets
        self.partial = share_score(total, 0, small)
        if not small:
            return [self.passed(f"All {total} links and buttons are big enough to tap.", self.WHY)]
        severity = Severity.WARN if small >= 3 or small / total >= 0.1 else Severity.INFO
        return [
            self.finding(
                severity,
                f"{small} of the {total} links and buttons on your homepage are too small to "
                "tap easily on a phone.",
                self.WHY,
                self.FIX,
                impact=Level.MEDIUM if severity is Severity.WARN else Level.LOW,
                urls=url,
                snippets=examples(
                    f"Smaller than {TAP_PX} x {TAP_PX} pixels", view.small_tap_examples
                ),
            )
        ]


class MobileTextSize(Check):
    """Text big enough to read on a phone without zooming."""

    id = "best_practices.mobile_text_size"
    category = Category.BEST_PRACTICES
    title = "Readable text on phones"
    weight = 4
    requires = frozenset({RENDER})

    WHY = (
        "If people have to zoom in to read your prices, opening hours or offer, many won't. "
        "Readable text keeps visitors on the page and makes your business look professional."
    )

    def run(self, ctx: AuditContext) -> list[Finding]:
        view = device(ctx, "mobile")
        if view is None or view.text_chars == 0:
            return []
        url = [ctx.homepage.final_url]
        if view.zoomed_out:
            return [
                self.finding(
                    Severity.WARN,
                    f"On phones, the text on your homepage is shown at about "
                    f"{shrink_percent(view)}% of its size, because the page isn't laid out for "
                    "phones.",
                    self.WHY,
                    'Fix the phone layout first (see "Fits phone and tablet screens").',
                    impact=Level.MEDIUM,
                    urls=url,
                )
            ]
        share = view.small_text_share
        self.partial = max(0.0, 1.0 - share)
        percent = round(share * 100)
        fix = (
            "Use at least 16 px for normal text on phones, and never less than "
            f"{SMALL_TEXT_PX} px, even for small print."
        )
        if share >= 0.25:
            return [
                self.finding(
                    Severity.WARN,
                    f"About {percent}% of the text on your homepage is smaller than "
                    f"{SMALL_TEXT_PX} px on a phone, which is hard to read.",
                    self.WHY,
                    fix,
                    impact=Level.MEDIUM,
                    urls=url,
                )
            ]
        if share >= 0.05:
            return [
                self.finding(
                    Severity.INFO,
                    f"About {percent}% of the text on your homepage is smaller than "
                    f"{SMALL_TEXT_PX} px on a phone (usually small print).",
                    self.WHY,
                    fix,
                    impact=Level.LOW,
                    urls=url,
                )
            ]
        return [self.passed("The text on your homepage is easy to read on a phone.", self.WHY)]
