"""The only place the engine makes HTTP requests.

Every request goes through `Fetcher.get`, which enforces:
- SSRF protection on the first URL AND on every redirect hop
- at most `max_concurrency` requests at the same time
- a timeout per request, with retries for temporary failures
- a maximum body size (bigger pages are cut off and marked `truncated`)
- our User-Agent, so site owners can see who is visiting
"""

import asyncio
import time
from types import TracebackType
from typing import Self
from urllib.parse import urljoin

import httpx

from .config import EngineConfig
from .netguard import BlockedURLError, NetGuard
from .types import Page

REDIRECT_CODES = {301, 302, 303, 307, 308}
RETRY_CODES = {429, 502, 503, 504}  # "try again later" answers


class FetchError(Exception):
    """The page could not be fetched (network error, timeout, too many redirects)."""


class Fetcher:
    """Use as `async with Fetcher(config) as fetcher: page = await fetcher.get(url)`."""

    def __init__(
        self,
        config: EngineConfig,
        guard: NetGuard | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
        retry_backoff: float = 0.5,
    ) -> None:
        self.config = config
        self.guard = guard or NetGuard()
        self._transport = transport  # tests pass a fake transport (respx)
        self._retry_backoff = retry_backoff
        self._semaphore = asyncio.Semaphore(config.max_concurrency)
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> Self:
        self._client = httpx.AsyncClient(
            headers={"User-Agent": self.config.user_agent},
            timeout=httpx.Timeout(self.config.request_timeout),
            follow_redirects=False,  # we follow them ourselves to check every hop
            transport=self._transport,
        )
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: TracebackType | None,
    ) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def get(
        self,
        url: str,
        *,
        user_agent: str | None = None,
        method: str = "GET",
        headers: dict[str, str] | None = None,
        timeout: float | None = None,
        polite: bool = True,
    ) -> Page:
        """Fetch `url`, following redirects safely. Raises BlockedURLError or FetchError.

        method="HEAD" asks only for the status and headers (no page body).
        timeout overrides the per-request timeout (e.g. for slow APIs).
        polite=False skips the "max 2 requests at once" limit; only for requests that
        don't go to the audited site (e.g. Google's PageSpeed API).
        """
        if self._client is None:
            raise RuntimeError("Use Fetcher inside 'async with'.")

        headers = dict(headers or {})
        if user_agent:
            headers["User-Agent"] = user_agent
        chain: list[str] = []
        current = url
        started = time.perf_counter()

        for _ in range(self.config.max_redirects + 1):
            await self.guard.check_url(current)  # every hop, not just the first
            response = await self._send_with_retries(method, current, headers, timeout, polite)
            try:
                location = response.headers.get("location")
                if response.status_code in REDIRECT_CODES and location:
                    chain.append(current)
                    current = urljoin(current, location)
                    continue
                body, truncated = await self._read_limited(response)
            finally:
                await response.aclose()

            text = body.decode(response.charset_encoding or "utf-8", errors="replace")
            return Page(
                url=url,
                final_url=current,
                status_code=response.status_code,
                headers={
                    k.lower(): ", ".join(response.headers.get_list(k)) for k in response.headers
                },
                text=text,
                size_bytes=len(body),
                truncated=truncated,
                elapsed_ms=round((time.perf_counter() - started) * 1000),
                redirect_chain=chain,
            )

        raise FetchError(f"Too many redirects (more than {self.config.max_redirects}).")

    async def status(self, url: str) -> int:
        """HTTP status of `url` after redirects, or 0 if it can't be reached.

        Tries a cheap HEAD request first; some servers refuse HEAD, so it falls
        back to GET for those.
        """
        try:
            page = await self.get(url, method="HEAD")
            if page.status_code in (403, 405, 501):
                page = await self.get(url)
        except (FetchError, BlockedURLError):
            return 0
        return page.status_code

    async def _send_with_retries(
        self,
        method: str,
        url: str,
        headers: dict[str, str],
        timeout: float | None = None,
        polite: bool = True,
    ) -> httpx.Response:
        assert self._client is not None  # noqa: S101 (checked in get())
        attempts = self.config.retries + 1
        for attempt in range(attempts):
            last_try = attempt == attempts - 1
            try:
                request = self._client.build_request(
                    method, url, headers=headers, timeout=timeout or self.config.request_timeout
                )
                if polite:
                    async with self._semaphore:
                        response = await self._client.send(request, stream=True)
                else:
                    response = await self._client.send(request, stream=True)
            except httpx.TransportError as error:  # timeouts, refused connections, DNS
                if last_try:
                    raise FetchError(f"Could not connect to {url}: {error!r}") from error
            else:
                if response.status_code not in RETRY_CODES or last_try:
                    return response
                await response.aclose()
            await asyncio.sleep(self._retry_backoff * 2**attempt)
        raise FetchError(f"Could not fetch {url}.")  # pragma: no cover (loop always returns)

    async def _read_limited(self, response: httpx.Response) -> tuple[bytes, bool]:
        """Read the body, stopping at max_page_bytes. Returns (body, truncated)."""
        limit = self.config.max_page_bytes
        chunks: list[bytes] = []
        size = 0
        async for chunk in response.aiter_bytes():
            chunks.append(chunk)
            size += len(chunk)
            if size > limit:
                return b"".join(chunks)[:limit], True
        return b"".join(chunks), False


__all__ = ["BlockedURLError", "FetchError", "Fetcher"]
