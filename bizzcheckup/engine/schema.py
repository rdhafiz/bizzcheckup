"""Page schema: does each page carry the right structured data (schema.org JSON-LD)?

For one page this module:

1. works out what KIND of page it is (homepage, article, product, contact, ...);
2. reads its JSON-LD and checks it against what that kind of page should have, including
   the properties Google requires and recommends for each type;
3. writes a complete JSON-LD block for the page when something is missing: what the page
   already tells us (title, description, image, phone, social links, dates, FAQ questions,
   breadcrumbs) is filled in, everything else is marked "REPLACE: ...".

Pure Python, no Django: the check in checks/seo.py (PageSchema) uses it, and it is tested on
plain HTML strings.
"""

import json
import re
from dataclasses import dataclass, field
from typing import Any
from urllib.parse import urljoin, urlsplit

from selectolax.lexbor import LexborHTMLParser

from .urls import domain, origin

Item = dict[str, Any]  # one JSON-LD object, e.g. {"@type": "Product", "name": ...}


# How page titles join a page name and the site name: "Pricing | Shop", "Pricing - Shop".
# Built from code points: an en dash, an em dash and a middle dot look like a hyphen in code.
EN_DASH, EM_DASH, MIDDLE_DOT = chr(0x2013), chr(0x2014), chr(0x00B7)
TITLE_SEPARATORS = (" | ", f" {EN_DASH} ", f" {EM_DASH} ", " - ", f" {MIDDLE_DOT} ")


def placeholder(what: str) -> str:
    """A value the site owner must fill in. Easy to spot, and easy to search for."""
    return f"REPLACE: {what}"


# --- What kind of page is this? --------------------------------------------------------------

KIND_LABELS = {
    "home": "Homepage",
    "about": "About page",
    "contact": "Contact page",
    "article": "Article",
    "product": "Product page",
    "service": "Service page",
    "faq": "FAQ page",
    "listing": "Listing page",
    "page": "Page",
}
ABOUT_WORDS = {"about", "about-us", "who-we-are", "our-story", "company", "team", "our-team"}
CONTACT_WORDS = {"contact", "contact-us", "contacts", "get-in-touch", "reach-us", "get-a-quote"}
FAQ_WORDS = {"faq", "faqs", "questions", "frequently-asked-questions"}
BLOG_SECTIONS = {"blog", "news", "insights", "articles", "article", "posts", "post", "stories"}
PRODUCT_SECTIONS = {"product", "products", "shop", "store", "item", "items"}
SERVICE_SECTIONS = {"service", "services", "solutions", "what-we-do"}


def path_segments(url: str) -> list[str]:
    return [part for part in urlsplit(url).path.lower().split("/") if part]


def classify(url: str, tree: LexborHTMLParser, *, homepage_url: str) -> str:
    """The kind of page, from its address first and its content second."""
    segments = path_segments(url)
    if not segments or url.rstrip("/") == homepage_url.rstrip("/"):
        return "home"
    og_type = _meta(tree, "property", "og:type").lower()
    first, last = segments[0], segments[-1]
    deep = len(segments) >= 2
    if og_type == "article" or (first in BLOG_SECTIONS and deep):
        return "article"
    if (
        og_type == "product"
        or _meta(tree, "property", "product:price:amount")
        or (first in PRODUCT_SECTIONS and deep)
    ):
        return "product"
    if last in FAQ_WORDS or len(question_answers(tree)) >= 3:
        return "faq"
    if any(part in CONTACT_WORDS for part in segments):
        return "contact"
    if any(part in ABOUT_WORDS for part in segments):
        return "about"
    if first in SERVICE_SECTIONS and deep:
        return "service"
    if first in BLOG_SECTIONS | PRODUCT_SECTIONS | SERVICE_SECTIONS:
        return "listing"
    return "page"


# --- schema.org types and the properties each one needs ----------------------------------------

