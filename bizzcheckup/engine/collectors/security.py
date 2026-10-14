"""SECURITY collector: the security basics around a website, beyond its pages.

- the TLS certificate: when does it expire, who issued it?
- the domain name: when does its registration run out? (RDAP, the modern WHOIS)
- email: are there SPF and DMARC records, so nobody can send email as @your-domain?
  (looked up with DNS-over-HTTPS, so no DNS library is needed)

`probe_exposed_files()` (files that must never be public, like /.env) runs separately,
after the other collectors: some firewalls block a visitor who asks for /.env, and that
must not stop the browser from opening the site.

Every lookup is optional: when one fails, its field stays None and the check says it
couldn't find out, instead of reporting a problem that may not exist.
"""

import asyncio
import contextlib
import json
import re
import ssl
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from ..config import EngineConfig
from ..context import SECURITY, AuditContext
from ..fetcher import Fetcher, FetchError
from ..netguard import BlockedURLError, NetGuard
from ..urls import site_domain

# Cloudflare's public DNS, asked over HTTPS (it answers in JSON).
DOH_URL = "https://cloudflare-dns.com/dns-query"
# rdap.org forwards each domain to the registry that knows it (Verisign for .com, ...).
RDAP_URL = "https://rdap.org/domain/"
LOOKUP_TIMEOUT = 8.0  # seconds: these are small answers


async def collect_security(ctx: AuditContext, fetcher: Fetcher, config: EngineConfig) -> None:
    info = ctx.security
    parts = urlsplit(ctx.homepage.final_url)
    host = parts.hostname or ""
    info.domain = site_domain(host)

    async def certificate() -> None:
        if parts.scheme == "https":
            info.cert_expires, info.cert_issuer, info.cert_error = await read_certificate(
                host, fetcher.guard
            )

    await asyncio.gather(
        certificate(),
        lookup_domain_expiry(ctx, fetcher),
        lookup_email_records(ctx, fetcher),
    )
    ctx.capabilities.add(SECURITY)


# --- The TLS certificate ------------------------------------------------------------


async def read_certificate(host: str, guard: NetGuard) -> tuple[datetime | None, str, str]:
    """(expiry date, issuer, error) of the certificate `host` serves on port 443."""
    try:
        await guard.check_url(f"https://{host}/")  # SSRF protection, like every request
    except BlockedURLError as error:
        return None, "", str(error)
    context = ssl.create_default_context()
    try:
        _reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, 443, ssl=context, server_hostname=host),
            LOOKUP_TIMEOUT,
        )
    except ssl.SSLCertVerificationError as error:
        return None, "", error.verify_message or "the certificate isn't valid"
    except (OSError, TimeoutError, ssl.SSLError):
        return None, "", ""  # couldn't connect: say nothing rather than guess
    try:
        cert: dict[str, Any] = writer.get_extra_info("peercert") or {}
    finally:
        writer.close()
        with contextlib.suppress(OSError, ssl.SSLError):
            await writer.wait_closed()
    return certificate_expiry(cert), certificate_issuer(cert), ""


def certificate_expiry(cert: dict[str, Any]) -> datetime | None:
    not_after = cert.get("notAfter")
    if not not_after:
        return None
    return datetime.fromtimestamp(ssl.cert_time_to_seconds(not_after), UTC)


def certificate_issuer(cert: dict[str, Any]) -> str:
    """The issuer's organisation, e.g. "Let's Encrypt". (`issuer` is nested tuples.)"""
    for group in cert.get("issuer", ()):
        for key, value in group:
            if key == "organizationName":
                return str(value)
    return ""


# --- The domain name's registration ---------------------------------------------


async def lookup_domain_expiry(ctx: AuditContext, fetcher: Fetcher) -> None:
    info = ctx.security
    data = await get_json(fetcher, RDAP_URL + info.domain)
    expires = rdap_expiry(data) if data else None
    info.domain_expires = expires
    info.domain_lookup_failed = expires is None


