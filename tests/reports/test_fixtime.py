"""How long fixes take, and who does them."""

import pytest
from django.test import Client
from django.urls import reverse

from bizzcheckup.checkups import services
from bizzcheckup.checkups.models import Checkup
from bizzcheckup.engine.types import Level
from bizzcheckup.reports.fixtime import duration, fix_time, summarise
from tests.checkups.conftest import make_report


@pytest.mark.parametrize(
    ("minutes", "words"),
    [
        (20, "about 20 minutes"),
        (60, "about 1 hour"),
        (150, "about 2 hours"),
        (700, "about 12 hours"),
        (960, "about 2 days"),
        (8 * 60 * 1.6, "about 2 days"),
    ],
)
def test_duration_in_plain_words(minutes: int, words: str) -> None:
    assert duration(int(minutes)) == words


def test_summary_splits_quick_fixes_from_developer_work() -> None:
    finding = make_report().findings[0]
    quick = finding.model_copy(update={"effort": Level.LOW})
    big = finding.model_copy(update={"effort": Level.HIGH})

    summary = summarise([quick, quick, big])

    assert summary.diy_count == 2
    assert summary.developer_minutes == fix_time(big).minutes
    assert summary.total == "about 2 days"
    assert fix_time(quick).do_it_yourself


@pytest.mark.django_db
def test_report_shows_fix_times(client: Client) -> None:
    checkup = Checkup.objects.create(url="https://shop.test/", domain="shop.test")
    services.save_report(checkup, make_report())  # one low-effort problem
    services.mark_done(checkup)

    html = client.get(reverse("checkups:detail", args=[checkup.pk])).content.decode()

    assert "~20 min" in html
    assert "Time: about 20 minutes." in html
    assert "You can usually do this yourself" in html
    assert "about 20 minutes of work" in html