LOCAL_BUSINESS_TYPES = {
    "LocalBusiness", "ProfessionalService", "Store", "OnlineStore", "Restaurant",
    "CafeOrCoffeeShop", "Bakery", "BarOrPub", "FastFoodRestaurant", "Dentist", "Physician",
    "MedicalBusiness", "MedicalClinic", "HealthAndBeautyBusiness", "HairSalon", "BeautySalon",
    "DaySpa", "AutoRepair", "AutomotiveBusiness", "AutoDealer", "LegalService", "Attorney",
    "AccountingService", "FinancialService", "RealEstateAgent", "TravelAgency",
    "HomeAndConstructionBusiness", "Plumber", "Electrician", "GeneralContractor",
    "HousePainter", "Locksmith", "MovingCompany", "Hotel", "LodgingBusiness",
    "SportsActivityLocation", "ExerciseGym", "ChildCare", "Pharmacy", "Optician",
    "VeterinaryCare", "ClothingStore", "ElectronicsStore", "FurnitureStore", "GroceryStore",
    "JewelryStore", "ShoeStore", "BookStore", "Florist", "EntertainmentBusiness",
}  # fmt: skip
ORGANIZATION_TYPES = LOCAL_BUSINESS_TYPES | {
    "Organization", "Corporation", "NGO", "EducationalOrganization", "GovernmentOrganization",
    "OnlineBusiness", "NewsMediaOrganization", "MedicalOrganization", "SportsOrganization",
    "Airline", "CollegeOrUniversity", "School",
}  # fmt: skip
ARTICLE_TYPES = {
    "Article",
    "BlogPosting",
    "NewsArticle",
    "TechArticle",
    "Report",
    "ScholarlyArticle",
}
WEBPAGE_TYPES = {
    "WebPage", "AboutPage", "ContactPage", "CollectionPage", "FAQPage", "ItemPage",
    "ProfilePage", "QAPage", "SearchResultsPage", "CheckoutPage", "MedicalWebPage",
}  # fmt: skip
PRODUCT_TYPES = {"Product", "ProductGroup", "IndividualProduct", "Vehicle", "Book"}


def family(schema_type: str) -> str | None:
    """Which rule set applies to a type: "LocalBusiness" covers Bakery, Dentist, ...

    A type with its own rules wins over its family: FAQPage is a kind of WebPage, but it is
    checked as an FAQPage (each question needs an answer)."""
    if schema_type in RULES:
        return schema_type
    if schema_type in LOCAL_BUSINESS_TYPES:
        return "LocalBusiness"
    if schema_type in ORGANIZATION_TYPES:
        return "Organization"
    if schema_type in ARTICLE_TYPES:
        return "Article"
    if schema_type in PRODUCT_TYPES:
        return "Product"
    if schema_type in WEBPAGE_TYPES:
        return "WebPage"
    return None


# family -> (required, recommended). Based on Google's structured data guidelines and the
# properties schema.org marks as expected; "required" means Google won't use the item without it.
RULES: dict[str, tuple[list[str], list[str]]] = {
    "Organization": (["name", "url"], ["logo", "sameAs", "contactPoint"]),
    "LocalBusiness": (
        ["name", "address"],
        ["url", "telephone", "openingHoursSpecification", "image"],
    ),
    "WebSite": (["name", "url"], []),
    "Article": (["headline", "image", "datePublished", "author"], ["dateModified", "publisher"]),
    "Product": (["name", "image", "offers"], ["description", "brand", "sku"]),
    "Service": (["name", "provider"], ["description", "serviceType", "areaServed"]),
    "FAQPage": (["mainEntity"], []),
    "BreadcrumbList": (["itemListElement"], []),
    "WebPage": (["name", "url"], ["description"]),
}

# Page kind -> the types it should carry: (label shown to the owner, acceptable types).
EXPECTED: dict[str, list[tuple[str, set[str]]]] = {
    "home": [("Organization", ORGANIZATION_TYPES), ("WebSite", {"WebSite"})],
    "about": [("AboutPage", {"AboutPage"})],
    "contact": [("ContactPage", {"ContactPage"})],
    "article": [("Article", ARTICLE_TYPES), ("BreadcrumbList", {"BreadcrumbList"})],
    "product": [("Product", PRODUCT_TYPES), ("BreadcrumbList", {"BreadcrumbList"})],
    "service": [("Service", {"Service"}), ("BreadcrumbList", {"BreadcrumbList"})],
    "faq": [("FAQPage", {"FAQPage"})],
    "listing": [
        ("CollectionPage", {"CollectionPage", "ItemList"}),
        ("BreadcrumbList", {"BreadcrumbList"}),
    ],
    "page": [("WebPage", WEBPAGE_TYPES), ("BreadcrumbList", {"BreadcrumbList"})],
}


