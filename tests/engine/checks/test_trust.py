"""Trust and conversion: a next step on a phone, a privacy policy, reviews."""

from bizzcheckup.engine.checks.trust import CallToAction, PrivacyPolicy, SocialProof
from bizzcheckup.engine.context import RENDER, AuditContext
from bizzcheckup.engine.types import DeviceView, RenderResult, Severity

from ..factories import make_context, make_page


def phone_ctx(*links: str) -> AuditContext:
    ctx = make_context(capabilities={RENDER})
    phone = DeviceView(
        name="mobile", width=390, height=844, layout_width=390, scroll_width=390,
        first_screen_links=list(links),
    )  # fmt: skip
    ctx.render = RenderResult(url="https://shop.test/", html="", text_length=0, devices=[phone])
    return ctx


def test_a_call_to_action_in_the_first_screen_passes() -> None:
    ctx = phone_ctx("Home | https://shop.test/", "Book a table | /book")
    (finding,) = CallToAction().run(ctx)
    assert finding.severity is Severity.PASS
    assert '"Book a table"' in finding.message


def test_a_phone_or_whatsapp_link_counts_too() -> None:
    (finding,) = CallToAction().run(phone_ctx(" | tel:+8801717863320"))
    assert finding.severity is Severity.PASS


def test_no_next_step_on_a_phone_warns() -> None:
    ctx = phone_ctx("Home | https://shop.test/", "Menu | ", "About us | /about")
    (finding,) = CallToAction().run(ctx)
    assert finding.severity is Severity.WARN


def test_bangla_call_to_action_counts() -> None:
    (finding,) = CallToAction().run(phone_ctx("এখনই অর্ডার করুন | /order"))
    assert finding.severity is Severity.PASS


def test_privacy_policy_link_passes() -> None:
    ctx = make_context(make_page('<footer><a href="/privacy">Privacy</a></footer>'))
    assert PrivacyPolicy().run(ctx)[0].severity is Severity.PASS


def test_forms_without_a_privacy_policy_warn() -> None:
    page = make_page('<form><input type="email" name="email"><button>Send</button></form>')
    (finding,) = PrivacyPolicy().run(make_context(page))
    assert finding.severity is Severity.WARN
    (note,) = PrivacyPolicy().run(make_context(make_page("<p>Hello</p>")))
    assert note.severity is Severity.INFO


def test_testimonials_or_review_schema_pass() -> None:
    words = make_page("<h2>What our clients say</h2><blockquote>Great work!</blockquote>")
    assert SocialProof().run(make_context(words))[0].severity is Severity.PASS
    schema = make_page(
        '<script type="application/ld+json">'
        '{"@type": "LocalBusiness", "aggregateRating": {"ratingValue": 4.8}}</script>'
    )
    assert SocialProof().run(make_context(schema))[0].severity is Severity.PASS


def test_no_social_proof_is_a_note_with_a_ready_snippet() -> None:
    (finding,) = SocialProof().run(make_context(make_page("<p>We make cakes.</p>")))
    assert finding.severity is Severity.INFO
    assert "<blockquote>" in finding.snippets[0].code
