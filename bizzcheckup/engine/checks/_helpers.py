"""Small helpers shared by many checks (no checks are defined here)."""

from selectolax.lexbor import LexborHTMLParser, LexborNode


def meta_content(tree: LexborHTMLParser, name: str) -> str | None:
    """content of <meta name="..."> (name compared case-insensitively)."""
    return _meta(tree, "name", name)


def meta_property(tree: LexborHTMLParser, prop: str) -> str | None:
    """content of <meta property="..."> (used by Open Graph: og:title, ...)."""
    return _meta(tree, "property", prop)


def meta_http_equiv(tree: LexborHTMLParser, header: str) -> str | None:
    """content of <meta http-equiv="..."> (a header written inside the HTML)."""
    return _meta(tree, "http-equiv", header)


def _meta(tree: LexborHTMLParser, attribute: str, value: str) -> str | None:
    for node in tree.css("meta"):
        if (node.attributes.get(attribute) or "").strip().lower() == value.lower():
            return (node.attributes.get("content") or "").strip()
    return None


def title_text(tree: LexborHTMLParser) -> str:
    node = tree.css_first("title")
    return node.text(strip=True) if node else ""


def links_with_rel(tree: LexborHTMLParser, rel: str) -> list[LexborNode]:
    """<link> elements whose rel contains `rel` (rel can hold several words)."""
    return [
        node
        for node in tree.css("link[rel]")
        if rel in (node.attributes.get("rel") or "").lower().split()
    ]


def on_pages(count: int, total: int, has: str, have: str) -> str:
    """Start a sentence about how many pages are affected.

    on_pages(1, 1, "has no title.", "have no title.") -> "Your homepage has no title."
    on_pages(2, 5, ...) -> "2 of the 5 pages we checked have no title."
    """
    if total == 1:
        return f"Your homepage {has}"
    if count == total:
        return f"All {total} pages we checked {have}"
    return f"{count} of the {total} pages we checked {has if count == 1 else have}"


def share_score(total: int, fails: int, warns: int = 0) -> float:
    """Partial credit: 1.0 when no page has the problem, 0.0 when every page fails."""
    if total == 0:
        return 1.0
    return max(0.0, 1.0 - (fails + 0.5 * warns) / total)


def version_tuple(text: str) -> tuple[int, ...]:
    """Turn "3.5.1" into (3, 5, 1) so versions compare correctly: 3.10 is newer than 3.9."""
    return tuple(int(part) for part in text.split(".") if part.isdigit())
