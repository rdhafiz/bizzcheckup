"""Recognising bot-protection checkpoint pages."""

import pytest

from bizzcheckup.engine.firewall import blocked_message, checkpoint_provider


@pytest.mark.parametrize(
    ("status", "headers", "html", "expected"),
    [
        (429, {"x-vercel-mitigated": "challenge"}, "", "Vercel"),
        (
            200,
            {},
            "<title>Vercel Security Checkpoint</title><p>We're verifying your browser</p>",
            "Vercel",
        ),
        (403, {"cf-mitigated": "challenge"}, "", "Cloudflare"),
        (503, {}, "<script src='/cdn-cgi/challenge-platform/x.js'></script>", "Cloudflare"),
        (403, {}, "<title>sgcaptcha</title>", "SiteGround"),
        (200, {}, "<h1>Just a moment...</h1>", ""),  # short page with a generic marker
        (429, {}, "<p>Please complete the captcha</p>", ""),
        (500, {}, "<h1>Internal server error</h1>", None),  # a real error, not a firewall
        (200, {}, "LONG_NORMAL_PAGE", None),  # a long page that mentions captcha
    ],
)
def test_checkpoint_provider(
    status: int, headers: dict[str, str], html: str, expected: str | None
) -> None:
    if html == "LONG_NORMAL_PAGE":  # built here: huge test ids break on Windows
        html = "<form>captcha</form>" + "<p>shop</p>" * 3000
    assert checkpoint_provider(status, headers, html) == expected


def test_blocked_message_names_the_provider_and_how_to_allow_us() -> None:
    message = blocked_message("Vercel", "browser")
    assert "security firewall (Vercel)" in message
    assert "our browser" in message
    assert '"BizzCheckup"' in message
    assert "()" not in blocked_message("", "browser")
