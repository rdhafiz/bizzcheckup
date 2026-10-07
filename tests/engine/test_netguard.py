import pytest

from bizzcheckup.engine.netguard import BlockedURLError, NetGuard

# Fake DNS: no test ever uses the real internet.
FAKE_DNS = {
    "public.test": ["93.184.216.34"],
    "public6.test": ["2606:2800:220:1:248:1893:25c8:1946"],
    "sneaky.test": ["93.184.216.34", "10.0.0.5"],  # one public + one private address
    "loopback.test": ["127.0.0.1"],
    "metadata.test": ["169.254.169.254"],
}


async def fake_resolver(host: str) -> list[str]:
    if host not in FAKE_DNS:
        raise BlockedURLError(f"The website name {host!r} could not be found.")
    return FAKE_DNS[host]


@pytest.fixture
def guard() -> NetGuard:
    return NetGuard(resolver=fake_resolver)


@pytest.mark.parametrize(
    "url",
    [
        "https://public.test/",
        "http://public.test/page",
        "https://public.test:443/",
        "http://public.test:80/",
        "https://public6.test/",
        "https://93.184.216.34/",
    ],
)
async def test_public_urls_are_allowed(guard: NetGuard, url: str) -> None:
    await guard.check_url(url)  # no exception = allowed


@pytest.mark.parametrize(
    "url",
    [
        # loopback
        "http://127.0.0.1/",
        "http://127.1.2.3/",
        "http://[::1]/",
        "http://localhost/",
        "http://app.localhost/",
        "http://loopback.test/",
        # private networks
        "http://10.0.0.1/",
        "http://172.16.5.4/",
        "http://192.168.1.1/",
        "http://[fd00::1]/",
        # link-local and cloud metadata
        "http://169.254.169.254/latest/meta-data/",
        "http://metadata.test/",
        "http://[fe80::1]/",
        # IPv4 hidden inside IPv6
        "http://[::ffff:127.0.0.1]/",
        "http://[::ffff:10.0.0.1]/",
        # carrier-grade NAT, "this network", broadcast, multicast
        "http://100.64.0.1/",
        "http://0.0.0.0/",
        "http://255.255.255.255/",
        "http://224.0.0.1/",
        # any resolved address private -> blocked
        "http://sneaky.test/",
        # mDNS / internal names
        "http://printer.local/",
        "http://db.internal/",
    ],
)
async def test_internal_addresses_are_blocked(guard: NetGuard, url: str) -> None:
    with pytest.raises(BlockedURLError):
        await guard.check_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "ftp://public.test/",
        "file:///etc/passwd",
        "gopher://public.test/",
        "https://public.test:8443/",
        "http://public.test:6379/",
        "http://public.test:22/",
    ],
)
async def test_other_schemes_and_ports_are_blocked(guard: NetGuard, url: str) -> None:
    with pytest.raises(BlockedURLError):
        await guard.check_url(url)


async def test_unknown_host_is_blocked(guard: NetGuard) -> None:
    with pytest.raises(BlockedURLError, match="could not be found"):
        await guard.check_url("https://does-not-exist.test/")
