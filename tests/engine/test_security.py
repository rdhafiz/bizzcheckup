"""Security basics: the SECURITY collector and its five checks."""

from datetime import UTC, datetime, timedelta

import pytest
import respx

from bizzcheckup.engine.checks.best_practices import (
    CertificateExpiry,
    DomainExpiry,
    EmailSpoofing,
    ExposedFiles,
    SecurityTxt,
)
from bizzcheckup.engine.collectors import security
from bizzcheckup.engine.collectors.security import (
    DOH_URL,
    RDAP_URL,
    collect_security,
    probe_exposed_files,
    txt_value,
)
from bizzcheckup.engine.config import EngineConfig
from bizzcheckup.engine.context import SECURITY, AuditContext
from bizzcheckup.engine.fetcher import Fetcher
from bizzcheckup.engine.types import SecurityInfo, Severity

from .factories import make_context, make_page

NOW = datetime.now(UTC)


def dns_answer(kind: int, *records: str, status: int = 0) -> dict[str, object]:
    return {"Status": status, "Answer": [{"type": kind, "data": r} for r in records]}


def mock_dns(router: respx.Router, *, mx: bool = True, spf: str = "", dmarc: str = "") -> None:
    def query(name: str, kind: str) -> respx.Route:
        return router.get(DOH_URL, params={"name": name, "type": kind})

    query("shop.test", "MX").respond(
        json=dns_answer(15, "10 mail.shop.test.") if mx else dns_answer(15)
    )
    query("shop.test", "TXT").respond(json=dns_answer(16, f'"{spf}"', '"google-site=abc"'))
    query("_dmarc.shop.test", "TXT").respond(
        json=dns_answer(16, f'"{dmarc}"') if dmarc else dns_answer(16, status=3)
    )


@pytest.fixture
def no_tls(monkeypatch: pytest.MonkeyPatch) -> None:
    """Tests never open a real TLS connection: the certificate comes from here."""

    async def read_certificate(host: str, guard: object) -> tuple[datetime | None, str, str]:
        return NOW + timedelta(days=60), "Let's Encrypt", ""

    monkeypatch.setattr(security, "read_certificate", read_certificate)


# --- The collector ------------------------------------------------------------------


@pytest.mark.usefixtures("no_tls")
async def test_collector_reads_certificate_domain_and_email_records(
    fetcher: Fetcher, router: respx.Router
) -> None:
    ctx = make_context(make_page(url="https://www.shop.test/"))
    router.get(RDAP_URL + "shop.test").respond(
        json={"events": [{"eventAction": "expiration", "eventDate": "2027-03-03T10:00:00Z"}]}
    )
    mock_dns(router, spf="v=spf1 include:_spf.google.com ~all", dmarc="v=DMARC1; p=reject")

    await collect_security(ctx, fetcher, EngineConfig())

    info = ctx.security
    assert ctx.has(SECURITY)
    assert info.domain == "shop.test"  # the registered name, without www.
    assert info.cert_issuer == "Let's Encrypt"
    assert info.domain_expires == datetime(2027, 3, 3, 10, tzinfo=UTC)
    assert info.dns_checked
    assert info.has_mx is True
    assert info.spf == "v=spf1 include:_spf.google.com ~all"
    assert info.dmarc == "v=DMARC1; p=reject"


@pytest.mark.usefixtures("no_tls")
async def test_failed_lookups_stay_unknown(fetcher: Fetcher, router: respx.Router) -> None:
    ctx = make_context()
    router.get(RDAP_URL + "shop.test").respond(404)  # e.g. a ccTLD without RDAP
    router.get(DOH_URL).respond(500)

    await collect_security(ctx, fetcher, EngineConfig())

    assert ctx.security.domain_lookup_failed
    assert ctx.security.domain_expires is None
    assert not ctx.security.dns_checked  # "couldn't find out", not "missing"
    assert ctx.security.spf is None


def test_long_txt_records_are_joined() -> None:
    assert txt_value('"v=spf1 include:a.test" " include:b.test -all"') == (
        "v=spf1 include:a.test include:b.test -all"
    )


