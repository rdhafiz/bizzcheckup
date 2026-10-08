"""engine/preview.py: reading link preview tags and suggesting complete ones."""

from selectolax.lexbor import LexborHTMLParser

from bizzcheckup.engine import preview

HOME = "https://shop.test/"


def tags(head: str) -> preview.PreviewTags:
    return preview.read_tags(LexborHTMLParser(f"<html><head>{head}</head></html>"))


def test_missing_and_relative_image() -> None:
    found = tags(
        '<meta property="og:title" content="Cakes"><meta property="og:image" content="/a.jpg">'
    )
    assert found.missing() == ["og:description", "twitter:card"]
    assert found.image_is_relative
    assert preview.image_url(HOME + "x", found) == HOME + "a.jpg"


def test_summary_uses_the_same_fallbacks_as_the_platforms() -> None:
    html = '<title>Cakes | Sweet</title><meta name="description" content="Fresh cakes.">'
    card = preview.summary("https://www.shop.test/", LexborHTMLParser(f"<head>{html}</head>"))
    assert (card.domain, card.title, card.description, card.image_url) == (
        "shop.test",
        "Cakes | Sweet",
        "Fresh cakes.",
        "",
    )


def test_suggestion_keeps_existing_values_and_fills_the_rest() -> None:
    found = tags('<title>Cake care</title><meta property="og:image" content="/a.jpg">')
    code = preview.suggestion(HOME + "blog/care", found, site_name="Sweet", is_article=True)
    assert code.splitlines() == [
        '<meta property="og:type" content="article">',
        '<meta property="og:url" content="https://shop.test/blog/care">',
        '<meta property="og:title" content="Cake care">',
        '<meta property="og:description" content="REPLACE: one or two sentences that make'
        ' people want to click">',
        '<meta property="og:image" content="https://shop.test/a.jpg">',  # made a full address
        '<meta property="og:site_name" content="Sweet">',
        '<meta name="twitter:card" content="summary_large_image">',
    ]
