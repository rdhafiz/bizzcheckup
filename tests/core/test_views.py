from django.test import Client
from django.urls import reverse
from pytest_django.fixtures import Settings

from bizzcheckup.core.tasks import ping


def test_home_shows_brand_name_and_tagline(client: Client) -> None:
    response = client.get(reverse("core:home"))

    assert response.status_code == 200
    html = response.content.decode()
    assert "<title>BizzCheckup — Check your business&#x27;s online health</title>" in html


def test_healthz_returns_ok(client: Client) -> None:
    response = client.get(reverse("core:healthz"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_styleguide_hidden_when_debug_off(client: Client) -> None:
    assert client.get(reverse("core:styleguide")).status_code == 404


def test_styleguide_visible_when_debug_on(client: Client, settings: Settings) -> None:
    settings.DEBUG = True
    assert client.get(reverse("core:styleguide")).status_code == 200


def test_ping_task_runs() -> None:
    assert ping.delay().get() == "pong"
