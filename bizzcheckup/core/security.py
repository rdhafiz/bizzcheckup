"""Visitor privacy and bot protection: IP hashing, Cloudflare Turnstile, security headers."""

import hashlib
import hmac
import logging
from collections.abc import Callable
from urllib.parse import urlsplit

import httpx
from django.conf import settings
from django.http import HttpRequest, HttpResponse

logger = logging.getLogger(__name__)

TURNSTILE_VERIFY_URL = "https://challenges.cloudflare.com/turnstile/v0/siteverify"
TURNSTILE_ORIGIN = "https://challenges.cloudflare.com"


# --- IP addresses: only ever stored as salted hashes ------------------------------


def client_ip(request: HttpRequest) -> str:
    """The visitor's IP address.

    Behind a reverse proxy (nginx, a load balancer) REMOTE_ADDR is the proxy, so the
    first address in X-Forwarded-For is used, but only when TRUST_X_FORWARDED_FOR is
    on, because visitors can fake that header when there is no proxy.

    Behind Cloudflare, even the first X-Forwarded-For entry can be faked (Cloudflare
    adds to the header a visitor sent). CLIENT_IP_HEADER="CF-Connecting-IP" reads the
    header Cloudflare always overwrites instead, so it wins when it's set.
    """
    if settings.CLIENT_IP_HEADER:
        meta_key = "HTTP_" + settings.CLIENT_IP_HEADER.upper().replace("-", "_")
        header_ip = str(request.META.get(meta_key, "")).strip()
        if header_ip:
            return header_ip
    if settings.TRUST_X_FORWARDED_FOR:
        forwarded = str(request.META.get("HTTP_X_FORWARDED_FOR", ""))
        if forwarded:
            return forwarded.split(",")[0].strip()
    return str(request.META.get("REMOTE_ADDR", ""))


def hash_ip(ip: str) -> str:
    """A salted HMAC-SHA256 of the IP: the same visitor gives the same hash (for rate
    limiting), but the address itself can't be read back from the database."""
    salt = settings.IP_HASH_SALT.encode()
    return hmac.new(salt, ip.encode(), hashlib.sha256).hexdigest()


# --- Cloudflare Turnstile (optional "are you human?" check) ------------------------


def turnstile_enabled() -> bool:
    return bool(settings.TURNSTILE_SITE_KEY and settings.TURNSTILE_SECRET_KEY)


def verify_turnstile(token: str, ip: str) -> bool:
    """Ask Cloudflare whether the widget's token is genuine. Fails closed on errors."""
    if not token:
        return False
    try:
        response = httpx.post(
            TURNSTILE_VERIFY_URL,
            data={"secret": settings.TURNSTILE_SECRET_KEY, "response": token, "remoteip": ip},
            timeout=5,
        )
        return bool(response.json().get("success"))
    except (httpx.HTTPError, ValueError):
        logger.warning("Turnstile verification failed", exc_info=True)
        return False


# --- Security headers ---------------------------------------------------------------


def content_security_policy() -> str:
    """Only our own files may load, plus the branding photo host and Turnstile if used."""
    img = ["'self'", "data:"]
    photo = branding_photo_origin()
    if photo:
        img.append(photo)
    script = ["'self'"]
    frame = ["'none'"]
    connect = ["'self'"]
    if turnstile_enabled():
        script.append(TURNSTILE_ORIGIN)
        frame = [TURNSTILE_ORIGIN]
        connect.append(TURNSTILE_ORIGIN)
    directives = {
        "default-src": ["'self'"],
        "script-src": script,
        "style-src": ["'self'"],
        "img-src": img,
        "font-src": ["'self'"],
        "connect-src": connect,
        "frame-src": frame,
        "object-src": ["'none'"],
        "base-uri": ["'self'"],
        "form-action": ["'self'"],
        "frame-ancestors": ["'none'"],
    }
    return "; ".join(f"{name} {' '.join(values)}" for name, values in directives.items())


def origin_of(url: str) -> str:
    parts = urlsplit(url)
    return f"{parts.scheme}://{parts.netloc}" if parts.scheme and parts.netloc else ""


def branding_photo_origin() -> str:
    """The consultant's photo in branding.yaml may come from their own website."""
    from bizzcheckup.reports.branding import load_branding  # avoids an import cycle

    try:
        photo = load_branding().photo_url
    except Exception:  # a broken branding.yaml is reported by the system check instead
        return ""
    return origin_of(str(photo)) if photo else ""


class SecurityHeadersMiddleware:
    """Adds Content-Security-Policy, Permissions-Policy and friends to every response."""

    def __init__(self, get_response: Callable[[HttpRequest], HttpResponse]) -> None:
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        response = self.get_response(request)
        response.setdefault("Content-Security-Policy", content_security_policy())
        response.setdefault(
            "Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=()"
        )
        response.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        return response
