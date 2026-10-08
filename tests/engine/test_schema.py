"""engine/schema.py: page kinds, reading JSON-LD, property rules and the suggested schema."""

import json

import pytest
from selectolax.lexbor import LexborHTMLParser

from bizzcheckup.engine import schema

HOME = "https://bakery.test/"
HOME_HTML = """<html><head><title>Cakes in Dhaka | Sweet Moments</title>
<meta property="og:site_name" content="Sweet Moments">
<meta name="description" content="Handmade cakes in Dhaka.">
<link rel="icon" href="/favicon.png"></head><body>
<a href="tel:+8801700000000">Call us</a> <a href="mailto:hello@bakery.test?subject=hi">Mail</a>
<a href="https://www.facebook.com/sweetmoments">Facebook</a>
<a href="https://instagram.com/sweetmoments">Instagram</a>
<a href="https://example.com/partner">Partner</a></body></html>"""


def tree(html: str) -> LexborHTMLParser:
    return LexborHTMLParser(html)


def site() -> schema.SiteFacts:
    return schema.site_facts(HOME, tree(HOME_HTML))


def json_ld(*items: object) -> str:
    blocks = "".join(f'<script type="application/ld+json">{json.dumps(i)}</script>' for i in items)
    return f"<html><head><title>Page | Sweet Moments</title>{blocks}</head><body></body></html>"


def suggestion_json(result: schema.PageSchema) -> dict[str, object]:
    code = result.suggestion
    assert code.startswith('<script type="application/ld+json">')
    assert code.endswith("</script>")
    parsed: dict[str, object] = json.loads(code.split(">", 1)[1].rsplit("<", 1)[0])
    return parsed


# --- what kind of page --------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "head", "kind"),
    [
        ("", "", "home"),
        ("about-us", "", "about"),
        ("company/team", "", "about"),
        ("contact", "", "contact"),
        ("blog/how-to-store-cakes", "", "article"),
        ("anything", '<meta property="og:type" content="article">', "article"),
        ("products/chocolate-cake", "", "product"),
        ("cake", '<meta property="product:price:amount" content="20">', "product"),
        ("services/wedding-cakes", "", "service"),
        ("faq", "", "faq"),
        ("blog", "", "listing"),
        ("services", "", "listing"),
        ("pricing", "", "page"),
    ],
)
def test_classify(path: str, head: str, kind: str) -> None:
    html = f"<html><head>{head}</head><body></body></html>"
    assert schema.classify(HOME + path, tree(html), homepage_url=HOME) == kind


def test_a_page_full_of_questions_is_an_faq() -> None:
    body = "".join(f"<h3>Question {n}?</h3><p>Answer {n}.</p>" for n in range(3))
    assert (
        schema.classify(HOME + "help-centre", tree(f"<body>{body}</body>"), homepage_url=HOME)
        == "faq"
    )


# --- reading JSON-LD ----------------------------------------------------------------------


def test_read_json_ld_flattens_lists_and_graphs() -> None:
    html = json_ld(
        [{"@type": "Product"}, {"@type": "Offer"}],
        {"@graph": [{"@type": "WebSite"}, {"@type": ["Organization", "Corporation"]}, "junk"]},
        {"@context": "https://schema.org"},  # no @type: ignored
    )
    items, broken = schema.read_json_ld(tree(html))
    assert [schema.types_of(i) for i in items] == [
        ["Product"],
        ["Offer"],
        ["WebSite"],
        ["Organization", "Corporation"],
    ]
    assert broken is False


def test_read_json_ld_reports_broken_blocks() -> None:
    html = '<script type="application/ld+json">{"@type": "Store",}</script>'
    assert schema.read_json_ld(tree(html)) == ([], True)


# --- property rules -----------------------------------------------------------------------


def test_missing_properties_follow_the_type_family() -> None:
    assert schema.missing_properties({"@type": "Bakery", "name": "x"}) == (
        ["address"],
        ["url", "telephone", "openingHoursSpecification", "image"],
    )
    assert schema.missing_properties({"@type": "UnknownThing"}) == ([], [])


def test_product_accepts_reviews_instead_of_offers() -> None:
    reviewed = {
        "@type": "Product",
        "name": "x",
        "image": "y",
        "aggregateRating": {"ratingValue": 5},
    }
    assert schema.missing_properties(reviewed)[0] == []


def test_nested_requirements() -> None:
    product = {"@type": "Product", "name": "x", "image": "y", "offers": {"price": "20"}}
    assert schema.missing_properties(product)[0] == ["offers.priceCurrency"]
    article = {
        "@type": "BlogPosting",
        "headline": "h",
        "image": "i",
        "datePublished": "d",
        "author": {},
    }
    assert "author" in schema.missing_properties(article)[0]  # empty author = missing
    faq = {"@type": "FAQPage", "mainEntity": [{"@type": "Question", "name": "q?"}]}
    assert schema.missing_properties(faq)[0][0].startswith("mainEntity")


