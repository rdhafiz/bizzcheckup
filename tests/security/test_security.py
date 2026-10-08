"""Security & abuse protection: the acceptance checklist, one test at a time."""

import importlib
from collections.abc import Iterator
from datetime import timedelta
from unittest.mock import patch

import httpx
import pytest
import respx
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from bizzcheckup.checkups import tasks
from bizzcheckup.checkups.models import Checkup
from bizzcheckup.core import security

pytestmark = pytest.mark.django_db

START = "/checkups/new/"


@pytest.fixture(autouse=True)
def no_real_queue() -> Iterator[None]:
    """Starting a check-up must not need Redis in these tests."""
    with patch.object(tasks.run_checkup, "delay"):
        yield


def start(client: Client, url: str = "shop.test", ip: str = "203.0.113.9", **fields: str):  # type: ignore[no-untyped-def]
    """Submit the landing-page form as a visitor from `ip`."""
    return client.post(START, {"url": url, "consent": "on", **fields}, REMOTE_ADDR=ip)


# --- SSRF: internal addresses are refused before anything is queued -----------------


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1",
        "http://localhost/",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.5/",
        "http://192.168.1.1/",
        "http://[::1]/",
        "http://internal.test/",  # a public-looking name that resolves to 10.0.0.7
        "https://shop.test:8443/",  # non-standard port
        "ftp://shop.test/",  # not http/https
    ],
)
def test_internal_addresses_are_rejected(client: Client, url: str) -> None:
    response = start(client, url)
    assert response.status_code == 400
    assert Checkup.objects.count() == 0


def test_rejection_message_is_friendly(client: Client) -> None:
    html = start(client, "http://169.254.169.254/").content.decode()
    assert "private or internal network" in html


def test_redirects_to_internal_addresses_are_rejected_by_the_engine() -> None:
    """Covered in depth by the engine tests; listed here for the checklist."""
    from tests.engine import test_fetcher, test_render, test_runner

    assert hasattr(test_fetcher, "test_redirect_to_private_address_is_blocked")
    assert hasattr(test_runner, "test_blocked_url_gives_friendly_error")
    assert hasattr(test_render, "test_render_collects_browser_data_safely")


# --- rate limit: 5 per IP per hour ------------------------------------------------------


def test_sixth_checkup_from_one_ip_within_an_hour_is_refused(client: Client) -> None:
    for number in range(5):
        assert start(client, f"site{number}.test").status_code == 302

    response = start(client, "site6.test")

    assert response.status_code == 429
    assert "several check-ups in the last hour" in response.content.decode()
    assert Checkup.objects.count() == 5


def test_checkups_that_never_started_do_not_count(client: Client) -> None:
    """If OUR queue was down, those failed check-ups aren't held against the visitor."""
    for number in range(5):
        start(client, f"site{number}.test")
    Checkup.objects.update(status=Checkup.Status.FAILED, started_at=None)

    assert start(client, "retry.test").status_code == 302


def test_failed_checkups_that_ran_still_count(client: Client) -> None:
    for number in range(5):
        start(client, f"site{number}.test")
    Checkup.objects.update(status=Checkup.Status.FAILED, started_at=timezone.now())

    assert start(client, "again.test").status_code == 429


def test_rate_limit_is_per_ip(client: Client) -> None:
    for number in range(5):
        start(client, f"site{number}.test", ip="203.0.113.1")
    assert start(client, "other.test", ip="203.0.113.2").status_code == 302


def test_rate_limit_window_is_one_hour(client: Client) -> None:
    for number in range(5):
        start(client, f"site{number}.test")
    Checkup.objects.update(created_at=timezone.now() - timedelta(minutes=61))
    assert start(client, "later.test").status_code == 302


# --- reuse: same URL within 24 hours ----------------------------------------------------------


def done_checkup(url: str = "https://shop.test/", age: timedelta = timedelta(hours=1)) -> Checkup:
    checkup = Checkup.objects.create(url=url, domain="shop.test", status=Checkup.Status.DONE)
    Checkup.objects.filter(pk=checkup.pk).update(created_at=timezone.now() - age)
    return checkup


def test_same_url_within_24_hours_reuses_the_report(client: Client) -> None:
    earlier = done_checkup()

    response = start(client, "SHOP.test/#anything")  # normalises to the same URL

    assert response["Location"] == reverse("checkups:detail", args=[earlier.pk])
    assert Checkup.objects.count() == 1


def test_reused_reports_do_not_count_towards_the_rate_limit(client: Client) -> None:
    done_checkup()
    for _ in range(10):
        start(client, "shop.test")
    assert start(client, "new.test").status_code == 302


def test_report_older_than_24_hours_is_not_reused(client: Client) -> None:
    done_checkup(age=timedelta(hours=25))
    start(client, "shop.test")
    assert Checkup.objects.count() == 2


def test_check_already_running_is_reused(client: Client) -> None:
    running = Checkup.objects.create(
        url="https://shop.test/", domain="shop.test", status=Checkup.Status.RUNNING
    )
    assert start(client, "shop.test")["Location"] == reverse("checkups:detail", args=[running.pk])


# --- global capacity ---------------------------------------------------------------------


def test_global_cap_on_waiting_and_running_checkups(client: Client, settings) -> None:  # type: ignore[no-untyped-def]
    settings.CHECKUP_QUEUE_CAP = 2
    for name in ("a", "b"):
        Checkup.objects.create(url=f"https://{name}.test/", domain=f"{name}.test")

    response = start(client, "c.test")

    assert response.status_code == 503
    assert "a lot of websites right now" in response.content.decode()


