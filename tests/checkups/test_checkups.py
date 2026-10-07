"""Check-up models, services, the Celery task and the status flow."""

from collections.abc import Awaitable, Callable
from typing import Any
from unittest.mock import patch

import pytest
from pytest_django.fixtures import Settings

from bizzcheckup.checkups import services, tasks
from bizzcheckup.checkups.models import Checkup, Finding
from bizzcheckup.checkups.progress import steps_for
from bizzcheckup.engine.runner import AuditError
from bizzcheckup.engine.types import AuditReport, Band, Category
from bizzcheckup.engine.urls import InvalidURLError

pytestmark = pytest.mark.django_db

Progress = Callable[[int, str], Awaitable[None]]


def fake_engine(report: AuditReport | None = None, error: Exception | None = None):  # type: ignore[no-untyped-def]
    """Replaces engine.run_audit: reports progress twice, then returns or raises."""

    async def run_audit(url: str, config: object, *, on_progress: Progress, **kwargs: object):  # type: ignore[no-untyped-def]
        await on_progress(5, "Visiting your website")
        checkup = await Checkup.objects.aget(url=url)
        assert checkup.status == Checkup.Status.RUNNING  # status flow: queued -> running
        await on_progress(60, "Checking Best practices")
        if error:
            raise error
        return report

    return run_audit


def test_create_checkup_normalises_url_and_queues_job(django_capture_on_commit_callbacks) -> None:  # type: ignore[no-untyped-def]
    with (
        patch.object(tasks.run_checkup, "delay") as delay,
        django_capture_on_commit_callbacks(execute=True),
    ):
        checkup = services.create_checkup("Shop.TEST/about#team", ip_hash="abc")

    assert checkup.url == "https://shop.test/about"
    assert checkup.domain == "shop.test"
    assert checkup.status == Checkup.Status.QUEUED
    delay.assert_called_once_with(str(checkup.pk))


def test_queue_down_fails_checkup_politely(django_capture_on_commit_callbacks) -> None:  # type: ignore[no-untyped-def]
    with (
        patch.object(tasks.run_checkup, "delay", side_effect=ConnectionError("redis down")),
        django_capture_on_commit_callbacks(execute=True),
    ):
        checkup = services.create_checkup("shop.test")

    checkup.refresh_from_db()
    assert checkup.status == Checkup.Status.FAILED
    assert checkup.error_message == services.QUEUE_DOWN_ERROR


def test_create_checkup_rejects_bad_urls() -> None:
    with pytest.raises(InvalidURLError):
        services.create_checkup("ftp://shop.test")


def test_task_runs_audit_and_saves_report(report: AuditReport) -> None:
    checkup = Checkup.objects.create(url="https://shop.test/", domain="shop.test")

    with patch.object(tasks, "run_audit", fake_engine(report)):
        tasks.run_checkup(str(checkup.pk))

    checkup.refresh_from_db()
    assert checkup.status == Checkup.Status.DONE
    assert checkup.progress == 100
    assert checkup.started_at is not None
    assert checkup.finished_at is not None
    assert checkup.health_score == 66
    assert checkup.health_band is Band.ATTENTION
    assert checkup.score_performance is None
    assert checkup.category_score(Category.SEO) == 48
    assert checkup.screenshot is not None
    assert bytes(checkup.screenshot) == b"\xff\xd8fake-jpeg"
    assert checkup.raw_results["health_score"] == 66
    assert "screenshot_jpeg" not in checkup.raw_results  # kept out of the JSON
    assert list(checkup.findings.values_list("check_id", "severity")) == [
        ("seo.sitemap", "pass"),
        ("seo.title", "fail"),
    ]


def test_task_records_progress(report: AuditReport) -> None:
    checkup = Checkup.objects.create(url="https://shop.test/", domain="shop.test")
    seen: list[tuple[int, str]] = []

    async def run_audit(
        url: str, config: object, *, on_progress: Progress, **kw: object
    ) -> AuditReport:
        await on_progress(60, "Checking Best practices")
        row = await Checkup.objects.aget(pk=checkup.pk)
        seen.append((row.progress, row.current_step))
        return report

    with patch.object(tasks, "run_audit", run_audit):
        tasks.run_checkup(str(checkup.pk))

    assert seen == [(60, "Checking Best practices")]


def test_task_shows_friendly_engine_errors() -> None:
    checkup = Checkup.objects.create(url="https://shop.test/", domain="shop.test")
    error = AuditError("We couldn't reach your website.")

    with patch.object(tasks, "run_audit", fake_engine(error=error)):
        tasks.run_checkup(str(checkup.pk))

    checkup.refresh_from_db()
    assert checkup.status == Checkup.Status.FAILED
    assert checkup.error_message == "We couldn't reach your website."
    assert checkup.finished_at is not None


