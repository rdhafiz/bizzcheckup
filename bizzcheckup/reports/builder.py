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
    summary: list[str]  # the three diagnosis sentences
    top_risks: list[Finding]
    plan: TreatmentPlan
    recommendations: list[Recommendation]
    extra_services: list[Service] = field(default_factory=list)
    qr_svg: str = ""

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
        summary=diagnosis_summary(checkup.domain, report, vital_signs, plan),
        top_risks=top_risks(report.findings),
        plan=plan,
        recommendations=recommendations,
        extra_services=extra,
        qr_svg=qr_code_svg(str(branding.qr_target)) if branding.qr_target else "",
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


def diagnosis_summary(
    domain: str, report: AuditReport, signs: list[VitalSign], plan: TreatmentPlan
) -> list[str]:
    """Three plain-English sentences about the overall result."""
    sentences = []
    if report.health_score is not None and report.health_band is not None:
        sentences.append(
            f"{domain} has a Business Health Score of {report.health_score} out of 100: "
            f"{report.health_band.label.lower()}."
        )
    scored = [s for s in signs if s.score.score is not None]
    if scored:
        best = max(scored, key=lambda s: (s.score.score or 0, CATEGORY_WEIGHTS[s.category]))
        worst = min(scored, key=lambda s: (s.score.score or 0, -CATEGORY_WEIGHTS[s.category]))
        if best is worst:
            sentences.append(f"Its {best.label.lower()} scored {best.score.score}.")
        else:
            sentences.append(
                f"Its strongest vital sign is {best.label.lower()} ({best.score.score}); the "
                f"one needing the most care is {worst.label.lower()} ({worst.score.score})."
            )
    serious = sum(1 for f in plan.all if f.severity is Severity.FAIL)
    smaller = len(plan.all) - serious
    pages = len(report.pages)
    page_word = "page" if pages == 1 else "pages"
    if plan.all:
        sentences.append(
            f"We found {serious} serious and {smaller} smaller issues across {pages} {page_word}, "
            f"and {len(plan.quick_wins)} of them are quick wins you can fix soon."
        )
    else:
        sentences.append(f"We found no problems across the {pages} {page_word} we checked.")
    return sentences


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
