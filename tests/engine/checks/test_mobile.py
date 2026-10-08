"""Phone and tablet checks, using made-up browser measurements (no browser needed)."""

import pytest

from bizzcheckup.engine.checks import mobile
from bizzcheckup.engine.checks.base import Check
from bizzcheckup.engine.context import RENDER, AuditContext
from bizzcheckup.engine.types import DeviceView, Finding, RenderResult, Severity

from ..factories import make_context

HOME = "https://shop.test/"


def view(name: str = "mobile", **values: object) -> DeviceView:
    width = 390 if name == "mobile" else 820
    defaults: dict[str, object] = {
        "name": name,
        "width": width,
        "height": 844,
        "layout_width": width,
        "scroll_width": width,
        "tap_targets": 20,
        "text_chars": 1000,
    }
    return DeviceView.model_validate(defaults | values)


def context(*views: DeviceView) -> AuditContext:
    ctx = make_context(capabilities={RENDER})
    ctx.render = RenderResult(url=HOME, html="", text_length=0, devices=list(views))
    return ctx


def run(check: type[Check], *views: DeviceView) -> list[Finding]:
    return check().run(context(*views))


CHECKS: list[type[Check]] = [mobile.MobileLayout, mobile.TapTargets, mobile.MobileTextSize]


@pytest.mark.parametrize("check", CHECKS, ids=lambda c: c.id)
def test_a_good_phone_layout_passes(check: type[Check]) -> None:
    assert [f.severity for f in run(check, view(), view("tablet"))] == [Severity.PASS]


@pytest.mark.parametrize("check", CHECKS, ids=lambda c: c.id)
def test_not_applicable_without_a_phone_view(check: type[Check]) -> None:
    assert run(check) == []


def test_shrunken_desktop_page_fails_on_phones() -> None:
    shrunk = view(layout_width=980, scroll_width=980)
    [layout] = run(mobile.MobileLayout, shrunk)
    assert layout.severity is Severity.FAIL
    assert "about 40% of its size" in layout.message
    # The other two point at the real cause instead of counting tiny things.
    for check in (mobile.TapTargets, mobile.MobileTextSize):
        [finding] = run(check, shrunk)
        assert finding.severity is Severity.WARN
        assert "isn't laid out for phones" in finding.message


def test_sideways_scrolling_lists_what_sticks_out() -> None:
    wide = view(scroll_width=600, overflowing=['div.banner "Big banner"'])
    [finding] = run(mobile.MobileLayout, wide, view("tablet"))
    assert finding.severity is Severity.FAIL
    assert "(600 px on a 390 px screen)" in finding.message
    assert finding.snippets[0].code == 'div.banner "Big banner"'


def test_tablet_problems_are_only_warnings() -> None:
    [finding] = run(mobile.MobileLayout, view(), view("tablet", scroll_width=900))
    assert finding.severity is Severity.WARN
    assert finding.message.startswith("On a tablet")


@pytest.mark.parametrize(
    ("small", "severity"),
    [(1, Severity.INFO), (3, Severity.WARN), (0, Severity.PASS)],
)
def test_tap_targets(small: int, severity: Severity) -> None:
    examples = ['button "Close"'] * small
    [finding] = run(mobile.TapTargets, view(small_tap_targets=small, small_tap_examples=examples))
    assert finding.severity is severity


@pytest.mark.parametrize(
    ("small_chars", "severity"),
    [(300, Severity.WARN), (100, Severity.INFO), (10, Severity.PASS)],
)
def test_text_size(small_chars: int, severity: Severity) -> None:
    [finding] = run(mobile.MobileTextSize, view(small_text_chars=small_chars))
    assert finding.severity is severity
