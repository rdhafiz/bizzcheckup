from abc import abstractmethod

import pytest

from bizzcheckup.engine.checks import base as checks_base
from bizzcheckup.engine.checks.base import Check
from bizzcheckup.engine.context import AuditContext
from bizzcheckup.engine.registry import Registry, load_builtin_checks
from bizzcheckup.engine.types import Category, Finding, Level, Severity


@pytest.fixture
def fresh_registry(monkeypatch: pytest.MonkeyPatch) -> Registry:
    """Swap in an empty registry so test classes don't leak into the real one."""
    registry = Registry()
    monkeypatch.setattr(checks_base, "default_registry", registry)
    return registry


def test_defining_a_check_registers_it(fresh_registry: Registry) -> None:
    class TitleCheck(Check):
        id = "seo.test_title"
        category = Category.SEO
        title = "Title"

        def run(self, ctx: AuditContext) -> list[Finding]:
            return []

    assert "seo.test_title" in fresh_registry
    assert fresh_registry.all() == [TitleCheck]


def test_abstract_helpers_and_opt_outs_are_not_registered(fresh_registry: Registry) -> None:
    class HelperBase(Check):  # still abstract: run() not implemented
        @abstractmethod
        def extra(self) -> None: ...

    class TestOnly(Check, register=False):
        id = "seo.test_only"
        category = Category.SEO
        title = "Test only"

        def run(self, ctx: AuditContext) -> list[Finding]:
            return []

    assert len(fresh_registry) == 0


def test_duplicate_ids_are_rejected(fresh_registry: Registry) -> None:
    class First(Check):
        id = "seo.dup"
        category = Category.SEO
        title = "First"

        def run(self, ctx: AuditContext) -> list[Finding]:
            return []

    with pytest.raises(ValueError, match="Two checks use the id"):

        class Second(Check):
            id = "seo.dup"
            category = Category.SEO
            title = "Second"

            def run(self, ctx: AuditContext) -> list[Finding]:
                return []


def test_missing_attributes_and_bad_weight_are_rejected(fresh_registry: Registry) -> None:
    with pytest.raises(TypeError, match="must define 'title'"):

        class NoTitle(Check):
            id = "seo.no_title"
            category = Category.SEO

            def run(self, ctx: AuditContext) -> list[Finding]:
                return []

    with pytest.raises(ValueError, match="weight"):

        class TooHeavy(Check):
            id = "seo.heavy"
            category = Category.SEO
            title = "Heavy"
            weight = 11

            def run(self, ctx: AuditContext) -> list[Finding]:
                return []


def test_all_is_sorted_by_category_order_then_id() -> None:
    registry = Registry()

    def make(check_id: str, category: Category) -> type[Check]:
        def run(self: Check, ctx: AuditContext) -> list[Finding]:
            return []

        attrs = {"id": check_id, "category": category, "title": check_id, "run": run}
        return type(check_id, (Check,), attrs, register=False)

    seo_b, perf, seo_a = (
        make("seo.b", Category.SEO),
        make("perf.a", Category.PERFORMANCE),
        make("seo.a", Category.SEO),
    )
    for check in (seo_b, perf, seo_a):
        registry.register(check)

    assert registry.all() == [perf, seo_a, seo_b]


def test_helpers_fill_in_check_id_and_category() -> None:
    class Example(Check, register=False):
        id = "agentic.example"
        category = Category.AGENTIC
        title = "Example"

        def run(self, ctx: AuditContext) -> list[Finding]:
            return []

    check = Example()
    problem = check.finding(Severity.WARN, "Msg", "Why", "Fix", impact=Level.HIGH, urls=["u"])
    ok = check.passed("All good", "Why")

    assert (problem.check_id, problem.category) == ("agentic.example", Category.AGENTIC)
    assert problem.affected_urls == ["u"]
    assert ok.severity is Severity.PASS
    assert check.score([problem, ok]) == 0.5


def test_load_builtin_checks_imports_the_checks_package() -> None:
    registry = load_builtin_checks()
    assert isinstance(registry, Registry)