def types_of(item: Item) -> list[str]:
    found = item.get("@type")
    if isinstance(found, list):
        return [str(t) for t in found]
    return [str(found)] if found else []


def missing_properties(item: Item) -> tuple[list[str], list[str]]:
    """(required, recommended) properties this item lacks, including a few nested musts."""
    rule = next((RULES[f] for t in types_of(item) if (f := family(t)) in RULES), None)
    if rule is None:
        return [], []
    required = [name for name in rule[0] if not _has(item, name)]
    recommended = [name for name in rule[1] if not _has(item, name)]
    kinds = {family(t) for t in types_of(item)}
    if "Organization" in kinds and "contactPoint" in recommended and _has(item, "telephone"):
        recommended.remove("contactPoint")  # a phone number does the same job
    if (
        "Product" in kinds
        and "offers" in required
        and (_has(item, "review") or _has(item, "aggregateRating"))
    ):
        required.remove("offers")  # Google accepts offers OR review OR aggregateRating
    required += _nested_problems(item, kinds)
    return required, recommended


def _nested_problems(item: Item, kinds: set[str | None]) -> list[str]:
    problems: list[str] = []
    if "Product" in kinds and isinstance(item.get("offers"), dict):
        offer = item["offers"]
        problems += [
            f"offers.{name}" for name in ("price", "priceCurrency") if not _has(offer, name)
        ]
    if (
        "Article" in kinds
        and isinstance(item.get("author"), dict)
        and not _has(item["author"], "name")
    ):
        problems.append("author.name")
    if "FAQPage" in kinds and isinstance(item.get("mainEntity"), list):
        for question in item["mainEntity"]:
            answer = question.get("acceptedAnswer") if isinstance(question, dict) else None
            if (
                not isinstance(question, dict)
                or not _has(question, "name")
                or not (isinstance(answer, dict) and _has(answer, "text"))
            ):
                problems.append(
                    "mainEntity (each Question needs a name and an acceptedAnswer.text)"
                )
                break
    return problems


def _has(item: Item, name: str) -> bool:
    value = item.get(name)
    return value not in (None, "", [], {})


# --- Reading a page's JSON-LD -----------------------------------------------------------------


def read_json_ld(tree: LexborHTMLParser) -> tuple[list[Item], bool]:
    """All JSON-LD items on the page, flattened (lists and @graph), and whether any block is
    broken JSON that search engines would ignore."""
    items: list[Item] = []
    broken = False
    for node in tree.css('script[type="application/ld+json"]'):
        try:
            data = json.loads(node.text())
        except ValueError:
            broken = True
            continue
        stack = data if isinstance(data, list) else [data]
        while stack:
            entry = stack.pop(0)
            if not isinstance(entry, dict):
                continue
            if isinstance(entry.get("@graph"), list):
                stack.extend(entry["@graph"])
            if entry.get("@type"):
                items.append(entry)
    return items, broken


# --- What the page already tells us ------------------------------------------------------------

SOCIAL_HOSTS = (
    "facebook.com", "instagram.com", "linkedin.com", "x.com", "twitter.com", "youtube.com",
    "tiktok.com", "pinterest.com", "github.com", "threads.net",
)  # fmt: skip


@dataclass
class SiteFacts:
    """Facts about the business, read from the homepage once and shared by every page."""

    origin: str
    name: str
    description: str = ""
    logo: str = ""
    telephone: str = ""
    email: str = ""
    same_as: list[str] = field(default_factory=list)

    @property
    def org_id(self) -> str:
        return f"{self.origin}/#organization"

    @property
    def website_id(self) -> str:
        return f"{self.origin}/#website"


