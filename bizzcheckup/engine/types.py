"""Data models shared by the whole engine (Pydantic v2).

Pydantic checks every value when an object is created, so a Finding with a
typo'd severity or a missing "how to fix" fails loudly in tests instead of
showing up broken in a client's report.
"""

from datetime import datetime
from enum import StrEnum
from functools import cached_property
from urllib.robotparser import RobotFileParser

from pydantic import BaseModel, ConfigDict, Field


class Category(StrEnum):
    """The five "vital signs". Values are the ids used in branding.yaml."""

    PERFORMANCE = "performance"
    ACCESSIBILITY = "accessibility"
    BEST_PRACTICES = "best_practices"
    SEO = "seo"
    AGENTIC = "agentic"

    @property
    def label(self) -> str:
        return CATEGORY_LABELS[self]


CATEGORY_LABELS: dict[Category, str] = {
    Category.PERFORMANCE: "Performance",
    Category.ACCESSIBILITY: "Accessibility",
    Category.BEST_PRACTICES: "Best practices",
    Category.SEO: "SEO",
    Category.AGENTIC: "Agentic browsing",
}


class Severity(StrEnum):
    PASS = "pass"  # noqa: S105 (a check result, not a password)
    INFO = "info"
    WARN = "warn"
    FAIL = "fail"


class Level(StrEnum):
    """Used for both effort (how hard to fix) and impact (how much it matters)."""

    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Band(StrEnum):
    URGENT = "urgent"
    ATTENTION = "attention"
    HEALTHY = "healthy"

    @property
    def label(self) -> str:
        return BAND_LABELS[self]


BAND_LABELS: dict[Band, str] = {
    Band.URGENT: "Needs urgent care",
    Band.ATTENTION: "Needs attention",
    Band.HEALTHY: "Healthy",
}


class Snippet(BaseModel):
    """Ready-to-use code that fixes a finding, e.g. the JSON-LD schema a page should have."""

    model_config = ConfigDict(frozen=True)

    title: str = Field(min_length=1)  # what it is for, e.g. "About page · https://... (missing)"
    code: str = Field(min_length=1)
    language: str = "html"  # "html" = ready to paste, "text" = an explanation
    image: str = ""  # a picture of where it is: a key of the report's pictures
    note: str = ""  # what's wrong, in words, shown above the code


class Shot(BaseModel):
    """Where a problem is: one element on one page, photographed after the checks run.

    Checks only say *where* (they never use a browser); the shots step
    (collectors/shots.py) opens the page, outlines the element in red and fills `image`.
    """

    model_config = ConfigDict(frozen=True)

    page: str  # the page's address
    selector: str  # CSS path to the element, from the parsed page
    # Found by attribute first when there is one (robust if scripts moved things around):
    # the first <match_tag> whose <match_attr> equals <match_value>.
    match_tag: str = ""
    match_attr: str = ""
    match_value: str = ""
    # Its visible text (first words), checked before outlining: positions can shift between
    # two visits of the same page (menus, injected banners), the text doesn't.
    match_text: str = ""
    label: str = Field(min_length=1)  # what it is, e.g. '<img src="banner.jpg">'
    device: str = "desktop"  # "desktop" or "mobile" (phone-sized window)
    image: str = ""  # key of its picture in the report's images, once taken


class Finding(BaseModel):
    """One result of one check: something wrong, or something healthy."""

    model_config = ConfigDict(frozen=True)

    check_id: str = Field(min_length=1)
    category: Category
    severity: Severity
    message: str = Field(min_length=1)  # what we found, in plain words
    why_it_matters: str = Field(min_length=1)  # business impact, shown first
    how_to_fix: str = Field(min_length=1)  # the technical fix
    effort: Level
    impact: Level
    affected_urls: list[str] = Field(default_factory=list)
    snippets: list[Snippet] = Field(default_factory=list)  # optional ready-made fixes
    shots: list[Shot] = Field(default_factory=list)  # where it is on the page (pictures)


