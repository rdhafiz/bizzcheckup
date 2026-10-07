"""Performance checks: how fast does your website load and respond?

The first four use Google PageSpeed Insights (they need PSI_API_KEY). The last
three also work from the page HTML alone, and use PageSpeed data when present.
"""

from dataclasses import dataclass

from selectolax.lexbor import LexborHTMLParser

from ..context import PAGESPEED, AuditContext
from ..types import Category, Finding, Level, Severity, SpeedTest
from ._helpers import on_pages, share_score
from .base import Check

SPEED_WHY = (
    "More than half of mobile visitors leave a page that takes over 3 seconds to load, and "
    "Google ranks faster sites higher. Every second you save keeps more potential customers."
)
SPEED_FIX = (
    "Start with the biggest wins in this report: compress and resize images, remove unused "
    "plugins and scripts, turn on caching and compression, and consider a CDN or faster hosting."
)

MB = 1024 * 1024


class _SpeedScore(Check, register=False):
    """Lighthouse performance score for one device type (abstract helper)."""

    category = Category.PERFORMANCE
    requires = frozenset({PAGESPEED})
    strategy = "mobile"
    device = "phones"

    def run(self, ctx: AuditContext) -> list[Finding]:
        assert ctx.pagespeed is not None  # noqa: S101 (guaranteed by `requires`)
        test: SpeedTest | None = getattr(ctx.pagespeed, self.strategy)
        if test is None:
            return []
        self.partial = test.score
        points = round(test.score * 100)
        message = f"Google rates your homepage's speed on {self.device} {points} out of 100."
        if test.lcp_ms:
            message += f" The main content appears after {test.lcp_ms / 1000:.1f} seconds."
        url = [ctx.homepage.final_url]
        if test.score >= 0.9:
            return [self.passed(message, SPEED_WHY, url)]
        severity, impact = (
            (Severity.WARN, Level.MEDIUM) if test.score >= 0.5 else (Severity.FAIL, Level.HIGH)
        )
        return [
            self.finding(
                severity,
                message,
                SPEED_WHY,
                SPEED_FIX,
                effort=Level.MEDIUM,
                impact=impact,
                urls=url,
            )
        ]


class MobileSpeed(_SpeedScore):
    id = "performance.mobile_speed"
    title = "Speed on phones"
    weight = 10


class DesktopSpeed(_SpeedScore):
    id = "performance.desktop_speed"
    title = "Speed on computers"
    weight = 5
    strategy = "desktop"
    device = "computers"


@dataclass(frozen=True)
class _Metric:
    name: str
    good: float  # at or below = good
    poor: float  # above = poor
    message: str  # {value} is filled in
    why: str
    fix: str
    in_seconds: bool = False  # measured in ms, shown in seconds

    def describe(self, value: float) -> str:
        return self.message.format(value=value / 1000 if self.in_seconds else value)

    def rating(self, value: float) -> float:
        return 1.0 if value <= self.good else 0.5 if value <= self.poor else 0.0


SLOW_SCRIPTS_FIX = (
    "Reduce heavy JavaScript: remove unused plugins, and load chat widgets, trackers and "
    "embeds only after the page has appeared."
)
METRICS = {
    "lcp_ms": _Metric(
        "LCP",
        2500,
        4000,
        "Your main content takes {value:.1f}s to appear (good: under 2.5s).",
        "Visitors judge a site in its first seconds. If the main picture or headline is slow, "
        "many leave before seeing your offer.",
        "Speed up the largest image or text block at the top: use a smaller WebP/AVIF image, "
        'preload it with <link rel="preload">, and make sure your hosting responds quickly.',
        in_seconds=True,
    ),
    "cls": _Metric(
        "CLS",
        0.1,
        0.25,
        "Your page jumps around while it loads (layout shift {value:.2f}; good: under 0.1).",
        "When content moves, people tap the wrong button or lose their place. It feels broken "
        "and untrustworthy.",
        "Give every image, video and ad space a fixed width and height, and don't insert "
        "banners above content that's already visible.",
    ),
    "inp_ms": _Metric(
        "INP",
        200,
        500,
        "Your page takes {value:.0f} ms to react to taps and clicks (good: under 200 ms).",
        "Buttons that react slowly feel broken: people tap again, get frustrated, or give up "
        "on their order.",
        SLOW_SCRIPTS_FIX,
    ),
    "tbt_ms": _Metric(
        "TBT",
        200,
        600,
        "Heavy scripts freeze your page for {value:.0f} ms while it loads (good: under 200 ms).",
        "While the page is frozen, visitors can't scroll, tap menus or press buttons.",
        SLOW_SCRIPTS_FIX,
    ),
    "fcp_ms": _Metric(
        "FCP",
        1800,
        3000,
        "Visitors look at a blank screen for {value:.1f}s before anything appears "
        "(good: under 1.8s).",
        "A blank screen makes people think your site is down, so they press back.",
        "Remove render-blocking scripts and styles, turn on compression and caching, and use "
        "faster hosting or a CDN.",
        in_seconds=True,
    ),
}