def site_facts(homepage_url: str, tree: LexborHTMLParser) -> SiteFacts:
    base = origin(homepage_url)
    name = (
        _meta(tree, "property", "og:site_name")
        or _site_name_from_title(_title(tree))
        or domain(base)
    )
    logo = ""
    for rel in ("apple-touch-icon", "icon"):
        node = next(
            (
                n
                for n in tree.css("link[rel]")
                if rel in (n.attributes.get("rel") or "").lower().split()
            ),
            None,
        )
        if node and node.attributes.get("href"):
            logo = urljoin(homepage_url, node.attributes["href"] or "")
            break
    same_as = []
    for node in tree.css("a[href]"):
        href = (node.attributes.get("href") or "").strip()
        host = domain(href)
        if (
            host
            and any(host == h or host.endswith("." + h) for h in SOCIAL_HOSTS)
            and href not in same_as
        ):
            same_as.append(href)
    return SiteFacts(
        origin=base,
        name=name,
        description=_description(tree),
        logo=logo,
        telephone=_link_value(tree, "tel:"),
        email=_link_value(tree, "mailto:"),
        same_as=same_as[:8],
    )


@dataclass
class PageFacts:
    url: str
    title: str
    description: str
    image: str
    published: str = ""
    modified: str = ""
    author: str = ""
    price: str = ""
    currency: str = ""
    questions: list[tuple[str, str]] = field(default_factory=list)


def page_facts(url: str, tree: LexborHTMLParser, site: SiteFacts) -> PageFacts:
    title = _meta(tree, "property", "og:title") or _title(tree)
    if site.name:  # "Pricing | Shop" -> "Pricing"
        for separator in TITLE_SEPARATORS:
            head, sep, tail = title.rpartition(separator)
            if sep and site.name.lower() in tail.lower():
                title = head
                break
    published = _meta(tree, "property", "article:published_time")
    if not published:
        node = tree.css_first("time[datetime]")
        published = (node.attributes.get("datetime") or "") if node else ""
    image = _meta(tree, "property", "og:image")
    return PageFacts(
        url=url,
        title=title.strip(),
        description=_description(tree),
        image=urljoin(url, image) if image else "",
        published=published,
        modified=_meta(tree, "property", "article:modified_time"),
        author=_meta(tree, "name", "author"),
        price=_meta(tree, "property", "product:price:amount"),
        currency=_meta(tree, "property", "product:price:currency"),
        questions=question_answers(tree),
    )


def question_answers(tree: LexborHTMLParser) -> list[tuple[str, str]]:
    """Visible questions and their answers: <summary>/<h2-4> ending in "?" + the next text."""
    found: list[tuple[str, str]] = []
    for node in tree.css("summary, h2, h3, h4"):
        question = " ".join(node.text().split())
        if not question.endswith("?") or len(question) > 200:
            continue
        answer_node = node.next
        while answer_node is not None and not " ".join((answer_node.text() or "").split()):
            answer_node = answer_node.next
        answer = " ".join((answer_node.text() if answer_node is not None else "").split())
        if answer and answer != question:
            found.append((question, answer[:300]))
        if len(found) == 6:
            break
    return found


def _meta(tree: LexborHTMLParser, attribute: str, value: str) -> str:
    for node in tree.css("meta"):
        if (node.attributes.get(attribute) or "").strip().lower() == value.lower():
            return (node.attributes.get("content") or "").strip()
    return ""


def _title(tree: LexborHTMLParser) -> str:
    node = tree.css_first("title")
    return node.text(strip=True) if node else ""


def _description(tree: LexborHTMLParser) -> str:
    return _meta(tree, "name", "description") or _meta(tree, "property", "og:description")


def _site_name_from_title(title: str) -> str:
    for separator in TITLE_SEPARATORS:
        if separator in title:
            return title.rpartition(separator)[2].strip()
    return title.strip()


def _link_value(tree: LexborHTMLParser, scheme: str) -> str:
    for node in tree.css(f'a[href^="{scheme}"]'):
        value = (node.attributes.get("href") or "")[len(scheme) :].split("?")[0].strip()
        if value:
            return value
    return ""


# --- Building the suggestion -----------------------------------------------------------------


