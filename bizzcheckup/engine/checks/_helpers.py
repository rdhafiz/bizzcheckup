"""Small helpers shared by many checks (no checks are defined here)."""

import re
from collections.abc import Iterable
from typing import TYPE_CHECKING

from selectolax.lexbor import LexborHTMLParser, LexborNode

from ..types import Shot
from ..urls import absolute

if TYPE_CHECKING:
    from ..context import AuditContext

# --- pointing at elements, for the pictures of where a problem is -------------------------

SAFE_ID = re.compile(r"[A-Za-z][\w-]*")  # an id usable as "#id" without escaping
# The attribute that identifies an element best, by tag (found by it before the CSS path).
MATCH_ATTRIBUTE = {
    "img": "src",
    "a": "href",
    "iframe": "src",
    "video": "src",
    "audio": "src",
    "input": "name",
    "select": "name",
    "textarea": "name",
}


def css_path(node: LexborNode) -> str:
    """A CSS selector for exactly this element: "main > div:nth-of-type(2) > img".

    Stops early at an ancestor with a usable id ("#gallery > img:nth-of-type(3)").
    """
    parts: list[str] = []
    current: LexborNode | None = node
    while current is not None and current.tag and not current.tag.startswith("-"):
        tag = current.tag
        if tag in ("html", "body"):
            parts.append(tag)
            break
        ident = (current.attributes.get("id") or "").strip()
        if SAFE_ID.fullmatch(ident):
            parts.append(f"#{ident}")
            break
        parent = current.parent
        siblings = [child for child in parent.iter() if child.tag == tag] if parent else []
        if len(siblings) > 1:
            position = next(
                i for i, child in enumerate(siblings, 1) if child.mem_id == current.mem_id
            )
            parts.append(f"{tag}:nth-of-type({position})")
        else:
            parts.append(tag)
        current = parent
    return " > ".join(reversed(parts))


def describe(node: LexborNode) -> str:
    """A short, readable name for an element: '<img src="banner.jpg">', '<a> "Old offer"'."""
    tag = node.tag or "element"
    attribute = MATCH_ATTRIBUTE.get(tag)
    value = (node.attributes.get(attribute) or "").strip() if attribute else ""
    if tag in ("img", "iframe", "video", "audio") and value:
        name = value.rsplit("/", 1)[-1][:50] or value[:50]
        return f'<{tag} src="{name}">'
    text = " ".join(node.text(strip=True).split())[:50]
    if text:
        return f'<{tag}> "{text}"'
    if value:
        return f'<{tag} {attribute}="{value[:50]}">'
    return f"<{tag}>"


def shot_of(node: LexborNode, page_url: str, *, label: str = "") -> Shot:
    """Where `node` is, so the shots step can photograph it later."""
    tag = node.tag or ""
    attribute = MATCH_ATTRIBUTE.get(tag, "")
    value = (node.attributes.get(attribute) or "") if attribute else ""
    return Shot(
        page=page_url,
        selector=css_path(node),
        match_tag=tag if value else "",
        match_attr=attribute if value else "",
        match_value=value,
        match_text=" ".join(node.text(strip=True).split())[:40],
        label=label or describe(node),
    )


def shots_of(nodes: Iterable[LexborNode], page_url: str, limit: int = 3) -> list[Shot]:
    """Shots for the first `limit` of these elements on one page."""
    return [shot_of(node, page_url) for node, _ in zip(nodes, range(limit), strict=False)]


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


def shots_for_urls(
    ctx: "AuditContext", urls: Iterable[str], sources: dict[str, list[str]], tag: str, attr: str
) -> list[Shot]:
    """Shots of the elements pointing at these addresses (broken links, broken images).

    `sources` maps each address to the pages it was found on; on each of those pages the
    first <tag> whose `attr` resolves to the address is used.
    """
    pages = {page.final_url: page for page in ctx.html_pages}
    shots: list[Shot] = []
    for url in urls:
        for page_url in sources.get(url, []):
            page = pages.get(page_url)
            if page is None:
                continue
            node = next(
                (
                    n
                    for n in ctx.dom(page).css(f"{tag}[{attr}]")
                    if (absolute(page_url, n.attributes.get(attr) or "") or "").split("#")[0] == url
                ),
                None,
            )
            if node is not None:
                shots.append(shot_of(node, page_url))
                break  # one picture per broken address is enough
        if len(shots) >= 3:
            break
    return shots
