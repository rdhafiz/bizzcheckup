"""The engine must stay independent of Django (acceptance checklist item)."""

import ast
from pathlib import Path

import bizzcheckup.engine

ENGINE_DIR = Path(bizzcheckup.engine.__file__).parent


def imported_modules(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            names.add(node.module)
    return names


def test_engine_never_imports_django() -> None:
    offenders = {
        str(path.relative_to(ENGINE_DIR)): sorted(
            m for m in imported_modules(path) if m.split(".")[0] in {"django", "celery"}
        )
        for path in ENGINE_DIR.rglob("*.py")
    }
    assert {file: mods for file, mods in offenders.items() if mods} == {}
