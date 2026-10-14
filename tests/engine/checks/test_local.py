"""Local business checks: contact details, tap-to-call, WhatsApp and directions."""

import pytest

from bizzcheckup.engine.checks.local import (
    ClickToCall,
    ContactDetails,
    Directions,
    WhatsAppChat,
    phones_in,
)
from bizzcheckup.engine.types import Severity

from ..factories import make_context, make_page


@pytest.mark.parametrize(
    ("text", "found"),
    [
        ("Call us: +880 1717-863320 today", ["+880 1717-863320"]),
        ("Phone (555) 123-4567", ["(555) 123-4567"]),
        ("01717863320", ["01717863320"]),
        ("Copyright 2026. Price 1200000 taka. Order 20261014", []),
        ("+880 1717-863320 or 01717-863320", ["+880 1717-863320"]),  # the same number twice
    ],
)
def test_phone_numbers_are_found_but_not_dates_or_prices(text: str, found: list[str]) -> None:
    assert phones_in(text) == found


def test_contact_details_on_the_homepage_pass() -> None:
    ctx = make_context(make_page('<footer><a href="mailto:hi@shop.test">Email us</a></footer>'))
    assert ContactDetails().run(ctx)[0].severity is Severity.PASS


def test_contact_details_only_elsewhere_is_a_note() -> None:
    contact = make_page('<a href="tel:+8801717863320">Call</a>', url="https://shop.test/contact")
    ctx = make_context(make_page("<p>Welcome</p>"), contact)
    (finding,) = ContactDetails().run(ctx)
    assert finding.severity is Severity.INFO
    assert finding.affected_urls == ["https://shop.test/contact"]


def test_no_contact_details_anywhere_warns() -> None:
    (finding,) = ContactDetails().run(make_context(make_page("<p>Welcome</p>")))
    assert finding.severity is Severity.WARN


def test_phone_as_plain_text_suggests_a_tel_link() -> None:
    ctx = make_context(make_page("<p>Call +880 1717-863320</p>"))
    (finding,) = ClickToCall().run(ctx)
    assert finding.severity is Severity.WARN
    assert finding.snippets[0].code == '<a href="tel:+8801717863320">+880 1717-863320</a>'


def test_linked_phone_passes_and_no_phone_says_nothing() -> None:
    linked = make_context(make_page('<a href="tel:+8801717863320">+880 1717-863320</a>'))
    assert ClickToCall().run(linked)[0].severity is Severity.PASS
    assert ClickToCall().run(make_context(make_page("<p>Hello</p>"))) == []


def test_whatsapp_link_passes_or_is_suggested_with_the_sites_number() -> None:
    with_chat = make_context(make_page('<a href="https://wa.me/8801717863320">Chat</a>'))
    assert WhatsAppChat().run(with_chat)[0].severity is Severity.PASS

    (finding,) = WhatsAppChat().run(
        make_context(make_page('<a href="tel:+8801717863320">Call</a>'))
    )
    assert finding.severity is Severity.INFO  # a suggestion, no penalty
    assert "https://wa.me/8801717863320" in finding.snippets[0].code


def test_directions_link_or_map_passes() -> None:
    map_embed = make_page('<iframe src="https://www.google.com/maps/embed?pb=1"></iframe>')
    assert Directions().run(make_context(map_embed))[0].severity is Severity.PASS
    assert Directions().run(make_context(make_page("<p>Hi</p>")))[0].severity is Severity.INFO


def test_scripts_are_not_read_as_text() -> None:
    ctx = make_context(make_page("<script>var phone = '+880 1717-863320';</script><p>Hi</p>"))
    assert ClickToCall().run(ctx) == []  # the number is only inside a script
