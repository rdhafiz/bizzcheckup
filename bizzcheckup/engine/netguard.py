"""SSRF protection: only ever connect to public web servers.

SSRF (Server-Side Request Forgery) is when an attacker makes OUR server fetch a
URL they choose, e.g. http://127.0.0.1:6379 (our Redis) or
http://169.254.169.254 (cloud metadata with secret keys). Because strangers
submit URLs to BizzCheckup, every outgoing request is checked here, including
each hop of a redirect (the fetcher calls `check_url` for every request).

Rules:
- only http and https
- only the standard ports 80 and 443
- the host name must resolve, and EVERY address it resolves to must be a
  public ("global") internet address
"""

import asyncio
import ipaddress
import socket
from collections.abc import Awaitable, Callable
from urllib.parse import urlsplit

ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_PORTS = {80, 443}

IPAddress = ipaddress.IPv4Address | ipaddress.IPv6Address
# A resolver turns a host name into a list of IP address strings.
Resolver = Callable[[str], Awaitable[list[str]]]


class BlockedURLError(Exception):
    """The URL points somewhere BizzCheckup must not connect to."""


async def system_resolver(host: str) -> list[str]:
    """Look up a host name with the operating system's DNS."""
    loop = asyncio.get_running_loop()
    try:
        infos = await loop.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as error:
        raise BlockedURLError(f"The website name {host!r} could not be found.") from error
    return sorted({str(info[4][0]) for info in infos})


def is_public_ip(ip: IPAddress) -> bool:
    """True only for normal internet addresses.

    `is_global` is False for loopback (127.x), private (10.x, 192.168.x,
    172.16-31.x), link-local (169.254.x, includes cloud metadata), carrier NAT
    (100.64.x), reserved and documentation ranges.
    """
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        # "::ffff:127.0.0.1" is really 127.0.0.1 written in IPv6 form.
        return is_public_ip(ip.ipv4_mapped)
    return ip.is_global and not ip.is_multicast


class NetGuard:
    """Decides whether a URL is safe to fetch."""

    def __init__(self, resolver: Resolver = system_resolver) -> None:
        # The resolver can be swapped in tests so they never use real DNS.
        self._resolve = resolver

    async def check_url(self, url: str) -> None:
        """Raise BlockedURLError unless `url` is safe. Returns None when it is."""
        parts = urlsplit(url)

        if parts.scheme not in ALLOWED_SCHEMES:
            raise BlockedURLError("Only http:// and https:// addresses can be checked.")

        try:
            port = parts.port or (443 if parts.scheme == "https" else 80)
        except ValueError as error:
            raise BlockedURLError("That address has an invalid port number.") from error
        if port not in ALLOWED_PORTS:
            raise BlockedURLError(
                "Only websites on the standard ports (80 and 443) can be checked."
            )

        host = parts.hostname
        if not host:
            raise BlockedURLError("That address has no website name.")

        addresses = await self._addresses_for(host)
        if not addresses:
            raise BlockedURLError(f"The website name {host!r} could not be found.")
        for ip in addresses:
            if not is_public_ip(ip):
                raise BlockedURLError(
                    "That address points to a private or internal network, "
                    "which BizzCheckup is not allowed to visit."
                )

    async def _addresses_for(self, host: str) -> list[IPAddress]:
        try:
            # The host is already an IP address, e.g. http://10.0.0.1/
            return [ipaddress.ip_address(host)]
        except ValueError:
            pass
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")):
            raise BlockedURLError("Local network addresses cannot be checked.")
        results: list[IPAddress] = []
        for text in await self._resolve(host):
            try:
                results.append(ipaddress.ip_address(text.split("%")[0]))  # drop IPv6 zone id
            except ValueError:
                continue
        return results
