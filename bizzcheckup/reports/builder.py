"""Turn a finished check-up into everything the report sections show.

Plain Python, no HTML: templates only display what this module prepares, so the
web report and the PDF are always identical, and the logic is easy to test.
"""

from dataclasses import dataclass, field

import segno

from bizzcheckup.checkups.models import Checkup
from bizzcheckup.engine.scoring import CATEGORY_WEIGHTS, HEALTHY_FROM
from bizzcheckup.engine.treatment import TreatmentPlan, build_treatment_plan
from bizzcheckup.engine.types import AuditReport, Band, Category, CategoryScore, Finding, Severity

from .branding import Branding, Service, load_branding

SEVERITY_ORDER = {Severity.FAIL: 0, Severity.WARN: 1, Severity.INFO: 2, Severity.PASS: 3}
IMPACT_ORDER = {"high": 0, "medium": 1, "low": 2}

# What each vital sign means, in one sentence for business owners.
CATEGORY_INTROS = {
    Category.PERFORMANCE: "How quickly your pages load and respond, especially on phones.",
    Category.ACCESSIBILITY: (
        "Whether everyone, including people with disabilities, can use your site."
    ),
    Category.BEST_PRACTICES: (
        "Security and modern standards that protect your visitors and reputation."
    ),
    Category.SEO: "Whether Google can find, understand and show your pages.",
    Category.AGENTIC: "Whether AI assistants like ChatGPT can read and recommend your business.",
}


@dataclass
class VitalSign:
    category: Category
    score: CategoryScore
    intro: str
    problems: list[Finding]  # fail / warn, most serious first
    notes: list[Finding]  # info
    healthy: list[Finding]  # pass

    @property
    def label(self) -> str:
        return self.category.label

    @property
    def needs_care(self) -> bool:
        return self.score.score is not None and self.score.score < HEALTHY_FROM

    @property
    def anchor(self) -> str:
        """id of this vital sign's section, for jump links ("sign-best_practices")."""
        return f"sign-{self.category.value}"

    @property
    def serious(self) -> int:
        return sum(1 for f in self.problems if f.severity is Severity.FAIL)

    @property
    def headline(self) -> str:
        """One short sentence under the score, in plain words."""
        if self.score.score is None:
            return "Not checked this time."
        if not self.problems:
            return "Healthy: nothing to fix here."
        count = len(self.problems)
        issues = "1 issue" if count == 1 else f"{count} issues"
        if self.serious:
            serious = "1 needs" if self.serious == 1 else f"{self.serious} need"
            return f"{issues} found; {serious} treatment."
        return f"{issues} worth fixing."


@dataclass
class Recommendation:
    """One failing area mapped to one service."""

    category: Category
    score: int | None
    service: Service


@dataclass
class ReportView:
    checkup: Checkup
    report: AuditReport
    branding: Branding
    vital_signs: list[VitalSign]
    top_risks: list[Finding]
    plan: TreatmentPlan
    recommendations: list[Recommendation]
    extra_services: list[Service] = field(default_factory=list)
    qr_svg: str = ""
    image_kinds: set[str] = field(default_factory=set)  # pictures saved, e.g. {"mobile"}

    @property
    def band(self) -> Band | None:
        return self.report.health_band

    # --- counts for the overview tiles -------------------------------------------------
    @property
    def needs_treatment(self) -> int:
        return sum(1 for f in self.plan.all if f.severity is Severity.FAIL)

    @property
    def worth_fixing(self) -> int:
        return sum(1 for f in self.plan.all if f.severity is Severity.WARN)

    @property
    def healthy_count(self) -> int:
        return sum(len(sign.healthy) for sign in self.vital_signs)

    @property
    def verdict(self) -> str:
        """The one sentence a business owner should remember."""
        serious, total = self.needs_treatment, len(self.plan.all)
        if self.band is Band.HEALTHY:
            if not total:
                return "Your website is in excellent health."
            return "Your website is in good health, with a few things worth polishing."
        if self.band is Band.URGENT:
            problems = "1 serious problem is" if serious == 1 else f"{serious} serious problems are"
            return f"Your website needs urgent care: {problems} likely costing you customers."
        if serious:
            problems = "1 serious problem is" if serious == 1 else f"{serious} serious problems are"
            return f"Your website works, but {problems} holding your business back."
        return f"Your website works, but {total} issues are holding your business back."

    # --- device screenshots -------------------------------------------------------------
    @property
    def has_tablet(self) -> bool:
        return "tablet" in self.image_kinds

    @property
    def has_phone(self) -> bool:
        return "mobile" in self.image_kinds

    # --- "Pages we found" ------------------------------------------------------------
    @property
    def all_pages(self) -> list[tuple[str, bool]]:
        """Every page address we came across, and whether it was checked."""
        checked = set(self.report.pages)
        found = self.report.discovered_pages or self.report.pages
        rows = [(url, url in checked) for url in found]
        return sorted(rows, key=lambda row: not row[1])  # checked ones first, order kept

    @property
    def unchecked_count(self) -> int:
        return sum(1 for _, checked in self.all_pages if not checked)

    @property
    def problem_categories(self) -> list[VitalSign]:
        """Vital signs that have something to fix, for the overview."""
        return [sign for sign in self.vital_signs if sign.problems]