def test_a_phone_number_counts_as_contact_details() -> None:
    org = {"@type": "Organization", "name": "x", "url": "u", "telephone": "+1"}
    assert "contactPoint" not in schema.missing_properties(org)[1]


# --- facts from the page -----------------------------------------------------------------


def test_site_facts() -> None:
    facts = site()
    assert facts.name == "Sweet Moments"
    assert facts.description == "Handmade cakes in Dhaka."
    assert facts.logo == "https://bakery.test/favicon.png"
    assert facts.telephone == "+8801700000000"
    assert facts.email == "hello@bakery.test"  # without ?subject=...
    assert facts.same_as == [
        "https://www.facebook.com/sweetmoments",
        "https://instagram.com/sweetmoments",
    ]


def test_page_title_drops_the_site_name() -> None:
    html = f"<html><head><title>Wedding cakes {schema.EN_DASH} Sweet Moments</title></head></html>"
    assert schema.page_facts(HOME + "x", tree(html), site()).title == "Wedding cakes"


def test_question_answers() -> None:
    html = "<details><summary>Do you deliver?</summary><p>Yes, all over Dhaka.</p></details>"
    assert schema.question_answers(tree(html)) == [("Do you deliver?", "Yes, all over Dhaka.")]


# --- one page, end to end -----------------------------------------------------------------


def test_homepage_without_schema_gets_a_complete_one() -> None:
    result = schema.analyse(HOME, tree(HOME_HTML), homepage_url=HOME, site=site())
    assert result.status == "missing"
    assert result.missing == ["Organization", "WebSite"]
    graph = suggestion_json(result)["@graph"]
    assert isinstance(graph, list)
    org, website = graph
    assert org["name"] == "Sweet Moments"
    assert org["contactPoint"]["telephone"] == "+8801700000000"
    assert org["sameAs"] == site().same_as
    assert website["publisher"] == {"@id": "https://bakery.test/#organization"}


def test_incomplete_schema_keeps_the_sites_own_values() -> None:
    html = json_ld({"@context": "https://schema.org", "@type": "Bakery", "name": "Our name"}) + (
        '<html><head><meta property="og:site_name" content="x"></head></html>'
    )
    result = schema.analyse(HOME, tree(html), homepage_url=HOME, site=site())
    assert result.incomplete == {"Bakery": ["address"]}
    assert result.missing == ["WebSite"]
    bakery = suggestion_json(result)["@graph"][0]  # type: ignore[index]
    assert bakery["name"] == "Our name"  # kept, not overwritten
    assert bakery["@type"] == "Bakery"  # the more specific type is kept
    assert bakery["address"]["streetAddress"].startswith("REPLACE:")


def test_complete_page_has_no_suggestion() -> None:
    page = {
        "@context": "https://schema.org",
        "@graph": [
            {"@type": "AboutPage", "name": "About", "url": HOME + "about", "description": "d"},
        ],
    }
    result = schema.analyse(HOME + "about", tree(json_ld(page)), homepage_url=HOME, site=site())
    assert result.status == "good"
    assert result.suggestion == ""
    assert result.summary() == "complete"


def test_breadcrumbs_follow_the_address() -> None:
    html = "<html><head><title>Chocolate cake | Sweet Moments</title></head></html>"
    result = schema.analyse(
        HOME + "products/chocolate-cake", tree(html), homepage_url=HOME, site=site()
    )
    crumbs = suggestion_json(result)["@graph"][1]["itemListElement"]  # type: ignore[index]
    assert [(c["position"], c["name"], c["item"]) for c in crumbs] == [
        (1, "Home", HOME),
        (2, "Products", HOME + "products"),
        (3, "Chocolate cake", HOME + "products/chocolate-cake"),
    ]


def test_faq_suggestion_uses_the_pages_questions() -> None:
    body = "".join(f"<h2>Question {n}?</h2><p>Answer {n}.</p>" for n in range(3))
    html = f"<html><head><title>FAQ</title></head><body>{body}</body></html>"
    result = schema.analyse(HOME + "faq", tree(html), homepage_url=HOME, site=site())
    questions = suggestion_json(result)["@graph"][0]["mainEntity"]  # type: ignore[index]
    assert [q["name"] for q in questions] == ["Question 0?", "Question 1?", "Question 2?"]
    assert questions[0]["acceptedAnswer"]["text"] == "Answer 0."
