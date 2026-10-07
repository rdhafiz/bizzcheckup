"""Engine limits and options. Django settings fill these in (see checkups app)."""

from pydantic import BaseModel, Field

USER_AGENT = "BizzCheckup/0.1 (+https://ridwanulhafiz.me)"
ROBOTS_AGENT_NAME = "BizzCheckup"  # the name robots.txt rules refer to


# AI crawlers checked in robots.txt. "search" bots fetch pages to answer questions
# live (blocking them hides you from AI answers); "training" bots collect data to
# train models (blocking them is a legitimate business choice).
AI_CRAWLERS: dict[str, str] = {
    "OAI-SearchBot": "search",  # ChatGPT search
    "PerplexityBot": "search",  # Perplexity
    "GPTBot": "training",  # OpenAI
    "ClaudeBot": "training",  # Anthropic
}

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
    render_timeout: float = 45.0  # seconds for the browser to load the homepage
    viewport_width: int = 1280
    viewport_height: int = 800
    total_timeout: float = 180.0  # whole check-up, seconds
    psi_api_key: str = ""
    psi_timeout: float = 90.0  # PageSpeed runs a full Lighthouse test; it can be slow