class CoreWebVitals(Check):
    id = "performance.core_web_vitals"
    category = Category.PERFORMANCE
    title = "Core Web Vitals"
    weight = 8
    requires = frozenset({PAGESPEED})

    WHY = (
        "Core Web Vitals are Google's official measures of how fast and smooth a page feels. "
        "They are a ranking factor in Google search."
    )

    def run(self, ctx: AuditContext) -> list[Finding]:
        assert ctx.pagespeed is not None  # noqa: S101 (guaranteed by `requires`)
        test = ctx.pagespeed.mobile or ctx.pagespeed.desktop
        if test is None:
            return []

        # Real-visitor data is better than a single lab test, so prefer it when Google has it.
        field = test.field
        raw: dict[str, float | None]
        if field and field.lcp_ms is not None:
            source = "measured from real visitors over the last 28 days"
            raw = {
                "lcp_ms": field.lcp_ms,
                "cls": field.cls,
                "inp_ms": field.inp_ms,
                "fcp_ms": field.fcp_ms,
            }
        else:
            source = "measured in Google's lab test, as no real-visitor data exists yet"
            raw = {
                "lcp_ms": test.lcp_ms,
                "cls": test.cls,
                "tbt_ms": test.tbt_ms,
                "fcp_ms": test.fcp_ms,
            }
        values = {key: value for key, value in raw.items() if value is not None}
        if not values:
            return []

        ratings = {key: METRICS[key].rating(value) for key, value in values.items()}
        self.partial = sum(ratings.values()) / len(ratings)
        url = [ctx.homepage.final_url]
        findings = []
        for key, value in values.items():
            metric = METRICS[key]
            if ratings[key] == 1.0:
                continue
            poor = ratings[key] == 0.0
            findings.append(
                self.finding(
                    Severity.FAIL if poor else Severity.WARN,
                    f"{metric.describe(value)} ({metric.name}, {source}.)",
                    metric.why,
                    metric.fix,
                    effort=Level.MEDIUM,
                    impact=Level.HIGH if poor else Level.MEDIUM,
                    urls=url,
                )
            )
        if not findings:
            return [
                self.passed(
                    f'All Core Web Vitals are in Google\'s "good" range ({source}).', self.WHY, url
                )
            ]
        return findings


class PageWeight(Check):
    id = "performance.page_weight"
    category = Category.PERFORMANCE
    title = "Page weight"
    weight = 4
    requires = frozenset({PAGESPEED})

    WHY = (
        "Every megabyte has to travel to the visitor's phone. Heavy pages are slow on mobile "
        "data and use up visitors' data plans."
    )

    def run(self, ctx: AuditContext) -> list[Finding]:
        assert ctx.pagespeed is not None  # noqa: S101 (guaranteed by `requires`)
        test = ctx.pagespeed.mobile or ctx.pagespeed.desktop
        if test is None or test.total_bytes is None:
            return []
        size = test.total_bytes / MB
        message = f"Your homepage downloads {size:.1f} MB in total."
        url = [ctx.homepage.final_url]
        if size <= 2:
            return [self.passed(message + " That's nice and light.", self.WHY, url)]
        return [
            self.finding(
                Severity.WARN if size <= 4 else Severity.FAIL,
                message + " Aim for under 2 MB.",
                self.WHY,
                "Images are usually most of the weight: resize them to the size they're shown "
                "at and save them as WebP or AVIF. Also remove unused fonts, videos and scripts.",
                effort=Level.MEDIUM,
                impact=Level.MEDIUM,
                urls=url,
            )
        ]


def _images(tree: LexborHTMLParser) -> list[str]:
    """src of real images (ignores tiny inline data: images such as tracking pixels)."""
    return [
        img.attributes.get("src") or ""
        for img in tree.css("img")
        if not (img.attributes.get("src") or "").startswith("data:")
    ]


