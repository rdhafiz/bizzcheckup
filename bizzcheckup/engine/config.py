"""Engine limits and options. Django settings fill these in (see checkups app)."""

from typing import Any

from pydantic import BaseModel, Field

# Who we are, for site owners reading their logs.
BOT_IDENTITY = "BizzCheckup/0.1 (+https://ridwanulhafiz.me)"
# The User-Agent we send: a normal browser identity with ours added at the end, the way
# Google's Lighthouse does it. Many hosts' bot protection (e.g. Vercel's) challenges
# anything that doesn't look like a browser, so a bare "BizzCheckup/0.1" gets HTTP 429
# instead of the website. The site owner still sees exactly who visited.
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    f"Chrome/141.0.0.0 Safari/537.36 {BOT_IDENTITY}"
)
ROBOTS_AGENT_NAME = "BizzCheckup"  # the name robots.txt rules refer to


# How we open the homepage on a phone and a tablet (sizes in CSS pixels: a common
# Android phone and a common tablet held upright). Our identity stays at the end.
DEVICES: dict[str, dict[str, Any]] = {
    "mobile": {
        "width": 390,
        "height": 844,
        "user_agent": "Mozilla/5.0 (Linux; Android 14; Pixel 8) AppleWebKit/537.36 (KHTML, like "
        f"Gecko) Chrome/141.0.0.0 Mobile Safari/537.36 {BOT_IDENTITY}",
    },
    "tablet": {
        "width": 820,
        "height": 1180,
        "user_agent": "Mozilla/5.0 (Linux; Android 14; SM-X710) AppleWebKit/537.36 (KHTML, like "
        f"Gecko) Chrome/141.0.0.0 Safari/537.36 {BOT_IDENTITY}",
    },
}


# AI crawlers checked in robots.txt. "search" bots fetch pages to answer questions
# live (blocking them hides you from AI answers); "training" bots collect data to
# train models (blocking them is a legitimate business choice).
AI_CRAWLERS: dict[str, str] = {
    "OAI-SearchBot": "search",  # ChatGPT search
    "PerplexityBot": "search",  # Perplexity
    "GPTBot": "training",  # OpenAI
    "ClaudeBot": "training",  # Anthropic
}

# Social networks hide pages from robots behind a login and answer with misleading codes
# (Facebook: 400; a deleted page can even answer 200), so links to them can't be checked
# automatically. Matched on the site domain (www.facebook.com -> facebook.com).
WALLED_SITES = frozenset(
    {
        "facebook.com", "fb.com", "fb.me", "instagram.com", "linkedin.com", "lnkd.in",
        "x.com", "twitter.com", "t.co", "tiktok.com", "threads.net", "threads.com",
    }
)  # fmt: skip

# User-Agents used to compare how the site treats an AI agent vs a normal visitor.
AI_AGENT_USER_AGENT = (
    "Mozilla/5.0 AppleWebKit/537.36 (KHTML, like Gecko; compatible; GPTBot/1.2; "
    "+https://openai.com/gptbot)"
)
BROWSER_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/141.0.0.0 Safari/537.36"
)


class EngineConfig(BaseModel):
    user_agent: str = USER_AGENT
    max_pages: int = Field(default=10, ge=1, le=50)  # never more than 50 (out of scope)
    max_concurrency: int = Field(default=2, ge=1)  # requests at the same time
    request_timeout: float = 15.0  # seconds per request
    retries: int = Field(default=2, ge=0)  # extra attempts after a failure
    max_redirects: int = 5
    max_page_bytes: int = 5 * 1024 * 1024  # 5 MB
    max_link_checks: int = 50  # internal links whose status we check
    max_external_checks: int = 30  # links to other websites whose status we check
    max_image_checks: int = 40  # images whose status we check
    external_timeout: float = 8.0  # seconds per request to another website
    outside_budget: float = 30.0  # seconds for all link/image status checks together
    max_shots: int = Field(default=24, ge=0)  # pictures of where problems are (0 = none)
    shots_budget: float = 30.0  # seconds for taking those pictures
    render_timeout: float = 45.0  # seconds for the browser to load the homepage
    viewport_width: int = 1280
    viewport_height: int = 800
    total_timeout: float = 180.0  # whole check-up, seconds
    psi_api_key: str = ""
    psi_timeout: float = 90.0  # PageSpeed runs a full Lighthouse test; it can be slow
