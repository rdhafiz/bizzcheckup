"""The Check base class every check inherits from.

Example:

    class SingleH1(Check):
        id = "seo.single_h1"
        category = Category.SEO
        title = "One main heading"
        weight = 5

        def run(self, ctx: AuditContext) -> list[Finding]:
            count = len(ctx.tree(ctx.homepage).css("h1"))
            if count == 1:
                return [self.passed("Your homepage has exactly one main heading.", WHY)]
            return [self.finding(Severity.WARN, f"Found {count} main headings.", WHY, FIX)]
"""

import inspect
from abc import ABC, abstractmethod
from collections.abc import Iterable
from typing import Any, ClassVar

from ..context import AuditContext
from ..registry import default_registry
from ..scoring import severity_score
from ..types import Category, Finding, Level, Severity, Snippet


class Check(ABC):
    id: ClassVar[str]  # unique, "<category>.<name>", e.g. "seo.single_h1"
    category: ClassVar[Category]
    title: ClassVar[str]  # short name shown in the report
    weight: ClassVar[int] = 5  # 1-10: importance within its category
    requires: ClassVar[frozenset[str]] = frozenset()  # e.g. frozenset({RENDER})

    # A check can set this in run() for partial credit, e.g. 0.9 when 9 of 10
    # pages are fine. Left as None, the score comes from the worst finding.
    partial: float | None = None

    def __init_subclass__(cls, register: bool = True, **kwargs: Any) -> None:
        """Runs automatically whenever a subclass is defined: registers it.

        `class MyCheck(Check, register=False)` opts out (used in tests).
        Abstract helper classes (with unimplemented methods) are never registered.
        """
        super().__init_subclass__(**kwargs)
        if register and not inspect.isabstract(cls):
            default_registry.register(cls)

    @abstractmethod
    def run(self, ctx: AuditContext) -> list[Finding]:
        """Inspect the context and return findings (at least one)."""

    def score(self, findings: list[Finding]) -> float:
        """0.0-1.0: `partial` if run() set it, otherwise based on the worst finding."""
        if self.partial is not None:
            return self.partial
        return severity_score(findings)

    # --- helpers so checks stay short -------------------------------------------

    def finding(
        self,
        severity: Severity,
        message: str,
        why_it_matters: str,
        how_to_fix: str,
        *,
        effort: Level = Level.LOW,
        impact: Level = Level.MEDIUM,
        urls: Iterable[str] = (),
        snippets: Iterable[Snippet] = (),
    ) -> Finding:
        return Finding(
            check_id=self.id,
            category=self.category,
            severity=severity,
            message=message,
            why_it_matters=why_it_matters,
            how_to_fix=how_to_fix,
            effort=effort,
            impact=impact,
            affected_urls=list(urls),
            snippets=list(snippets),
        )

    def passed(self, message: str, why_it_matters: str, urls: Iterable[str] = ()) -> Finding:
        return self.finding(
            Severity.PASS,
            message,
            why_it_matters,
            "Nothing to do. Keep it this way.",
            effort=Level.LOW,
            impact=Level.LOW,
            urls=urls,
        )