def organization(site: SiteFacts, schema_type: str = "Organization") -> Item:
    item: Item = {
        "@type": schema_type,
        "@id": site.org_id,
        "name": site.name,
        "url": f"{site.origin}/",
        "logo": site.logo or placeholder("full URL of your logo image"),
        "description": site.description or placeholder("one sentence about your business"),
        "sameAs": site.same_as
        or [
            placeholder("https://www.facebook.com/your-page"),
            placeholder("https://www.linkedin.com/company/your-company"),
        ],
        "contactPoint": {
            "@type": "ContactPoint",
            "telephone": site.telephone or placeholder("+1-555-000-0000"),
            "contactType": "customer service",
            **({"email": site.email} if site.email else {}),
        },
    }
    if family(schema_type) == "LocalBusiness":
        item["telephone"] = site.telephone or placeholder("+1-555-000-0000")
        item["image"] = site.logo or placeholder("full URL of a photo of your business")
        item["address"] = {
            "@type": "PostalAddress",
            "streetAddress": placeholder("street and number"),
            "addressLocality": placeholder("city"),
            "postalCode": placeholder("postal code"),
            "addressCountry": placeholder("two-letter country code, e.g. US"),
        }
        item["openingHoursSpecification"] = [{
            "@type": "OpeningHoursSpecification",
            "dayOfWeek": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"],
            "opens": placeholder("09:00"),
            "closes": placeholder("17:00"),
        }]  # fmt: skip
    return item


def website(site: SiteFacts) -> Item:
    return {
        "@type": "WebSite",
        "@id": site.website_id,
        "name": site.name,
        "url": f"{site.origin}/",
        "publisher": {"@id": site.org_id},
    }


def web_page(page: PageFacts, site: SiteFacts, schema_type: str) -> Item:
    return {
        "@type": schema_type,
        "@id": f"{page.url}#webpage",
        "url": page.url,
        "name": page.title or placeholder("the page's title"),
        "description": page.description or placeholder("one sentence about this page"),
        "isPartOf": {"@id": site.website_id},
        "publisher": _org_reference(site),
    }


def breadcrumbs(page: PageFacts, site: SiteFacts) -> Item:
    crumbs = [("Home", f"{site.origin}/")]
    segments = [part for part in urlsplit(page.url).path.split("/") if part]
    for depth, part in enumerate(segments, start=1):
        name = page.title if depth == len(segments) and page.title else _humanize(part)
        crumbs.append((name, f"{site.origin}/{'/'.join(segments[:depth])}"))
    return {
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": position, "name": name, "item": url}
            for position, (name, url) in enumerate(crumbs, start=1)
        ],
    }


def article(page: PageFacts, site: SiteFacts) -> Item:
    return {
        "@type": "BlogPosting",
        "headline": (page.title or placeholder("the article's headline"))[:110],
        "description": page.description or placeholder("one-sentence summary"),
        "image": [page.image or placeholder("full URL of the article's main image")],
        "datePublished": page.published or placeholder("publication date, e.g. 2026-01-31"),
        "dateModified": page.modified
        or page.published
        or placeholder("last update, e.g. 2026-02-15"),
        "author": {"@type": "Person", "name": page.author or placeholder("author's name")},
        "publisher": _org_reference(site),
        "mainEntityOfPage": page.url,
    }


def product(page: PageFacts, site: SiteFacts) -> Item:
    return {
        "@type": "Product",
        "name": page.title or placeholder("product name"),
        "description": page.description or placeholder("one-sentence product description"),
        "image": [page.image or placeholder("full URL of the product photo")],
        "brand": {"@type": "Brand", "name": site.name},
        "sku": placeholder("your product code"),
        "offers": {
            "@type": "Offer",
            "url": page.url,
            "price": page.price or placeholder("price, e.g. 49.99"),
            "priceCurrency": page.currency or placeholder("currency code, e.g. USD"),
            "availability": "https://schema.org/InStock",
        },
    }


def service(page: PageFacts, site: SiteFacts) -> Item:
    return {
        "@type": "Service",
        "name": page.title or placeholder("service name"),
        "description": page.description or placeholder("one sentence about the service"),
        "serviceType": page.title or placeholder("type of service"),
        "provider": _org_reference(site),
        "areaServed": placeholder("the city, region or country you serve"),
        "url": page.url,
    }


def faq(page: PageFacts) -> Item:
    pairs = page.questions or [
        (placeholder("a question customers ask"), placeholder("its answer")),
        (placeholder("another common question"), placeholder("its answer")),
    ]
    return {
        "@type": "FAQPage",
        "mainEntity": [
            {"@type": "Question", "name": q, "acceptedAnswer": {"@type": "Answer", "text": a}}
            for q, a in pairs
        ],
    }


