import pytest

from bizzcheckup.engine.urls import (
    InvalidURLError,
    absolute,
    domain,
    normalize_url,
    origin,
    same_origin,
)


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("example.com", "https://example.com/"),
        ("  Example.COM/About#team ", "https://example.com/About"),
        ("http://example.com:80/", "http://example.com/"),
        ("https://example.com:443/a?x=1", "https://example.com/a?x=1"),
        ("https://example.com:8443/", "https://example.com:8443/"),
        ("https://user:secret@example.com/", "https://example.com/"),
        ("https://example.com./", "https://example.com/"),
        ("https://bücher.de/", "https://xn--bcher-kva.de/"),
        ("https://[2001:db8::1]/", "https://[2001:db8::1]/"),
    ],
)
def test_normalize_url(raw: str, expected: str) -> None:
    assert normalize_url(raw) == expected


@pytest.mark.parametrize(
    "raw",
    ["", "   ", "ftp://example.com", "file:///etc/passwd", "https://", "https://a.com:99999/"],
)
def test_normalize_url_rejects_bad_input(raw: str) -> None:
    with pytest.raises(InvalidURLError):
        normalize_url(raw)


def test_origin_domain_and_same_origin() -> None:
    assert origin("https://shop.com/a/b?x=1") == "https://shop.com"
    assert domain("https://WWW.Shop.com/a") == "www.shop.com"
    assert same_origin("https://shop.com/a", "https://shop.com/b")
    assert not same_origin("https://shop.com/", "http://shop.com/")
    assert not same_origin("https://shop.com/", "https://blog.shop.com/")


@pytest.mark.parametrize(
    ("href", "expected"),
    [
        ("/about", "https://shop.com/about"),
        ("contact#form", "https://shop.com/products/contact"),
        ("https://other.com/x", "https://other.com/x"),
        ("#top", None),
        ("mailto:hi@shop.com", None),
        ("tel:+123", None),
        ("javascript:void(0)", None),
        ("", None),
    ],
)
def test_absolute(href: str, expected: str | None) -> None:
    assert absolute("https://shop.com/products/item", href) == expected


@pytest.mark.parametrize(
    ("host", "site"),
    [
        ("www.shop.com", "shop.com"),
        ("shop.com", "shop.com"),
        ("a.b.shop.com", "shop.com"),
        ("www.shop.co.uk", "shop.co.uk"),
        ("shop.com.bd", "shop.com.bd"),
        (".facebook.com", "facebook.com"),
    ],
)
def test_site_domain(host: str, site: str) -> None:
    from bizzcheckup.engine.urls import site_domain

    assert site_domain(host) == site
