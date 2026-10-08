"""Accessibility checks, tested against local HTML and fake browser results (no network)."""

import pytest

from bizzcheckup.engine.checks import accessibility as a11y
from bizzcheckup.engine.checks.base import Check
from bizzcheckup.engine.context import RENDER, AuditContext
from bizzcheckup.engine.types import AxeNode, AxeRule, Level, RenderResult, Severity

from ..factories import fixture_html, make_context, make_page

HOME = "https://shop.test/"

STATIC_CHECKS: list[type[Check]] = [
    a11y.ImageAlt,
    a11y.HtmlLang,
    a11y.HeadingOrder,
    a11y.FormLabels,
    a11y.AccessibleNames,
]


def severities(check: type[Check], ctx: AuditContext) -> list[Severity]:
    return [finding.severity for finding in check().run(ctx)]


def body(html: str, lang: str = "en") -> str:
    head = "<head><title>x</title></head>"
    return f'<!doctype html><html lang="{lang}">{head}<body>{html}</body></html>'


def rendered(**fields: object) -> RenderResult:
    data: dict[str, object] = {"url": HOME, "html": "<html></html>", "text_length": 100}
    data.update(fields)
    return RenderResult.model_validate(data)


@pytest.mark.parametrize("check", STATIC_CHECKS, ids=lambda c: c.id)
def test_healthy_page_passes(check: type[Check]) -> None:
    ctx = make_context(make_page(fixture_html("healthy")))
    assert severities(check, ctx) == [Severity.PASS]


@pytest.mark.parametrize(
    ("check", "expected"),
    [
        (a11y.ImageAlt, [Severity.FAIL]),
        (a11y.HtmlLang, [Severity.FAIL]),
        (a11y.HeadingOrder, [Severity.WARN]),  # h1 -> h4
        (a11y.FormLabels, [Severity.FAIL]),  # placeholder only
        (a11y.AccessibleNames, [Severity.WARN]),  # icon link + empty button
    ],
    ids=lambda value: getattr(value, "id", ""),
)
def test_neglected_page_has_problems(check: type[Check], expected: list[Severity]) -> None:
    ctx = make_context(make_page(fixture_html("neglected")))
    assert severities(check, ctx) == expected


# --- alt text ----------------------------------------------------------------


def test_decorative_empty_alt_is_fine_and_partial_score() -> None:
    html = body('<img src="a.jpg" alt=""> <img src="b.jpg" alt="Cake"> <img src="c.jpg">')
    check = a11y.ImageAlt()
    findings = check.run(make_context(make_page(html)))

    assert findings[0].message == "1 of your 3 images have no description for blind visitors."
    assert check.score(findings) == pytest.approx(2 / 3)


def test_no_images_is_not_applicable() -> None:
    assert a11y.ImageAlt().run(make_context(make_page(body("<p>Text only</p>")))) == []


# --- language ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("lang", "expected"),
    [
        ("en", Severity.PASS),
        ("en-GB", Severity.PASS),
        ("bn", Severity.PASS),
        ("english", Severity.WARN),
    ],
)
def test_lang_values(lang: str, expected: Severity) -> None:
    assert severities(a11y.HtmlLang, make_context(make_page(body("", lang=lang)))) == [expected]


def test_rendered_html_is_used_for_the_homepage() -> None:
    """A JavaScript site may only add lang (and content) after it runs in the browser."""
    raw = make_page("<html><body><div id='app'></div></body></html>")
    ctx = make_context(raw, capabilities={RENDER})
    ctx.render = rendered(html=body("<h1>Built by JavaScript</h1>"))
    assert severities(a11y.HtmlLang, ctx) == [Severity.PASS]


# --- headings ----------------------------------------------------------------


@pytest.mark.parametrize(
    ("headings", "expected"),
    [
        ("<h1>a</h1><h2>b</h2><h3>c</h3><h2>d</h2>", Severity.PASS),
        ("<h2>starts at h2</h2><h3>b</h3>", Severity.PASS),  # starting lower is fine
        ("<h1>a</h1><h3>skips h2</h3>", Severity.WARN),
    ],
)
def test_heading_order(headings: str, expected: Severity) -> None:
    assert severities(a11y.HeadingOrder, make_context(make_page(body(headings)))) == [expected]


# --- form labels -------------------------------------------------------------


@pytest.mark.parametrize(
    "field",
    [
        '<label for="e">Email</label><input id="e">',
        "<label>Email <input></label>",
        '<input aria-label="Email">',
        '<span id="lbl">Email</span><input aria-labelledby="lbl">',
        '<select title="Size"><option>S</option></select>',
    ],
)
def test_labelled_fields(field: str) -> None:
    assert severities(a11y.FormLabels, make_context(make_page(body(field)))) == [Severity.PASS]


@pytest.mark.parametrize(
    "field",
    [
        '<input placeholder="Email">',
        '<label for="other">Email</label><input id="e">',
        "<textarea></textarea>",
    ],
)
def test_unlabelled_fields(field: str) -> None:
    assert severities(a11y.FormLabels, make_context(make_page(body(field)))) == [Severity.FAIL]


def test_page_without_forms_is_not_applicable() -> None:
    html = body('<input type="hidden" name="x"><input type="submit" value="Go">')
    assert a11y.FormLabels().run(make_context(make_page(html))) == []


# --- link and button names ---------------------------------------------------


