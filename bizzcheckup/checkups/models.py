"""Database tables for check-ups (MODEL layer). Explained in docs/07-database.md."""

import uuid

from django.db import models

from bizzcheckup.engine.scoring import band_for
from bizzcheckup.engine.types import Band, Category, Level, Severity


def choices(enum: type[Category] | type[Severity] | type[Level]) -> list[tuple[str, str]]:
    """Turn an engine enum into Django choices: [("seo", "Seo"), ...]."""
    return [(member.value, member.value.replace("_", " ").capitalize()) for member in enum]


class Lead(models.Model):
    """A visitor who left their name/email and agreed to be contacted."""

    name = models.CharField(max_length=120, blank=True)
    email = models.EmailField()
    consent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.name} <{self.email}>" if self.name else self.email


class Checkup(models.Model):
    """One health check-up of one website."""

    class Status(models.TextChoices):
        QUEUED = "queued", "Queued"
        RUNNING = "running", "Running"
        DONE = "done", "Done"
        FAILED = "failed", "Failed"

    # An unguessable id: the share link /checkups/<id>/ is the only way to see a report.
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    url = models.URLField(max_length=2048)  # normalised, e.g. https://shop.com/
    domain = models.CharField(max_length=253, db_index=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.QUEUED)
    progress = models.PositiveSmallIntegerField(default=0)  # 0-100
    current_step = models.CharField(max_length=100, default="Waiting to start")

    # 0-100 per vital sign; empty = "not checked".
    score_performance = models.PositiveSmallIntegerField(null=True, blank=True)
    score_accessibility = models.PositiveSmallIntegerField(null=True, blank=True)
    score_best_practices = models.PositiveSmallIntegerField(null=True, blank=True)
    score_seo = models.PositiveSmallIntegerField(null=True, blank=True)
    score_agentic = models.PositiveSmallIntegerField(null=True, blank=True)
    health_score = models.PositiveSmallIntegerField(null=True, blank=True)

    error_message = models.TextField(blank=True)  # friendly text shown to the visitor
    ip_hash = models.CharField(max_length=64, blank=True, db_index=True)  # never the raw IP
    lead = models.ForeignKey(
        Lead, null=True, blank=True, on_delete=models.SET_NULL, related_name="checkups"
    )
    raw_results = models.JSONField(default=dict, blank=True)  # the full engine AuditReport
    # Homepage screenshot (JPEG). Kept in the database so the web and worker
    # containers don't need a shared disk.
    screenshot = models.BinaryField(null=True, blank=True, editable=False)
    # The PDF version of the report, made by the worker right after the check-up.
    pdf = models.BinaryField(null=True, blank=True, editable=False)

    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            # "Was this URL checked in the last 24 hours?" (report reuse)
            models.Index(fields=["url", "status", "created_at"], name="checkup_reuse_idx"),
            # "How many check-ups did this IP start in the last hour?" (rate limit)
            models.Index(fields=["ip_hash", "created_at"], name="checkup_ip_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.domain} ({self.get_status_display()})"

    @property
    def is_finished(self) -> bool:
        return self.status in (self.Status.DONE, self.Status.FAILED)

    @property
    def health_band(self) -> Band | None:
        return band_for(self.health_score)

    def category_score(self, category: Category) -> int | None:
        value: int | None = getattr(self, f"score_{category.value}")
        return value


class CheckupImage(models.Model):
    """A picture that belongs to a report, other than the homepage screenshot."""

    class Kind(models.TextChoices):
        LINK_PREVIEW = "link_preview", "Link preview picture"
        MOBILE = "mobile", "Phone screenshot"
        TABLET = "tablet", "Tablet screenshot"

    # Only real pictures are stored (checked from their first bytes, never SVG).
    ALLOWED_TYPES = ("image/jpeg", "image/png", "image/gif", "image/webp")

    checkup = models.ForeignKey(Checkup, on_delete=models.CASCADE, related_name="images")
    kind = models.CharField(max_length=20, choices=Kind.choices)
    content_type = models.CharField(max_length=20)
    data = models.BinaryField(editable=False)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["checkup", "kind"], name="one_image_per_kind")
        ]

    def __str__(self) -> str:
        return f"{self.checkup_id} {self.kind}"


class Finding(models.Model):
    """One result of one check, copied from the report for searching and filtering."""

    checkup = models.ForeignKey(Checkup, on_delete=models.CASCADE, related_name="findings")
    check_id = models.CharField(max_length=80, db_index=True)
    category = models.CharField(max_length=20, choices=choices(Category))
    severity = models.CharField(max_length=10, choices=choices(Severity))
    message = models.TextField()
    why_it_matters = models.TextField()
    how_to_fix = models.TextField()
    effort = models.CharField(max_length=10, choices=choices(Level))
    impact = models.CharField(max_length=10, choices=choices(Level))
    affected_urls = models.JSONField(default=list, blank=True)
    # Ready-made fixes, e.g. the JSON-LD a page should have: [{"title", "code", "language"}].
    snippets = models.JSONField(default=list, blank=True)

    class Meta:
        ordering = ["checkup", "category", "check_id"]
        indexes = [models.Index(fields=["checkup", "category"], name="finding_category_idx")]

    def __str__(self) -> str:
        return f"[{self.severity}] {self.check_id}"
