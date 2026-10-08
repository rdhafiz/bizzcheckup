"""Link previews: what Facebook, WhatsApp, LinkedIn and X show when a page is shared.

They read Open Graph tags (og:title, og:description, og:image) and X's twitter:card,
and fall back to the page's <title> and description when those are missing.
"""

from dataclasses import dataclass
from html import escape

from selectolax.lexbor import LexborHTMLParser

from .checks._helpers import meta_content, meta_property, title_text
from .types import LinkPreview
from .urls import absolute, domain

REQUIRED = ("og:title", "og:description", "og:image", "twitter:card")
IMAGE_SIZE_HINT = "1200 x 630 pixels"


@dataclass
class PreviewTags:
    """The preview tags as written on one page ("" = missing)."""

    title: str
    description: str
    image: str  # as written, may be relative
    url: str
    type: str
    site_name: str
    twitter_card: str
    page_title: str  # <title>: the fallback most platforms use
    page_description: str  # <meta name="description">

    def missing(self) -> list[str]:
        values = {
            "og:title": self.title,
            "og:description": self.description,
            "og:image": self.image,
            "twitter:card": self.twitter_card,
        }
        return [name for name in REQUIRED if not values[name]]

    @property
    def image_is_relative(self) -> bool:
        return bool(self.image) and not self.image.startswith(("http://", "https://"))


def read_tags(tree: LexborHTMLParser) -> PreviewTags:
    return PreviewTags(
        title=meta_property(tree, "og:title") or "",
        description=meta_property(tree, "og:description") or "",
        image=meta_property(tree, "og:image") or meta_content(tree, "twitter:image") or "",
        url=meta_property(tree, "og:url") or "",
        type=meta_property(tree, "og:type") or "",
        site_name=meta_property(tree, "og:site_name") or "",
        twitter_card=meta_content(tree, "twitter:card") or "",
        page_title=title_text(tree),
        page_description=meta_content(tree, "description") or "",
    )


def image_url(page_url: str, tags: PreviewTags) -> str:
    """The picture's full address (platforms need a full one, but we resolve it to check)."""
    return absolute(page_url, tags.image) or "" if tags.image else ""


def summary(page_url: str, tree: LexborHTMLParser) -> LinkPreview:
    """What a platform would show, using the same fallbacks they use."""
    tags = read_tags(tree)
    return LinkPreview(
        url=page_url,
        domain=domain(page_url).removeprefix("www."),
        title=tags.title or tags.page_title,
        description=tags.description or tags.page_description,
        image_url=image_url(page_url, tags),
    )


def suggestion(page_url: str, tags: PreviewTags, *, site_name: str, is_article: bool) -> str:
    """The complete set of preview tags for a page, keeping what it already has."""

    def tag(kind: str, name: str, value: str) -> str:
        return f'<meta {kind}="{name}" content="{escape(value, quote=True)}">'

    image = tags.image if tags.image and not tags.image_is_relative else ""
    if not image and tags.image:
        image = image_url(page_url, tags)
    lines = [
        tag("property", "og:type", tags.type or ("article" if is_article else "website")),
        tag("property", "og:url", tags.url or page_url),
        tag("property", "og:title", tags.title or tags.page_title or "REPLACE: page headline"),
        tag(
            "property",
            "og:description",
            tags.description
            or tags.page_description
            or "REPLACE: one or two sentences that make people want to click",
        ),
        tag(
            "property",
            "og:image",
            image or f"REPLACE: full address of a {IMAGE_SIZE_HINT} picture (JPG or PNG)",
        ),
        tag("property", "og:site_name", tags.site_name or site_name or "REPLACE: business name"),
        tag("name", "twitter:card", tags.twitter_card or "summary_large_image"),
    ]
    return "\n".join(lines)