@pytest.mark.parametrize(
    ("element", "expected"),
    [
        ('<a href="/">Home</a>', Severity.PASS),
        ('<a href="/cart" aria-label="Cart"><i></i></a>', Severity.PASS),
        ('<a href="/"><img src="logo.png" alt="Sweet Moments home"></a>', Severity.PASS),
        ('<button title="Search"><i></i></button>', Severity.PASS),
        ('<input type="submit" value="Send">', Severity.PASS),
        ('<a href="/cart"><i class="icon"></i></a>', Severity.WARN),
        ('<a href="/"><img src="logo.png"></a>', Severity.WARN),
        ("<button></button>", Severity.WARN),
        ('<input type="submit">', Severity.WARN),
    ],
)
def test_accessible_names(element: str, expected: Severity) -> None:
    assert severities(a11y.AccessibleNames, make_context(make_page(body(element)))) == [expected]


# --- axe scan ----------------------------------------------------------------


def axe_rule(rule_id: str, impact: str, nodes: int = 2) -> AxeRule:
    return AxeRule(
        id=rule_id,
        impact=impact,
        help=f"Rule {rule_id}",
        help_url=f"https://dequeuniversity.com/rules/axe/4.14/{rule_id}",
        nodes=nodes,
        targets=[".a", ".b"],
    )


def axe_context(violations: list[AxeRule], passes: list[str]) -> AuditContext:
    ctx = make_context(capabilities={RENDER})
    ctx.render = rendered(axe_violations=violations, axe_passes=passes)
    return ctx


def test_axe_scan_reports_each_rule_by_impact_and_skips_covered_rules() -> None:
    ctx = axe_context(
        [
            axe_rule("region", "moderate"),
            axe_rule("color-contrast", "serious"),
            axe_rule("image-alt", "critical"),  # covered by ImageAlt: not repeated
            axe_rule("aria-hidden-focus", "critical"),
            axe_rule("some-minor-thing", "minor"),
        ],
        passes=["document-title", "bypass", "link-name"],
    )
    check = a11y.AxeScan()
    findings = check.run(ctx)

    assert [(f.message.split(" (")[0], f.severity, f.impact) for f in findings] == [
        ("Rule aria-hidden-focus", Severity.FAIL, Level.HIGH),
        ("Rule color-contrast", Severity.FAIL, Level.HIGH),
        ("Rule region", Severity.WARN, Level.LOW),
        ("Rule some-minor-thing", Severity.INFO, Level.LOW),
    ]
    assert "sunlight" in findings[1].why_it_matters  # plain-language impact for contrast
    assert "dequeuniversity.com" in findings[0].how_to_fix
    # passes: document-title, bypass (link-name is covered) = 2; violations = 4
    # penalty = 1.0 + 0.7 + 0.3 + 0.1 = 2.1 -> (6 - 2.1) / 6
    assert check.score(findings) == pytest.approx(3.9 / 6)


def test_axe_scan_all_clear() -> None:
    findings = a11y.AxeScan().run(axe_context([], passes=["document-title", "bypass"]))
    assert [f.severity for f in findings] == [Severity.PASS]


CONTRAST_SUMMARY = (
    "Fix any of the following:\n  Element has insufficient color contrast of 2.81 "
    "(foreground color: #9ca3af, background color: #ffffff, font size: 9.0pt (12px), "
    "font weight: normal). Expected contrast ratio of 4.5:1"
)


def test_axe_finding_shows_each_element_with_its_picture_and_problem() -> None:
    rule = axe_rule("color-contrast", "serious", nodes=1)
    rule.details = [
        AxeNode(
            target="#audience-panel-0 > .relative > .bottom-4",
            html='<span class="bottom-4">Our audience</span>',
            summary=CONTRAST_SUMMARY,
            text="Our audience",
            image="element-1",
        )
    ]
    [finding] = a11y.AxeScan().run(axe_context([rule], passes=["bypass"]))
    assert finding.how_to_fix.startswith("Below you can see the element: where it is on the page")
    assert "webaim.org/resources/contrastchecker" in finding.how_to_fix
    assert "#audience-panel-0" not in finding.how_to_fix  # the selector moved to the details
    [snippet] = finding.snippets
    assert snippet.title == '"Our audience" — Element has insufficient color contrast of 2.81'
    assert snippet.language == "element"
    assert snippet.image == "element-1"
    assert snippet.note == (
        "Element has insufficient color contrast of 2.81 (foreground color: "
        "#9ca3af, background color: #ffffff, font size: 9.0pt (12px), font weight: normal). "
        "Expected contrast ratio of 4.5:1"
    )
    assert snippet.code == (
        'HTML: <span class="bottom-4">Our audience</span>\n\n'
        "CSS selector: #audience-panel-0 > .relative > .bottom-4"
    )


def test_older_reports_without_element_details_still_name_examples() -> None:
    [finding] = a11y.AxeScan().run(axe_context([axe_rule("region", "moderate")], ["bypass"]))
    assert finding.how_to_fix.startswith("Fix the affected elements, for example `.a`, `.b`.")
    assert finding.snippets == []


def test_element_names_are_one_short_line() -> None:
    node = AxeNode(
        target=".x",
        text="Bizzacquire helped\n  HustleBlaze book 18 qualified appointments with UK firms",
    )
    assert a11y.element_snippet(1, node).title.startswith(
        '"Bizzacquire helped HustleBlaze book 18 qualified appointm..."'
    )
    assert a11y.element_snippet(2, AxeNode(target=".y")).title.startswith("Element 2")