def rdap_expiry(data: dict[str, Any]) -> datetime | None:
    """The "expiration" event of an RDAP answer."""
    for event in data.get("events", []):
        if event.get("eventAction") == "expiration":
            try:
                when = datetime.fromisoformat(str(event.get("eventDate", "")))
            except ValueError:
                return None
            return when if when.tzinfo else when.replace(tzinfo=UTC)
    return None


# --- Email: SPF and DMARC ---------------------------------------------------------


async def lookup_email_records(ctx: AuditContext, fetcher: Fetcher) -> None:
    info = ctx.security
    mx, txt, dmarc = await asyncio.gather(
        dns_records(fetcher, info.domain, "MX"),
        dns_records(fetcher, info.domain, "TXT"),
        dns_records(fetcher, f"_dmarc.{info.domain}", "TXT"),
    )
    if mx is None or txt is None or dmarc is None:
        return  # DNS couldn't be asked: dns_checked stays False
    info.dns_checked = True
    info.has_mx = bool(mx)
    info.spf = next((r for r in txt if r.lower().startswith("v=spf1")), "")
    info.dmarc = next((r for r in dmarc if r.lower().startswith("v=dmarc1")), "")


DNS_TYPES = {"MX": 15, "TXT": 16}
QUOTED = re.compile(r'"((?:[^"\\]|\\.)*)"')


async def dns_records(fetcher: Fetcher, name: str, kind: str) -> list[str] | None:
    """The records of one type for `name`, [] if there are none, None if DNS failed."""
    data = await get_json(fetcher, f"{DOH_URL}?name={name}&type={kind}", dns=True)
    if data is None:
        return None
    status = data.get("Status")
    if status == 3:  # NXDOMAIN: the name doesn't exist, so no records
        return []
    if status != 0:
        return None
    return [
        txt_value(str(answer.get("data", "")))
        for answer in data.get("Answer", [])
        if answer.get("type") == DNS_TYPES[kind]
    ]


def txt_value(data: str) -> str:
    """A TXT record arrives quoted, long ones in pieces: '"v=spf1 a" " -all"' -> 'v=spf1 a -all'."""
    pieces = QUOTED.findall(data)
    return "".join(pieces) if pieces else data


async def get_json(fetcher: Fetcher, url: str, *, dns: bool = False) -> dict[str, Any] | None:
    headers = {"Accept": "application/dns-json" if dns else "application/rdap+json"}
    try:
        page = await fetcher.get(url, headers=headers, timeout=LOOKUP_TIMEOUT, polite=False)
    except (FetchError, BlockedURLError):
        return None
    if not page.ok:
        return None
    try:
        data = json.loads(page.text)
    except ValueError:
        return None
    return data if isinstance(data, dict) else None


# --- Files that must never be public -----------------------------------------------

ENV_LINE = re.compile(r"^[A-Z][A-Z0-9_]{2,}=", re.MULTILINE)
GIT_HEAD = re.compile(r"^(ref: refs/|[0-9a-f]{40}\s*$)")


async def probe_exposed_files(ctx: AuditContext, fetcher: Fetcher) -> None:
    """Ask for /.git/HEAD, /.env and /.well-known/security.txt. Only yes/no is kept."""
    info = ctx.security
    parts = urlsplit(ctx.homepage.final_url)

    async def text_of(path: str) -> str | None:
        """The file's text if the server really sends that file (not an HTML page)."""
        url = urlunsplit((parts.scheme, parts.netloc, path, "", ""))
        try:
            page = await fetcher.get(url)
        except (FetchError, BlockedURLError):
            return None
        if not page.ok or page.is_html or page.text.lstrip().startswith("<"):
            return None
        return page.text

    git = await text_of("/.git/HEAD")
    env = await text_of("/.env")
    security_txt = await text_of("/.well-known/security.txt")
    info.files_checked = True
    info.git_exposed = bool(git and GIT_HEAD.match(git.strip()))
    info.env_exposed = bool(env and len(ENV_LINE.findall(env)) >= 2)
    info.security_txt = bool(security_txt and "contact:" in security_txt.lower())