class Page(BaseModel):
    """One fetched page (or file such as robots.txt)."""

    url: str  # the URL we asked for
    final_url: str  # after redirects
    status_code: int
    headers: dict[str, str] = Field(default_factory=dict)  # keys lowercased
    text: str = ""
    size_bytes: int = 0
    truncated: bool = False  # True when the body was cut at the size limit
    elapsed_ms: int = 0
    redirect_chain: list[str] = Field(default_factory=list)
    # The raw bytes, only when asked for (images); never saved in the report JSON.
    body: bytes | None = Field(default=None, exclude=True, repr=False)

    @property
    def content_type(self) -> str:
        return self.headers.get("content-type", "").split(";")[0].strip().lower()

    @property
    def is_html(self) -> bool:
        return self.content_type in ("text/html", "application/xhtml+xml")

    @property
    def ok(self) -> bool:
        return 200 <= self.status_code < 300


class RobotsInfo(BaseModel):
    """What we learned from /robots.txt."""

    url: str
    exists: bool
    status_code: int | None = None
    text: str = ""
    sitemaps: list[str] = Field(default_factory=list)  # "Sitemap:" lines

    @cached_property
    def _parser(self) -> RobotFileParser:
        parser = RobotFileParser()
        parser.parse(self.text.splitlines() if self.exists else [])
        return parser

    def allows(self, agent: str, url: str) -> bool:
        """Does robots.txt let `agent` (e.g. "GPTBot") visit `url`?"""
        return self._parser.can_fetch(agent, url)


class SitemapInfo(BaseModel):
    """What we learned from the sitemap(s)."""

    checked: list[str] = Field(default_factory=list)  # sitemap URLs we fetched
    found: bool = False  # at least one valid sitemap
    urls: list[str] = Field(default_factory=list)  # page URLs listed in it


class CrawlResult(BaseModel):
    start_url: str
    final_url: str  # homepage after redirects (e.g. http -> https)
    pages: list[Page]  # homepage first, then other HTML pages
    robots: RobotsInfo
    sitemap: SitemapInfo
    skipped_by_robots: list[str] = Field(default_factory=list)
    errors: dict[str, str] = Field(default_factory=dict)  # url -> what went wrong
    # Every page address of the site we came across (sitemap and links), checked or not.
    discovered: list[str] = Field(default_factory=list)

    @property
    def homepage(self) -> Page:
        return self.pages[0]


class AgentProbe(BaseModel):
    """How the homepage answered one User-Agent."""

    status_code: int = 0  # 0 = no answer
    text_length: int = 0
    challenge: bool = False  # a "prove you're human" / bot-protection page


class ProbeResults(BaseModel):
    """Extra requests made after crawling (see collectors/probes.py)."""

    # What happens when someone visits the http:// version of the homepage.
    http_final_url: str | None = None  # where http:// ended up
    http_error: str = ""  # set when http:// could not be reached at all
    # Internal link -> HTTP status (0 = unreachable), and the pages it appears on.
    link_status: dict[str, int] = Field(default_factory=dict)
    link_sources: dict[str, list[str]] = Field(default_factory=dict)
    # The same for links to other websites, and for images (any website).
    external_status: dict[str, int] = Field(default_factory=dict)
    external_sources: dict[str, list[str]] = Field(default_factory=dict)
    external_skipped: list[str] = Field(default_factory=list)  # social networks: not checkable
    image_status: dict[str, int] = Field(default_factory=dict)
    image_sources: dict[str, list[str]] = Field(default_factory=dict)
    # /llms.txt: a plain-text guide to your site written for AI assistants.
    llms_txt_status: int = 0
    llms_txt_text: str = ""  # first few KB, only when it really is a text file
    # The same homepage requested as an AI agent and as a normal browser.
    as_ai_agent: AgentProbe | None = None
    as_browser: AgentProbe | None = None
    # The homepage's link preview picture (og:image): does it load, and is it an image?
    og_image_url: str = ""
    og_image_status: int = 0  # 0 = not checked or unreachable
    og_image_type: str = ""  # e.g. "image/jpeg", from the file's first bytes ("" = not an image)
    og_image_too_big: bool = False
    og_image: bytes | None = Field(default=None, exclude=True, repr=False)


