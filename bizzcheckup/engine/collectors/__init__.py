"""Collectors gather extra data after the crawl and before the checks run.

Each collector is `async def collect(ctx, fetcher, config) -> None`: it stores
its results on the AuditContext and adds its capability name (e.g. PROBES), so
checks that need that data know it is available.
"""

from collections.abc import Awaitable, Callable

from ..config import EngineConfig
from ..context import AuditContext
from ..fetcher import Fetcher

Collector = Callable[[AuditContext, Fetcher, EngineConfig], Awaitable[None]]

from .probes import collect_probes  # noqa: E402 (needs Collector defined first)
from .render import collect_render  # noqa: E402

DEFAULT_COLLECTORS: list[Collector] = [collect_probes, collect_render]