def test_task_hides_unexpected_crashes_from_visitors() -> None:
    checkup = Checkup.objects.create(url="https://shop.test/", domain="shop.test")

    with patch.object(tasks, "run_audit", fake_engine(error=KeyError("internal detail"))):
        tasks.run_checkup(str(checkup.pk))

    checkup.refresh_from_db()
    assert checkup.status == Checkup.Status.FAILED
    assert "internal detail" not in checkup.error_message
    assert checkup.error_message == tasks.GENERIC_ERROR


def test_task_ignores_checkups_that_are_not_queued(report: AuditReport) -> None:
    checkup = Checkup.objects.create(
        url="https://shop.test/", domain="shop.test", status=Checkup.Status.DONE
    )
    with patch.object(tasks, "run_audit", fake_engine(report)) as engine:
        tasks.run_checkup(str(checkup.pk))
    assert engine is not None
    assert Finding.objects.count() == 0  # nothing was run again


def test_engine_config_comes_from_settings(settings) -> None:  # type: ignore[no-untyped-def]
    settings.PSI_API_KEY = "k"
    settings.CHECKUP_MAX_PAGES = 4
    config = services.engine_config()
    assert (config.psi_api_key, config.max_pages) == ("k", 4)


@pytest.mark.parametrize(
    ("progress", "states"),
    [
        (0, ["active"] + ["pending"] * 7),
        (25, ["done", "active"] + ["pending"] * 6),
        (60, ["done"] * 4 + ["active"] + ["pending"] * 3),
        (95, ["done"] * 7 + ["active"]),
        (100, ["done"] * 8),
    ],
)
def test_progress_steps(progress: int, states: list[str]) -> None:
    assert [step.state for step in steps_for(progress)] == states


def test_immediate_runner_starts_the_checkup_right_away(
    settings: Settings,
    django_capture_on_commit_callbacks: Any,
) -> None:
    settings.CHECKUP_RUNNER = "immediate"
    with (
        patch.object(services, "run_in_background_thread") as thread,
        patch.object(tasks.run_checkup, "delay") as delay,
        django_capture_on_commit_callbacks(execute=True),
    ):
        checkup = services.create_checkup("shop.test")

    thread.assert_called_once_with(str(checkup.pk))
    delay.assert_not_called()  # no Redis, no Celery


def test_celery_runner_uses_the_queue(
    settings: Settings,
    django_capture_on_commit_callbacks: Any,
) -> None:
    settings.CHECKUP_RUNNER = "celery"
    with (
        patch.object(services, "run_in_background_thread") as thread,
        patch.object(tasks.run_checkup, "delay") as delay,
        django_capture_on_commit_callbacks(execute=True),
    ):
        services.create_checkup("shop.test")

    delay.assert_called_once()
    thread.assert_not_called()


def test_immediate_runner_limits_how_many_run_at_once(settings: Settings) -> None:
    import threading
    import time

    settings.CHECKUP_MAX_CONCURRENT = 2
    services._slots = None  # start with fresh slots for this test
    running = 0
    most = 0
    done = 0
    lock = threading.Lock()
    all_done = threading.Event()

    def fake_task(pk: str) -> None:
        nonlocal running, most, done
        with lock:
            running += 1
            most = max(most, running)
        time.sleep(0.2)  # pretend to audit a website
        with lock:
            running -= 1
            done += 1
            if done == 5:
                all_done.set()

    with patch.object(tasks, "run_checkup", side_effect=fake_task):
        for number in range(5):
            services.run_in_background_thread(str(number))
        assert all_done.wait(timeout=10)

    services._slots = None
    assert most == 2  # never more than 2 at the same time, and all 5 finished


def test_stuck_checkup_is_failed_instead_of_spinning_forever(settings: Settings) -> None:
    from datetime import timedelta

    from django.utils import timezone

    checkup = Checkup.objects.create(url="https://a.test/", domain="a.test", status="running")
    Checkup.objects.filter(pk=checkup.pk).update(
        created_at=timezone.now() - timedelta(seconds=settings.CHECKUP_TIMEOUT_SECONDS + 300)
    )
    checkup.refresh_from_db()

    services.expire_if_stuck(checkup)

    checkup.refresh_from_db()
    assert checkup.status == Checkup.Status.FAILED
    assert checkup.error_message == services.STUCK_ERROR


def test_recent_running_checkup_is_left_alone() -> None:
    checkup = Checkup.objects.create(url="https://a.test/", domain="a.test", status="running")
    services.expire_if_stuck(checkup)
    checkup.refresh_from_db()
    assert checkup.status == Checkup.Status.RUNNING


def test_background_thread_runs_the_worker_task() -> None:
    import threading

    done = threading.Event()
    with patch.object(tasks, "run_checkup", side_effect=lambda pk: done.set()) as task:
        services.run_in_background_thread("abc")
        assert done.wait(timeout=5)
    task.assert_called_once_with("abc")