class AxeNode(BaseModel):
    """One element that fails an axe rule: where it is, what it is, and what's wrong."""

    target: str  # CSS selector
    html: str = ""  # the element's opening HTML (shortened)
    summary: str = ""  # axe's explanation, e.g. the colours and the contrast ratio
    text: str = ""  # its visible text, to recognise it
    image: str = ""  # key of its screenshot in the report's pictures ("" = none)


class AxeRule(BaseModel):
    """One axe-core accessibility rule that failed on the rendered page."""

    id: str  # e.g. "color-contrast"
    impact: str  # "critical" | "serious" | "moderate" | "minor"
    help: str  # short description from axe
    help_url: str
    nodes: int  # how many elements fail it
    targets: list[str] = Field(default_factory=list)  # CSS selectors of a few of them
    details: list[AxeNode] = Field(default_factory=list)  # the same few, in detail


class Cookie(BaseModel):
    name: str
    domain: str
    third_party: bool


class DeviceView(BaseModel):
    """The homepage on a phone or tablet: does it fit, and can people tap and read it?"""

    name: str  # "mobile" | "tablet"
    width: int  # screen width in CSS pixels
    height: int
    layout_width: int  # the width the page was laid out at (980 = desktop page shrunk)
    scroll_width: int  # the page's width: wider than its layout means sideways scrolling
    overflowing: list[str] = Field(default_factory=list)  # elements sticking out
    overflowing_selectors: list[str] = Field(default_factory=list)  # ...their CSS paths
    tap_targets: int = 0  # links and buttons on the first load
    small_tap_targets: int = 0  # smaller than 24 x 24 pixels
    small_tap_examples: list[str] = Field(default_factory=list)
    small_tap_selectors: list[str] = Field(default_factory=list)  # ...their CSS paths
    text_chars: int = 0  # visible text, in characters
    small_text_chars: int = 0  # ... of which smaller than 12 px
    screenshot_jpeg: bytes | None = Field(default=None, exclude=True, repr=False)

    @property
    def zoomed_out(self) -> bool:
        """The desktop page shown shrunk (no mobile layout), so everything is tiny."""
        return self.layout_width > self.width + 2

    @property
    def fits(self) -> bool:
        """No sideways scrolling (a pixel or two is rounding)."""
        return self.scroll_width <= self.layout_width + 2

    @property
    def small_text_share(self) -> float:
        return self.small_text_chars / self.text_chars if self.text_chars else 0.0

    @property
    def label(self) -> str:
        return "phone" if self.name == "mobile" else self.name


class RenderResult(BaseModel):
    """What a real browser (Chromium via Playwright) saw on the homepage."""

    url: str
    html: str  # the page after JavaScript ran
    text_length: int  # characters of visible text after JavaScript
    console_errors: list[str] = Field(default_factory=list)
    cookies: list[Cookie] = Field(default_factory=list)
    libraries: dict[str, str] = Field(default_factory=dict)  # name -> version
    axe_violations: list[AxeRule] = Field(default_factory=list)
    axe_passes: list[str] = Field(default_factory=list)  # ids of rules that passed
    blocked_requests: list[str] = Field(default_factory=list)  # stopped by the SSRF guard
    devices: list[DeviceView] = Field(default_factory=list)  # the phone and tablet views
    # Screenshots of flagged elements, outlined: "element-1" -> JPEG (AxeNode.image).
    element_shots: dict[str, bytes] = Field(default_factory=dict, exclude=True, repr=False)

    def device(self, name: str) -> "DeviceView | None":
        return next((view for view in self.devices if view.name == name), None)

    # The picture for the report cover. exclude=True keeps it out of the JSON.
    screenshot_jpeg: bytes | None = Field(default=None, exclude=True, repr=False)


