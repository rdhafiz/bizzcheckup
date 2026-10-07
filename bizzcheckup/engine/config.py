"""Engine limits and options. Django settings fill these in (see checkups app)."""

from pydantic import BaseModel, Field

USER_AGENT = "BizzCheckup/0.1 (+https://ridwanulhafiz.me)"
ROBOTS_AGENT_NAME = "BizzCheckup"  # the name robots.txt rules refer to


class EngineConfig(BaseModel):
    user_agent: str = USER_AGENT
    max_pages: int = Field(default=10, ge=1, le=50)  # never more than 50 (out of scope)
    max_concurrency: int = Field(default=2, ge=1)  # requests at the same time
    request_timeout: float = 15.0  # seconds per request
    retries: int = Field(default=2, ge=0)  # extra attempts after a failure
    max_redirects: int = 5
    max_page_bytes: int = 5 * 1024 * 1024  # 5 MB
    max_link_checks: int = 50  # internal links whose status we check
    total_timeout: float = 180.0  # whole check-up, seconds
    psi_api_key: str = ""
