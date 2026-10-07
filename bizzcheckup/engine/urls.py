"""Small helpers for cleaning up and comparing URLs."""

from urllib.parse import urljoin, urlsplit, urlunsplit

DEFAULT_PORTS = {"http": 80, "https": 443}


class InvalidURLError(ValueError):
    """The text cannot be turned into a usable http(s) URL."""


def normalize_url(raw: str) -> str:
    """Turn what a visitor typed into one canonical URL.

    "Example.com/About#team" -> "https://example.com/About"

    - adds https:// when no scheme is given
    - lowercases scheme and host, converts international domains to punycode
    - removes default ports, fragments and user:password@ parts
    - uses "/" for an empty path
    """
    text = raw.strip()
    if not text:
        raise InvalidURLError("Please enter a website address.")
    if "://" not in text:
        text = f"https://{text}"

    parts = urlsplit(text)
    scheme = parts.scheme.lower()
    if scheme not in DEFAULT_PORTS:
        raise InvalidURLError("Only http:// and https:// addresses can be checked.")

    host = (parts.hostname or "").rstrip(".")
    if not host:
        raise InvalidURLError("That doesn't look like a website address.")
    try:
        host = host.encode("idna").decode("ascii")
    except UnicodeError as error:
        raise InvalidURLError("That website name contains invalid characters.") from error

    try:
        port = parts.port
    except ValueError as error:
        raise InvalidURLError("That address has an invalid port number.") from error

    netloc = f"[{host}]" if ":" in host else host  # IPv6 needs brackets
    if port is not None and port != DEFAULT_PORTS[scheme]:
        netloc = f"{netloc}:{port}"

    return urlunsplit((scheme, netloc, parts.path or "/", parts.query, ""))


def origin(url: str) -> str:
    """Scheme + host + port only: https://shop.com/a/b?x=1 -> https://shop.com"""
    parts = urlsplit(url)
    return urlunsplit((parts.scheme, parts.netloc, "", "", ""))


def domain(url: str) -> str:
    """Host name only: https://www.shop.com/a -> www.shop.com"""
    return (urlsplit(url).hostname or "").lower()


def same_origin(a: str, b: str) -> bool:
    return origin(a) == origin(b)


def absolute(base: str, href: str) -> str | None:
    """Resolve a link found on page `base`. Returns None for non-web links."""
    href = href.strip()
    if not href or href.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
        return None
    joined = urljoin(base, href)
    if urlsplit(joined).scheme not in DEFAULT_PORTS:
        return None
    try:
        return normalize_url(joined)
    except InvalidURLError:
        return None