# --- bots: honeypot and Turnstile ----------------------------------------------------------


def test_honeypot_blocks_bots(client: Client) -> None:
    response = start(client, "shop.test", website="https://spam.example")
    assert response.status_code == 400
    assert Checkup.objects.count() == 0


def test_honeypot_field_is_on_the_page_but_hidden(client: Client) -> None:
    html = client.get("/").content.decode()
    assert 'name="website"' in html
    assert 'class="honeypot" aria-hidden="true"' in html


def test_turnstile_is_off_without_keys(client: Client) -> None:
    assert "cf-turnstile" not in client.get("/").content.decode()
    assert start(client).status_code == 302


@pytest.fixture
def turnstile_on(settings) -> None:  # type: ignore[no-untyped-def]
    settings.TURNSTILE_SITE_KEY = "site-key"
    settings.TURNSTILE_SECRET_KEY = "secret-key"


@pytest.mark.usefixtures("turnstile_on")
def test_turnstile_widget_and_csp_when_enabled(client: Client) -> None:
    response = client.get("/")
    assert 'data-sitekey="site-key"' in response.content.decode()
    assert "https://challenges.cloudflare.com" in response["Content-Security-Policy"]


@pytest.mark.usefixtures("turnstile_on")
@pytest.mark.parametrize(("success", "status"), [(True, 302), (False, 400)])
def test_turnstile_token_is_verified(client: Client, success: bool, status: int) -> None:
    with respx.mock(assert_all_called=True) as mock:
        route = mock.post(security.TURNSTILE_VERIFY_URL).respond(json={"success": success})
        response = start(client, **{"cf-turnstile-response": "token-123"})

    assert response.status_code == status
    sent = route.calls.last.request.content.decode()
    assert "secret=secret-key" in sent
    assert "response=token-123" in sent


@pytest.mark.usefixtures("turnstile_on")
def test_turnstile_fails_closed_when_cloudflare_is_unreachable(client: Client) -> None:
    with respx.mock() as mock:
        mock.post(security.TURNSTILE_VERIFY_URL).mock(side_effect=httpx.ConnectError("down"))
        assert start(client, **{"cf-turnstile-response": "t"}).status_code == 400


# --- privacy: IPs only as salted hashes ---------------------------------------------------------


def test_ip_is_stored_only_as_a_salted_hash(client: Client) -> None:
    start(client, ip="198.51.100.23")
    stored = Checkup.objects.get().ip_hash

    assert "198.51.100.23" not in stored
    assert len(stored) == 64
    assert stored == security.hash_ip("198.51.100.23")  # same visitor, same hash


def test_hash_depends_on_the_salt(settings) -> None:  # type: ignore[no-untyped-def]
    first = security.hash_ip("198.51.100.23")
    settings.IP_HASH_SALT = "a-different-salt"
    assert security.hash_ip("198.51.100.23") != first


def test_forwarded_for_header_is_ignored_unless_trusted(rf, settings) -> None:  # type: ignore[no-untyped-def]
    request = rf.get("/", REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="1.2.3.4")
    assert security.client_ip(request) == "10.0.0.1"
    settings.TRUST_X_FORWARDED_FOR = True
    assert security.client_ip(request) == "1.2.3.4"


def test_client_ip_header_wins_when_set(rf, settings) -> None:  # type: ignore[no-untyped-def]
    # Cloudflare appends the real address to a faked X-Forwarded-For.
    request = rf.get(
        "/",
        REMOTE_ADDR="172.29.0.1",
        HTTP_X_FORWARDED_FOR="1.2.3.4, 198.51.100.7",
        HTTP_CF_CONNECTING_IP="198.51.100.7",
    )
    settings.TRUST_X_FORWARDED_FOR = True
    assert security.client_ip(request) == "1.2.3.4"
    settings.CLIENT_IP_HEADER = "CF-Connecting-IP"
    assert security.client_ip(request) == "198.51.100.7"


def test_client_ip_header_missing_falls_back(rf, settings) -> None:  # type: ignore[no-untyped-def]
    settings.CLIENT_IP_HEADER = "CF-Connecting-IP"
    request = rf.get("/", REMOTE_ADDR="10.0.0.1")
    assert security.client_ip(request) == "10.0.0.1"


# --- headers, CSRF, production settings ---------------------------------------------------------


def test_security_headers(client: Client) -> None:
    response = client.get("/")
    csp = response["Content-Security-Policy"]
    for directive in (
        "default-src 'self'",
        "script-src 'self'",
        "style-src 'self'",
        "object-src 'none'",
        "frame-ancestors 'none'",
        "img-src 'self' data: https://ridwanulhafiz.me",  # branding photo host
    ):
        assert directive in csp
    assert "unsafe-inline" not in csp
    assert response["X-Frame-Options"] == "DENY"
    assert response["X-Content-Type-Options"] == "nosniff"
    assert response["Referrer-Policy"] == "strict-origin-when-cross-origin"
    assert "camera=()" in response["Permissions-Policy"]


def test_csrf_protection_is_on() -> None:
    client = Client(enforce_csrf_checks=True)
    assert client.post(START, {"url": "shop.test"}).status_code == 403


def test_production_settings_are_locked_down(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DJANGO_DEBUG", "True")  # even if someone sets it by mistake
    prod = importlib.import_module("config.settings.prod")
    prod = importlib.reload(prod)
    assert prod.DEBUG is False
    assert prod.SECURE_SSL_REDIRECT is True
    assert prod.SESSION_COOKIE_SECURE is True
    assert prod.CSRF_COOKIE_SECURE is True
    assert prod.SECURE_HSTS_SECONDS >= 31536000
