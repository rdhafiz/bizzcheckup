"""Django admin: search, filters and CSV export of leads."""

import csv
import io

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from bizzcheckup.checkups.admin import safe_cell
from bizzcheckup.checkups.models import Checkup, Finding, Lead

pytestmark = pytest.mark.django_db


@pytest.fixture
def admin_client(client: Client) -> Client:
    User.objects.create_superuser("admin", "admin@example.com", "test-only-password")
    client.login(username="admin", password="test-only-password")
    return client


@pytest.fixture
def data() -> Lead:
    lead = Lead.objects.create(name="Ayesha", email="ayesha@shop.test", consent=True)
    checkup = Checkup.objects.create(
        url="https://shop.test/", domain="shop.test", status="done", health_score=42, lead=lead
    )
    Checkup.objects.create(url="https://other.test/", domain="other.test", health_score=95)
    Finding.objects.create(
        checkup=checkup, check_id="seo.title", category="seo", severity="fail",
        message="No title", why_it_matters="w", how_to_fix="f", effort="low", impact="high",
    )  # fmt: skip
    return lead


@pytest.mark.parametrize(
    "url",
    [
        "admin:checkups_checkup_changelist",
        "admin:checkups_finding_changelist",
        "admin:checkups_lead_changelist",
    ],
)
def test_admin_lists_load(admin_client: Client, data: Lead, url: str) -> None:
    assert admin_client.get(reverse(url)).status_code == 200


def test_checkups_are_searchable_and_filterable(admin_client: Client, data: Lead) -> None:
    url = reverse("admin:checkups_checkup_changelist")
    by_email = admin_client.get(url, {"q": "ayesha@shop.test"}).content.decode()
    assert "shop.test" in by_email
    assert "other.test" not in by_email

    urgent = admin_client.get(url, {"band": "urgent"}).content.decode()
    assert "shop.test" in urgent
    assert "other.test" not in urgent


def test_findings_filter_by_severity(admin_client: Client, data: Lead) -> None:
    url = reverse("admin:checkups_finding_changelist")
    assert "seo.title" in admin_client.get(url, {"severity__exact": "fail"}).content.decode()
    assert "seo.title" not in admin_client.get(url, {"severity__exact": "pass"}).content.decode()


def test_checkup_detail_shows_report_link_and_findings(admin_client: Client, data: Lead) -> None:
    checkup = Checkup.objects.get(domain="shop.test")
    html = admin_client.get(
        reverse("admin:checkups_checkup_change", args=[checkup.pk])
    ).content.decode()
    assert reverse("checkups:detail", args=[checkup.pk]) in html
    assert "No title" in html


def test_checkups_cannot_be_added_in_admin(admin_client: Client) -> None:
    assert admin_client.get(reverse("admin:checkups_checkup_add")).status_code == 403


def test_export_leads_to_csv(admin_client: Client, data: Lead) -> None:
    Lead.objects.create(name='=HYPERLINK("http://evil")', email="x@y.test")
    response = admin_client.post(
        reverse("admin:checkups_lead_changelist"),
        {"action": "export_csv", "_selected_action": [lead.pk for lead in Lead.objects.all()]},
    )

    assert response["Content-Type"].startswith("text/csv")
    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig"))))
    assert rows[0] == ["name", "email", "consent", "created_at", "websites", "latest_health_score"]
    by_email = {row[1]: row for row in rows[1:]}
    assert by_email["ayesha@shop.test"][2] == "yes"
    assert by_email["ayesha@shop.test"][4] == "shop.test"
    assert by_email["ayesha@shop.test"][5] == "42"
    assert by_email["x@y.test"][0].startswith("'=")  # formula neutralised


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("=1+1", "'=1+1"),
        ("+44 20", "'+44 20"),
        ("-x", "'-x"),
        ("@sum", "'@sum"),
        ("Ayesha", "Ayesha"),
        (None, ""),
    ],
)
def test_safe_cell(value: str | None, expected: str) -> None:
    assert safe_cell(value) == expected
