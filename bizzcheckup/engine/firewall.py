"""Recognise bot-protection "checkpoint" pages (Vercel, Cloudflare, SiteGround, ...).

Some hosts answer automated visitors with a "verifying your browser" page instead of
the website. If we analysed that page, the report would describe the checkpoint, not
the business's site. So the crawler and the browser collector both use this to notice
it, stop, and say so honestly. We never try to trick these systems: the site owner
switched them on, and BizzCheckup stays an identifiable visitor.
"""

from collections.abc import Mapping

# Phrases that appear on common checkpoint pages (lower-case).
_GENERIC_MARKERS = (
    "verifying your browser",
    "verify you are human",
    "are you a robot",
    "just a moment...",
    "checking your browser",
)


def checkpoint_provider(status: int, headers: Mapping[str, str], html: str) -> str | None:
    """The firewall's name if this answer is a checkpoint page, "" if unknown, else None.

    `headers` must have lower-case keys.
    """
    if headers.get("x-vercel-mitigated", "").lower() in ("challenge", "deny"):
        return "Vercel"
    if headers.get("cf-mitigated", "").lower() == "challenge":
        return "Cloudflare"

    head = html[:20000].lower()
    if "vercel security checkpoint" in head:
        return "Vercel"
    # Real pages may mention "captcha" (e.g. a contact form), so the generic markers
    # only count on error answers or very short pages, which is what checkpoints are.
    suspicious = status in (403, 429, 503) or len(html) < 15000
    if not suspicious:
        return None
    if "cf-chl" in head or "challenge-platform" in head:
        return "Cloudflare"
    if "sgcaptcha" in head:
        return "SiteGround"
    if "imunify" in head:
        return "Imunify360"
    if any(marker in head for marker in _GENERIC_MARKERS) or (
        status in (403, 429, 503) and "captcha" in head
    ):
        return ""
    return None


def blocked_message(provider: str, what: str) -> str:
    """A friendly sentence for the report: what was blocked and how to allow it."""
    name = f" ({provider})" if provider else ""
    return (
        f"Your website's security firewall{name} showed our {what} a \"verify you're human\" "
        "check instead of your site. Normal visitors are probably fine. To include this in "
        'your check-up, allow visitors whose browser identity contains "BizzCheckup" in '
        "your hosting's bot protection settings."
    )