class FieldData(BaseModel):
    """Speed measured from REAL Chrome users over the last 28 days (Chrome UX Report)."""

    lcp_ms: float | None = None  # Largest Contentful Paint
    cls: float | None = None  # Cumulative Layout Shift
    inp_ms: float | None = None  # Interaction to Next Paint
    fcp_ms: float | None = None  # First Contentful Paint
    origin_wide: bool = False  # True = data for the whole site, not just this page


class SpeedTest(BaseModel):
    """One Lighthouse run by Google PageSpeed Insights (mobile or desktop)."""

    strategy: str  # "mobile" | "desktop"
    score: float  # 0.0-1.0 (Lighthouse performance score)
    lcp_ms: float | None = None
    cls: float | None = None
    tbt_ms: float | None = None  # Total Blocking Time (lab stand-in for INP)
    fcp_ms: float | None = None
    speed_index_ms: float | None = None
    total_bytes: int | None = None  # page weight
    render_blocking: list[str] = Field(default_factory=list)  # resource URLs
    render_blocking_savings_ms: float = 0
    offscreen_images: list[str] = Field(default_factory=list)  # should be lazy-loaded
    unsized_images: list[str] = Field(default_factory=list)
    field: FieldData | None = None


class PageSpeedResult(BaseModel):
    mobile: SpeedTest | None = None
    desktop: SpeedTest | None = None


class CheckStatus(StrEnum):
    RAN = "ran"
    SKIPPED = "skipped"  # a requirement (e.g. PageSpeed key) was missing
    ERROR = "error"  # the check crashed; it is left out of the score


class CheckResult(BaseModel):
    check_id: str
    category: Category
    title: str
    weight: int
    status: CheckStatus
    score: float | None = None  # 0.0-1.0, None unless status is RAN
    findings: list[Finding] = Field(default_factory=list)
    note: str = ""  # why it was skipped or what went wrong


class CategoryScore(BaseModel):
    category: Category
    score: int | None  # None = "Not checked"
    band: Band | None
    checks_run: int
    checks_skipped: int
    note: str = ""


class LinkPreview(BaseModel):
    """How the homepage looks when its link is shared (Facebook, WhatsApp, LinkedIn, X)."""

    url: str
    domain: str
    title: str = ""
    description: str = ""
    image_url: str = ""
    image_ok: bool = False  # the picture loaded and really is an image


class ReportImage(BaseModel):
    """A picture that belongs to the report, e.g. a phone screenshot."""

    content_type: str  # image/jpeg, image/png, image/gif or image/webp
    data: bytes = Field(repr=False)


class AuditReport(BaseModel):
    """Everything the engine produces for one check-up. Saved as JSON."""

    url: str
    final_url: str
    started_at: datetime
    finished_at: datetime
    pages: list[str]  # URLs that were analysed
    discovered_pages: list[str] = Field(default_factory=list)  # every page we came across
    categories: list[CategoryScore]
    health_score: int | None
    health_band: Band | None
    results: list[CheckResult]
    notes: list[str] = Field(default_factory=list)
    browser_note: str = ""  # why the browser couldn't see the site (e.g. a firewall)
    link_preview: LinkPreview | None = None
    # Homepage screenshot (JPEG). Saved as a file by the web app, not in the JSON.
    screenshot_jpeg: bytes | None = Field(default=None, exclude=True, repr=False)
    # More pictures by name ("link_preview", "mobile", "tablet"), saved by the web app.
    images: dict[str, ReportImage] = Field(default_factory=dict, exclude=True, repr=False)

    @property
    def findings(self) -> list[Finding]:
        return [finding for result in self.results for finding in result.findings]

    def category(self, category: Category) -> CategoryScore:
        return next(c for c in self.categories if c.category == category)
