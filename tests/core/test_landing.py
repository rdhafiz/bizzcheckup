"""Landing page, lead capture, consent and the privacy note."""

from collections.abc import Iterator
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from bizzcheckup.checkups import tasks
from bizzcheckup.checkups.models import Checkup, Lead
from bizzcheckup.engine.registry import load_builtin_checks

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def no_real_queue() -> Iterator[None]:
    with patch.object(tasks.run_checkup, "delay"):
        yield


def submit(client: Client, **fields: str):  # type: ignore[no-untyped-def]
    data = {"url": "shop.test", "consent": "on", **fields}
    return client.post(reverse("checkups:start"), {k: v for k, v in data.items() if v is not None})


def test_landing_page_shows_brand_and_everything_the_brief_asks_for(client: Client) -> None:
    html = client.get("/").content.decode()

    assert "<title>BizzCheckup — Check your business&#x27;s online health</title>" in html
    assert '<span class="sr-only">BizzCheckup: </span>Is your business website' in html
    for name in ('name="url"', 'name="name"', 'name="email"', 'name="consent"'):
        assert name in html
    assert "Start my free check-up" in html
    assert reverse("core:privacy") in html  # privacy note link
    assert html.count('class="sign-card tone-') == 5  # the five vital signs
    # Each sign card, "How it works" and the last section lead to the form.
    assert html.count('href="#start"') == 7
    assert 'id="start"' in html


def test_consent_is_required(client: Client) -> None:
    response = submit(client, consent="")
    assert response.status_code == 400
    assert "Please agree to the privacy note" in response.content.decode()
    assert Checkup.objects.count() == 0


def test_lead_is_saved_with_consent_when_email_given(client: Client) -> None:
    submit(client, name="  Ayesha   Rahman ", email="Ayesha@Example.com")

    lead = Lead.objects.get()
    assert (lead.name, lead.email, lead.consent) == ("Ayesha Rahman", "ayesha@example.com", True)
    assert Checkup.objects.get().lead == lead


def test_no_lead_without_email(client: Client) -> None:
    submit(client, name="Just a name")
    assert Lead.objects.count() == 0
    assert Checkup.objects.get().lead is None


def test_invalid_email_is_rejected(client: Client) -> None:
    response = submit(client, email="not-an-email")
    assert response.status_code == 400
    assert Checkup.objects.count() == 0


def test_lead_is_kept_when_a_recent_report_is_reused(client: Client) -> None:
    earlier = Checkup.objects.create(
        url="https://shop.test/", domain="shop.test", status=Checkup.Status.DONE
    )
    Checkup.objects.filter(pk=earlier.pk).update(created_at=timezone.now() - timedelta(hours=2))

    submit(client, email="owner@shop.test")

    earlier.refresh_from_db()
    assert earlier.lead is not None
    assert earlier.lead.email == "owner@shop.test"


def test_privacy_note(client: Client) -> None:
    html = client.get(reverse("core:privacy")).content.decode()
    assert "Your data, in plain words" in html
    assert "salted hash" in html
    assert "ridwanul.hafiz@gmail.com" in html  # contact from branding.yaml
    assert "Google PageSpeed Insights" in html
    assert "Cloudflare Turnstile" not in html  # only mentioned when it's on


def test_privacy_link_in_every_page_footer(client: Client) -> None:
    assert (
        f'href="{reverse("core:privacy")}"' in client.get(reverse("core:privacy")).content.decode()
    )


def test_how_it_works_steps_use_the_real_numbers(client: Client, settings) -> None:  # type: ignore[no-untyped-def]
    settings.CHECKUP_MAX_PAGES = 12
    html = client.get("/").content.decode()
    checks = len(load_builtin_checks().all())

    assert html.count('class="timeline__step') == 5
    assert html.count('class="step-art"') == 5  # one illustration per step
    assert 'class="how-art"' in html  # and the laptop scene
    assert f"{checks} checks, while you watch" in html  # counted from the engine
    assert "We open up to 12 public pages" in html  # from the settings
    assert "Up to 12 pages" in html
