"""Shared test helpers for the engine: fake DNS and a fake internet (respx)."""

from collections.abc import AsyncIterator

import httpx
import pytest
import respx

from bizzcheckup.engine.config import EngineConfig
from bizzcheckup.engine.fetcher import Fetcher
from bizzcheckup.engine.netguard import BlockedURLError, NetGuard

PUBLIC_IP = "93.184.216.34"
FAKE_DNS = {
    "shop.test": [PUBLIC_IP],
    "www.shop.test": [PUBLIC_IP],
    "other.test": [PUBLIC_IP],
    "evil.test": ["10.0.0.1"],
}


async def fake_resolver(host: str) -> list[str]:
    if host not in FAKE_DNS:
        raise BlockedURLError(f"The website name {host!r} could not be found.")
    return FAKE_DNS[host]


@pytest.fixture
def config() -> EngineConfig:
    return EngineConfig(retries=1, max_page_bytes=1000)


@pytest.fixture
def router() -> respx.Router:
    """A fake internet. Any request without a matching route fails the test."""
    return respx.Router(assert_all_mocked=True, assert_all_called=False)


@pytest.fixture
async def fetcher(config: EngineConfig, router: respx.Router) -> AsyncIterator[Fetcher]:
    transport = httpx.MockTransport(router.async_handler)
    async with Fetcher(
        config,
        guard=NetGuard(resolver=fake_resolver),
        transport=transport,
        retry_backoff=0,
    ) as f:
        yield f
