import pytest
from pydantic import ValidationError

from bizzcheckup.engine.types import Band, Category, Finding, Level, Page, Severity


def make_finding(**overrides: object) -> Finding:
    data: dict[str, object] = {
        "check_id": "seo.title",
        "category": Category.SEO,
        "severity": Severity.FAIL,
        "message": "Your homepage has no title.",
        "why_it_matters": "Google shows the title in search results.",
        "how_to_fix": "Add a <title> tag.",
        "effort": Level.LOW,
        "impact": Level.HIGH,
    }
    data.update(overrides)
    return Finding.model_validate(data)


def test_finding_accepts_plain_strings_for_enums() -> None:
    finding = make_finding(severity="warn", category="seo")
    assert finding.severity is Severity.WARN
    assert finding.affected_urls == []


@pytest.mark.parametrize("field", ["message", "why_it_matters", "how_to_fix"])
def test_finding_requires_explanations(field: str) -> None:
    with pytest.raises(ValidationError):
        make_finding(**{field: ""})


def test_finding_rejects_unknown_severity() -> None:
    with pytest.raises(ValidationError):
        make_finding(severity="terrible")


def test_labels() -> None:
    assert Category.BEST_PRACTICES.label == "Best practices"
    assert Band.URGENT.label == "Needs urgent care"


def test_page_content_type_helpers() -> None:
    page = Page(
        url="https://a.com/",
        final_url="https://a.com/",
        status_code=200,
        headers={"content-type": "text/html; charset=utf-8"},
    )
    assert page.content_type == "text/html"
    assert page.is_html
    assert page.ok
