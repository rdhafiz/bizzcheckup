"""python manage.py run_rechecks: run the monthly re-checks that are due, then exit.

With CHECKUP_RUNNER=celery, Celery Beat already does this every 6 hours (docs/12). Without
Celery ("immediate" mode), run this command from a daily scheduled task instead (cron on
Linux, Task Scheduler on Windows). It runs the check-ups one by one, in this process, so
they finish before the command exits.
"""

from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand, CommandParser

from bizzcheckup.checkups import services, tasks


class Command(BaseCommand):
    help = "Run the monthly re-checks that are due and email what changed."

    def add_arguments(self, parser: CommandParser) -> None:
        parser.add_argument(
            "--limit",
            type=int,
            default=settings.RECHECKS_PER_RUN,
            help="The most re-checks to run this time (default: RECHECKS_PER_RUN).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        checkups = services.start_due_rechecks(options["limit"], start=False)
        for checkup in checkups:
            self.stdout.write(f"Checking {checkup.domain}...")
            tasks.run_checkup(str(checkup.pk))  # runs here and now, not in the background
            checkup.refresh_from_db()
            self.stdout.write(f"  {checkup.get_status_display()}: {checkup.health_score}")
        self.stdout.write(self.style.SUCCESS(f"{len(checkups)} re-check(s) done."))