def build_report(checkup: Checkup) -> ReportView:
    report = AuditReport.model_validate(checkup.raw_results)
    branding = load_branding()
    vital_signs = [vital_sign(report, category) for category in Category]
    plan = build_treatment_plan(report.findings)
    recommendations, extra = recommend_services(branding, vital_signs)
    return ReportView(
        checkup=checkup,
        report=report,
        branding=branding,
        vital_signs=vital_signs,
        top_risks=top_risks(report.findings),
        plan=plan,
        recommendations=recommendations,
        extra_services=extra,
        qr_svg=qr_code_svg(str(branding.qr_target)) if branding.qr_target else "",
        image_kinds=set(checkup.images.values_list("kind", flat=True)),
    )


def vital_sign(report: AuditReport, category: Category) -> VitalSign:
    findings = [f for f in report.findings if f.category is category]
    problems = sorted(
        (f for f in findings if f.severity in (Severity.FAIL, Severity.WARN)),
        key=lambda f: (SEVERITY_ORDER[f.severity], IMPACT_ORDER[f.impact.value]),
    )
    return VitalSign(
        category=category,
        score=report.category(category),
        intro=CATEGORY_INTROS[category],
        problems=problems,
        notes=[f for f in findings if f.severity is Severity.INFO],
        healthy=[f for f in findings if f.severity is Severity.PASS],
    )


def top_risks(findings: list[Finding], count: int = 3) -> list[Finding]:
    """The problems that hurt the business most: high impact first, failures first."""
    problems = [f for f in findings if f.severity in (Severity.FAIL, Severity.WARN)]
    problems.sort(
        key=lambda f: (
            IMPACT_ORDER[f.impact.value],
            SEVERITY_ORDER[f.severity],
            -CATEGORY_WEIGHTS[f.category],
        )
    )
    return problems[:count]


def recommend_services(
    branding: Branding, signs: list[VitalSign]
) -> tuple[list[Recommendation], list[Service]]:
    """Map each area that needs care to its most specific service.

    When three or more areas need care, the broadest service (e.g. a full rebuild)
    is suggested as well.
    """
    recommendations = []
    for sign in signs:
        if not sign.needs_care:
            continue
        services = branding.services_for(sign.category)
        if services:
            recommendations.append(Recommendation(sign.category, sign.score.score, services[0]))

    extra: list[Service] = []
    if len(recommendations) >= 3 and branding.services:
        broadest = max(branding.services, key=lambda s: len(s.related_categories))
        if all(r.service is not broadest for r in recommendations):
            extra.append(broadest)
    return recommendations, extra


def qr_code_svg(target: str) -> str:
    """An inline <svg> QR code that scans to `target` (no external image needed)."""
    qr = segno.make(target, error="m")
    svg: str = qr.svg_inline(scale=4, dark="#0e1b1e", light="#ffffff", border=2)
    return svg
