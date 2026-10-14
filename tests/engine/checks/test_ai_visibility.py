"""AI search visibility: answers to quote, who the business is, and up to date."""

from datetime import UTC, datetime

from bizzcheckup.engine.checks.agentic import AnswerReady, BusinessIdentity, UpToDate
from bizzcheckup.engine.types import Severity

from ..factories import make_context, make_page

FAQ = """
<h2>How much does a cake cost?</h2><p>From 1500 taka for a 1 kg cake.</p>
<h2>Do you deliver?</h2><p>Yes, anywhere in Dhaka within 2 hours.</p>
"""


def test_questions_with_answers_pass() -> None:
    ctx = make_context(make_page("<p>Welcome</p>"), make_page(FAQ, url="https://shop.test/faq"))
    (finding,) = AnswerReady().run(ctx)
    assert finding.severity is Severity.PASS
    assert finding.affected_urls == ["https://shop.test/faq"]


def test_faq_schema_counts_as_answers() -> None:
    page = make_page('<script type="application/ld+json">{"@type": "FAQPage"}</script>')
    assert AnswerReady().run(make_context(page))[0].severity is Severity.PASS


def test_no_answers_warn_with_an_faq_snippet() -> None:
    (finding,) = AnswerReady().run(make_context(make_page("<h2>Our cakes</h2>")))
    assert finding.severity is Severity.WARN
    assert "<details>" in finding.snippets[0].code


def test_about_page_and_profiles_pass() -> None:
    page = make_page(
        '<a href="/about">About us</a><a href="https://www.linkedin.com/company/shop">LinkedIn</a>'
    )
    assert BusinessIdentity().run(make_context(page))[0].severity is Severity.PASS


def test_identity_missing_one_is_a_note_missing_both_warns() -> None:
    only_about = make_context(make_page('<a href="/about">About</a>'))
    assert BusinessIdentity().run(only_about)[0].severity is Severity.INFO
    (nothing,) = BusinessIdentity().run(make_context(make_page("<p>Hi</p>")))
    assert nothing.severity is Severity.WARN
    assert "no link to an About page and no links to your business profiles" in nothing.message


def test_old_copyright_year_warns_current_passes_none_says_nothing() -> None:
    this_year = datetime.now(UTC).year
    old = make_context(make_page("<footer>© 2019\u20132021 Shop Ltd</footer>"))
    (finding,) = UpToDate().run(old)
    assert finding.severity is Severity.WARN
    assert "© 2021" in finding.message

    current = make_context(make_page(f"<footer>Copyright {this_year} Shop</footer>"))
    assert UpToDate().run(current)[0].severity is Severity.PASS
    assert UpToDate().run(make_context(make_page("<p>Hi</p>"))) == []
