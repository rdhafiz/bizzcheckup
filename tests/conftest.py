"""Fixtures shared by every test."""

import pytest

from bizzcheckup.checkups import services
from bizzcheckup.engine.netguard import NetGuard

# Fake DNS for the web app: example sites under .test look public, except internal.test.
PUBLIC_TEST_IP = "93.184.216.34"


async def test_dns(host: str) -> list[str]:
    if host == "internal.test":
        return ["10.0.0.7"]
    if host.endswith(".test"):
        return [PUBLIC_TEST_IP]
    return ["93.184.216.35"]  # tests never reach real hosts anyway


@pytest.fixture(autouse=True)
def offline_ssrf_guard(monkeypatch: pytest.MonkeyPatch) -> None:
    """The form's SSRF check uses the real rules, with fake DNS instead of the internet."""
    monkeypatch.setattr(services, "make_guard", lambda: NetGuard(resolver=test_dns))