def _org_reference(site: SiteFacts) -> Item:
    return {
        "@type": "Organization",
        "@id": site.org_id,
        "name": site.name,
        "url": f"{site.origin}/",
    }


def _humanize(slug: str) -> str:
    return re.sub(r"[-_]+", " ", slug).strip().capitalize() or slug


def build(label: str, page: PageFacts, site: SiteFacts, existing_type: str | None) -> Item:
    """A complete item for one expected type, keeping an existing more specific type."""
    if label == "Organization":
        return organization(site, existing_type or "Organization")
    if label == "WebSite":
        return website(site)
    if label == "Article":
        return article(page, site) | ({"@type": existing_type} if existing_type else {})
    if label == "Product":
        return product(page, site)
    if label == "Service":
        return service(page, site)
    if label == "FAQPage":
        return faq(page)
    if label == "BreadcrumbList":
        return breadcrumbs(page, site)
    return web_page(page, site, existing_type or label)  # AboutPage, ContactPage, WebPage, ...


def complete(existing: Item, built: Item) -> Item:
    """The site's own item, with every property it lacks taken from our built one."""
    merged = dict(existing)
    for key, value in built.items():
        if not _has(merged, key):
            merged[key] = value
        elif isinstance(merged[key], dict) and isinstance(value, dict):
            merged[key] = complete(merged[key], value)
    return merged


# --- One page, end to end ---------------------------------------------------------------------


@dataclass
class PageSchema:
    url: str
    kind: str
    found: list[str]  # schema types already on the page
    broken: bool = False  # a JSON-LD block that isn't valid JSON
    missing: list[str] = field(default_factory=list)  # expected types not on the page
    incomplete: dict[str, list[str]] = field(default_factory=dict)  # type -> missing required
    richer: dict[str, list[str]] = field(default_factory=dict)  # type -> missing recommended
    suggestion: str = ""  # complete JSON-LD for the page ("" when nothing is missing)

    @property
    def kind_label(self) -> str:
        return KIND_LABELS[self.kind]

    @property
    def status(self) -> str:
        if self.broken:
            return "broken"
        if self.missing:
            return "missing"
        if self.incomplete:
            return "incomplete"
        if self.richer:
            return "could be richer"
        return "good"

    def summary(self) -> str:
        """One line for the report, e.g. "missing Organization, WebSite"."""
        parts = []
        if self.broken:
            parts.append("broken JSON-LD")
        if self.missing:
            parts.append("missing " + ", ".join(self.missing))
        for schema_type, names in self.incomplete.items():
            parts.append(f"{schema_type} lacks {', '.join(names)}")
        for schema_type, names in self.richer.items():
            parts.append(f"{schema_type} could add {', '.join(names)}")
        return "; ".join(parts) or "complete"


def analyse(url: str, tree: LexborHTMLParser, *, homepage_url: str, site: SiteFacts) -> PageSchema:
    kind = classify(url, tree, homepage_url=homepage_url)
    items, broken = read_json_ld(tree)
    found = sorted({t for item in items for t in types_of(item)})
    result = PageSchema(url=url, kind=kind, found=found, broken=broken)
    facts = page_facts(url, tree, site)

    graph: list[Item] = []
    for label, acceptable in EXPECTED[kind]:
        match = next((item for item in items if set(types_of(item)) & acceptable), None)
        existing_type = (
            next((t for t in types_of(match) if t in acceptable), None) if match else None
        )
        built = build(label, facts, site, existing_type)
        if match is None:
            result.missing.append(label)
            graph.append(built)
            continue
        required, recommended = missing_properties(match)
        if required:
            result.incomplete[existing_type or label] = required
        if recommended:
            result.richer[existing_type or label] = recommended
        graph.append(complete(match, built) if required or recommended else match)

    if result.status != "good":
        body = {"@context": "https://schema.org", "@graph": [_without_context(i) for i in graph]}
        result.suggestion = (
            '<script type="application/ld+json">\n'
            + json.dumps(body, indent=2, ensure_ascii=False)
            + "\n</script>"
        )
    return result


def _without_context(item: Item) -> Item:
    """Inside an @graph the shared @context covers every item."""
    return {key: value for key, value in item.items() if key != "@context"}
