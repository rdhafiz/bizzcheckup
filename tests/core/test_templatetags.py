"""Template filters in core/templatetags/bizz.py."""

from bizzcheckup.core.templatetags.bizz import contrast, url_path

AXE_CONTRAST = (
    "Element has insufficient color contrast of 4.11 (foreground color: #e3b24b, background "
    "color: #52504b, font size: 9.0pt (12px), font weight: bold). Expected contrast ratio "
    "of 4.5:1"
)


def test_contrast_reads_the_colours_and_ratios() -> None:
    assert contrast(AXE_CONTRAST) == {
        "ratio": "4.11",
        "fg": "#e3b24b",
        "bg": "#52504b",
        "expected": "4.5:1",
    }


def test_contrast_ignores_other_explanations_and_odd_colours() -> None:
    assert contrast("ARIA role group is not allowed for given element") is None
    assert contrast(AXE_CONTRAST.replace("#e3b24b", 'red" onload="x')) is None
    assert contrast("") is None


def test_url_path() -> None:
    assert url_path("https://shop.test/about?x=1") == "/about?x=1"
    assert url_path("https://shop.test") == "/"
