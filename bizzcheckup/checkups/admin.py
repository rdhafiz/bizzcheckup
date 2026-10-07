"""Django admin: search and filter check-ups, findings and leads; export leads to CSV."""

import csv
from collections.abc import Iterable
from typing import Any

from django.contrib import admin
from django.db.models import Count, QuerySet
from django.http import HttpRequest, HttpResponse
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import SafeString

from bizzcheckup.engine.scoring import band_for

from .models import Checkup, Finding, Lead

# Spreadsheet apps treat a cell starting with these as a formula, which an attacker can
# abuse ("CSV injection"), e.g. a name like =HYPERLINK("http://evil",...).
FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value: object) -> str:
    text = "" if value is None else str(value)
    return f"'{text}" if text.startswith(FORMULA_START) else text


class HealthBandFilter(admin.SimpleListFilter):
    title = "health band"
    parameter_name = "band"

    def lookups(self, request: HttpRequest, model_admin: Any) -> list[tuple[str, str]]:
        return [
            ("urgent", "Needs urgent care (0-49)"),
            ("attention", "Needs attention (50-89)"),
            ("healthy", "Healthy (90-100)"),
        ]

    def queryset(self, request: HttpRequest, queryset: QuerySet[Checkup]) -> QuerySet[Checkup]:
        ranges = {"urgent": (0, 49), "attention": (50, 89), "healthy": (90, 100)}
        if self.value() in ranges:
            low, high = ranges[str(self.value())]
            return queryset.filter(health_score__gte=low, health_score__lte=high)
        return queryset


class FindingInline(admin.TabularInline):
    model = Finding
    fields = ("severity", "category", "check_id", "message", "impact", "effort")
    readonly_fields = fields
    extra = 0
    can_delete = False
    show_change_link = True

    def has_add_permission(self, request: HttpRequest, obj: Any = None) -> bool:
        return False


@admin.register(Checkup)
class CheckupAdmin(admin.ModelAdmin):
    list_display = ("domain", "status", "health", "lead", "created_at", "duration")
    list_filter = ("status", HealthBandFilter, "created_at")
    search_fields = ("url", "domain", "lead__email", "lead__name")
    date_hierarchy = "created_at"
    list_select_related = ("lead",)
    inlines = [FindingInline]
    readonly_fields = (
        "id", "report_link", "url", "domain", "status", "progress", "current_step",
        "health_score", "score_performance", "score_accessibility", "score_best_practices",
        "score_seo", "score_agentic", "error_message", "ip_hash", "screenshot_preview",
        "created_at", "started_at", "finished_at",
    )  # fmt: skip
    exclude = ("raw_results",)  # large; the report link shows it properly

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False  # check-ups start from the website, not from admin

    @admin.display(description="health", ordering="health_score")
    def health(self, obj: Checkup) -> str:
        band = band_for(obj.health_score)
        return f"{obj.health_score} · {band.label}" if band else "-"

    @admin.display(description="took")
    def duration(self, obj: Checkup) -> str:
        if obj.started_at and obj.finished_at:
            return f"{(obj.finished_at - obj.started_at).total_seconds():.0f} s"
        return "-"

    @admin.display(description="report")
    def report_link(self, obj: Checkup) -> SafeString:
        url = reverse("checkups:detail", args=[obj.pk])
        return format_html('<a href="{}" target="_blank" rel="noopener">Open report</a>', url)

    @admin.display(description="screenshot")
    def screenshot_preview(self, obj: Checkup) -> SafeString | str:
        if not obj.screenshot:
            return "-"
        url = reverse("checkups:screenshot", args=[obj.pk])
        return format_html('<img src="{}" width="320" alt="Homepage screenshot">', url)


@admin.register(Finding)
class FindingAdmin(admin.ModelAdmin):
    list_display = ("check_id", "severity", "category", "impact", "effort", "checkup")
    list_filter = ("severity", "category", "impact", "effort")
    search_fields = ("check_id", "message", "checkup__domain")
    list_select_related = ("checkup",)
    readonly_fields = (
        "checkup", "check_id", "category", "severity", "message", "why_it_matters",
        "how_to_fix", "effort", "impact", "affected_urls",
    )  # fmt: skip

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = ("email", "name", "consent", "checkup_count", "created_at")
    list_filter = ("consent", "created_at")
    search_fields = ("email", "name", "checkups__domain")
    date_hierarchy = "created_at"
    actions = ["export_csv"]

    def get_queryset(self, request: HttpRequest) -> QuerySet[Lead]:
        queryset: QuerySet[Lead] = super().get_queryset(request)
        return queryset.annotate(checkup_total=Count("checkups"))

    @admin.display(description="check-ups", ordering="checkup_total")
    def checkup_count(self, obj: Lead) -> int:
        return int(getattr(obj, "checkup_total", 0))

    @admin.action(description="Export selected leads to CSV")
    def export_csv(self, request: HttpRequest, queryset: QuerySet[Lead]) -> HttpResponse:
        return leads_csv(queryset.prefetch_related("checkups"))


def leads_csv(leads: Iterable[Lead]) -> HttpResponse:
    response = HttpResponse(content_type="text/csv; charset=utf-8")
    stamp = timezone.now().strftime("%Y-%m-%d")
    response["Content-Disposition"] = f'attachment; filename="bizzcheckup-leads-{stamp}.csv"'
    response.write("﻿")  # lets Excel detect UTF-8 (names like "Sébastien", "রহমান")
    writer = csv.writer(response)
    writer.writerow(["name", "email", "consent", "created_at", "websites", "latest_health_score"])
    for lead in leads:
        checkups = sorted(lead.checkups.all(), key=lambda c: c.created_at, reverse=True)
        writer.writerow(
            [
                safe_cell(lead.name),
                safe_cell(lead.email),
                "yes" if lead.consent else "no",
                lead.created_at.isoformat(timespec="seconds"),
                safe_cell(" ".join(c.domain for c in checkups)),
                checkups[0].health_score
                if checkups and checkups[0].health_score is not None
                else "",
            ]
        )
    return response