async def test_exposed_files_are_found_but_never_kept(
    fetcher: Fetcher, router: respx.Router
) -> None:
    ctx = make_context()
    router.get("https://shop.test/.git/HEAD").respond(200, text="ref: refs/heads/main\n")
    router.get("https://shop.test/.env").respond(200, text="DB_PASSWORD=secret\nAPP_KEY=abc\n")
    router.get("https://shop.test/.well-known/security.txt").respond(404)

    await probe_exposed_files(ctx, fetcher)

    info = ctx.security
    assert info.git_exposed
    assert info.env_exposed
    assert info.security_txt is False
    assert "secret" not in info.model_dump_json()  # only yes/no is stored


async def test_html_pages_for_every_address_are_not_exposed_files(
    fetcher: Fetcher, router: respx.Router
) -> None:
    """Many sites answer every address with their homepage: that's not a leak."""
    ctx = make_context()
    page = "<!doctype html><html><body>APP_KEY=x\nDB_HOST=y</body></html>"
    for path in ("/.git/HEAD", "/.env", "/.well-known/security.txt"):
        router.get(f"https://shop.test{path}").respond(200, html=page)

    await probe_exposed_files(ctx, fetcher)

    assert ctx.security.files_checked
    assert not ctx.security.git_exposed
    assert not ctx.security.env_exposed


# --- The checks ---------------------------------------------------------------------


def context_with(**info: object) -> AuditContext:
    ctx = make_context(capabilities={SECURITY})
    ctx.security = SecurityInfo(domain="shop.test", **info)
    return ctx


@pytest.mark.parametrize(
    ("days", "severity"),
    [(90, Severity.PASS), (14, Severity.WARN), (3, Severity.FAIL), (-2, Severity.FAIL)],
)
def test_certificate_expiry(days: int, severity: Severity) -> None:
    ctx = context_with(cert_expires=NOW + timedelta(days=days, hours=1), cert_issuer="R3")
    (finding,) = CertificateExpiry().run(ctx)
    assert finding.severity is severity


def test_invalid_certificate_fails() -> None:
    ctx = context_with(cert_error="certificate has expired")
    (finding,) = CertificateExpiry().run(ctx)
    assert finding.severity is Severity.FAIL
    assert "certificate has expired" in finding.message


@pytest.mark.parametrize(
    ("days", "severity"), [(200, Severity.PASS), (20, Severity.WARN), (5, Severity.FAIL)]
)
def test_domain_expiry(days: int, severity: Severity) -> None:
    (finding,) = DomainExpiry().run(context_with(domain_expires=NOW + timedelta(days=days)))
    assert finding.severity is severity


def test_unknown_domain_expiry_is_only_a_note() -> None:
    (finding,) = DomainExpiry().run(context_with(domain_lookup_failed=True))
    assert finding.severity is Severity.INFO


def test_missing_spf_and_dmarc_suggest_records() -> None:
    ctx = context_with(dns_checked=True, has_mx=False, spf="", dmarc="")
    (finding,) = EmailSpoofing().run(ctx)
    assert finding.severity is Severity.WARN
    assert "no SPF and no DMARC record" in finding.message
    codes = [snippet.code for snippet in finding.snippets]
    assert codes == ["v=spf1 -all", "v=DMARC1; p=quarantine; rua=mailto:dmarc@shop.test"]


def test_dmarc_p_none_is_a_note_and_good_records_pass() -> None:
    weak = context_with(dns_checked=True, spf="v=spf1 -all", dmarc="v=DMARC1; p=none")
    assert EmailSpoofing().run(weak)[0].severity is Severity.INFO
    good = context_with(dns_checked=True, spf="v=spf1 -all", dmarc="v=DMARC1; p=reject")
    assert EmailSpoofing().run(good)[0].severity is Severity.PASS


def test_unchecked_dns_says_nothing() -> None:
    assert EmailSpoofing().run(context_with()) == []


def test_exposed_files_fail_hard() -> None:
    (finding,) = ExposedFiles().run(context_with(files_checked=True, env_exposed=True))
    assert finding.severity is Severity.FAIL
    assert "/.env" in finding.message
    (ok,) = ExposedFiles().run(context_with(files_checked=True))
    assert ok.severity is Severity.PASS


def test_security_txt_suggests_the_file() -> None:
    (finding,) = SecurityTxt().run(context_with(security_txt=False))
    assert finding.severity is Severity.INFO
    assert finding.snippets[0].code.startswith("Contact: mailto:security@shop.test")