class ImageDimensions(Check):
    id = "performance.image_dimensions"
    category = Category.PERFORMANCE
    title = "Image sizes declared"
    weight = 3

    WHY = (
        "When the browser doesn't know an image's size in advance, the page jumps as each "
        "image loads, a main cause of visitors tapping the wrong thing."
    )

    def run(self, ctx: AuditContext) -> list[Finding]:
        total = 0
        unsized = 0
        pages: list[str] = []
        for page in ctx.html_pages:
            images = [
                img
                for img in ctx.dom(page).css("img")
                if not (img.attributes.get("src") or "").startswith("data:")
            ]
            bad = [
                i for i in images if not (i.attributes.get("width") and i.attributes.get("height"))
            ]
            total += len(images)
            unsized += len(bad)
            if bad:
                pages.append(page.final_url)
        if total == 0:
            return []
        self.partial = share_score(total, 0, unsized)
        if not unsized:
            return [self.passed(f"All {total} images declare their width and height.", self.WHY)]
        return [
            self.finding(
                Severity.WARN,
                f"{unsized} of your {total} images don't declare their width and height.",
                self.WHY,
                'Add width and height to each <img>, e.g. <img src="cake.jpg" width="800" '
                'height="600" alt="...">. CSS can still make them responsive.',
                impact=Level.MEDIUM,
                urls=pages,
            )
        ]


class LazyImages(Check):
    id = "performance.lazy_images"
    category = Category.PERFORMANCE
    title = "Images load when needed"
    weight = 3

    WHY = (
        "Images further down the page don't need to download before the visitor scrolls. "
        "Loading them later makes the first screen appear much faster."
    )
    FIX = (
        'Add loading="lazy" to images below the first screen (not to the main top image), '
        'e.g. <img src="gallery-3.jpg" loading="lazy" ...>.'
    )
    MIN_IMAGES = 4  # with fewer images, lazy loading hardly matters

    def run(self, ctx: AuditContext) -> list[Finding]:
        test = ctx.pagespeed.mobile if ctx.pagespeed else None
        if test is not None:  # Google measured which images were off-screen
            if not test.offscreen_images:
                return [
                    self.passed("Images below the first screen load only when needed.", self.WHY)
                ]
            return [
                self.finding(
                    Severity.WARN,
                    f"{len(test.offscreen_images)} images below the first screen load straight "
                    "away and slow it down.",
                    self.WHY,
                    self.FIX,
                    impact=Level.MEDIUM,
                    urls=[ctx.homepage.final_url],
                )
            ]

        pages = []
        candidates = 0
        for page in ctx.html_pages:
            tree = ctx.dom(page)
            if len(_images(tree)) < self.MIN_IMAGES:
                continue
            candidates += 1
            if not tree.css('img[loading="lazy"]'):
                pages.append(page.final_url)
        if candidates == 0:
            return []
        if not pages:
            return [self.passed("Your image-heavy pages use lazy loading.", self.WHY)]
        return [
            self.finding(
                Severity.WARN,
                on_pages(
                    len(pages),
                    len(ctx.html_pages),
                    "loads all of its images straight away.",
                    "load all of their images straight away.",
                ),
                self.WHY,
                self.FIX,
                impact=Level.LOW,
                urls=pages,
            )
        ]


class RenderBlocking(Check):
    id = "performance.render_blocking"
    category = Category.PERFORMANCE
    title = "Files that block the first screen"
    weight = 4

    WHY = (
        "Some scripts and stylesheets make the browser wait before drawing anything. Visitors "
        "see a blank page until they have all downloaded."
    )
    FIX = (
        'Add defer (or async) to scripts in <head>, e.g. <script src="app.js" defer>, inline '
        "the small amount of CSS needed for the first screen, and load the rest later."
    )

    def run(self, ctx: AuditContext) -> list[Finding]:
        test = ctx.pagespeed.mobile if ctx.pagespeed else None
        url = [ctx.homepage.final_url]
        if test is not None:
            if not test.render_blocking:
                return [
                    self.passed("Nothing blocks your first screen from appearing.", self.WHY, url)
                ]
            savings = test.render_blocking_savings_ms
            return [
                self.finding(
                    Severity.WARN,
                    f"{len(test.render_blocking)} files delay your first screen"
                    + (f" by about {savings / 1000:.1f}s." if savings else "."),
                    self.WHY,
                    self.FIX,
                    effort=Level.MEDIUM,
                    impact=Level.MEDIUM if savings >= 500 else Level.LOW,
                    urls=url,
                )
            ]

        head = ctx.tree(ctx.homepage).css_first("head")
        if head is None:
            return []
        blocking = [
            script.attributes.get("src")
            for script in head.css("script[src]")
            if "async" not in script.attributes
            and "defer" not in script.attributes
            and (script.attributes.get("type") or "").lower() != "module"
        ]
        if not blocking:
            return [
                self.passed(
                    "Scripts in your page header don't block the first screen.", self.WHY, url
                )
            ]
        return [
            self.finding(
                Severity.WARN,
                f"{len(blocking)} scripts in your page header make visitors wait before "
                "anything appears.",
                self.WHY,
                self.FIX,
                impact=Level.LOW,
                urls=url,
            )
        ]
