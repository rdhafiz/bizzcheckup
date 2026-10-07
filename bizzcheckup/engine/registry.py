"""Keeps the list of all checks.

Checks add themselves: defining `class MyCheck(Check): ...` is enough (see
Check.__init_subclass__ in checks/base.py). `load_builtin_checks()` imports
every module in the `checks` package so all those classes get defined.
"""

from __future__ import annotations  # lets type hints name Check without importing it at runtime

import importlib
import pkgutil
from typing import TYPE_CHECKING

from .types import Category

if TYPE_CHECKING:  # only for type hints; avoids a circular import at runtime
    from .checks.base import Check

CATEGORY_ORDER = list(Category)


class Registry:
    def __init__(self) -> None:
        self._checks: dict[str, type[Check]] = {}

    def register(self, check: type[Check]) -> None:
        for attribute in ("id", "category", "title"):
            if not getattr(check, attribute, None):
                raise TypeError(f"{check.__name__} must define '{attribute}'.")
        if not isinstance(check.category, Category):
            raise TypeError(f"{check.__name__}.category must be a Category.")
        if not 1 <= check.weight <= 10:
            raise ValueError(f"{check.__name__}.weight must be between 1 and 10.")
        existing = self._checks.get(check.id)
        if existing is not None and existing is not check:
            raise ValueError(
                f"Two checks use the id {check.id!r}: {existing.__name__}, {check.__name__}."
            )
        self._checks[check.id] = check

    def all(self) -> list[type[Check]]:
        """Every check, grouped by category in report order, then by id."""
        return sorted(self._checks.values(), key=lambda c: (CATEGORY_ORDER.index(c.category), c.id))

    def __contains__(self, check_id: object) -> bool:
        return check_id in self._checks

    def __len__(self) -> int:
        return len(self._checks)


default_registry = Registry()


def load_builtin_checks() -> Registry:
    """Import every module in bizzcheckup.engine.checks, registering their checks."""
    from . import checks

    for module in pkgutil.iter_modules(checks.__path__):
        importlib.import_module(f"{checks.__name__}.{module.name}")
    return default_registry
