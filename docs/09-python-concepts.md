# 9. Python Concepts Used

Each Python feature the code uses gets a short explanation here, with the file where
you can see it.

## Modules, packages, `import`

```python
import os                    # the whole module: os.environ
from pathlib import Path     # one name: Path(...)
from . import views          # "." = the package this file is in  (core/urls.py)
from .base import *          # copy every public name  (settings/dev.py)
```

- A **module** is one `.py` file.
- A **package** is a folder with `__init__.py`. `bizzcheckup/` is a package, and so is
  `bizzcheckup/core/`.
- **Import order** (Ruff enforces it): standard library, then third-party, then our
  code, with a blank line between groups.
- `import *` is normally avoided. Settings files are the classic exception, which is
  why they have `# noqa: F403` to tell Ruff "I know".

## Functions and type hints

```python
def home(request: HttpRequest) -> HttpResponse:   # core/views.py
    return render(request, "core/home.html")
```

- `request: HttpRequest` means this parameter should be an `HttpRequest`.
- `-> HttpResponse` means the function returns an `HttpResponse`.
- Python **doesn't enforce** hints at runtime. **mypy** checks them before the code
  runs.
- `-> None` means the function returns nothing (`manage.py::main`).
- `dict[str, str]` is a dictionary with string keys and string values
  (`context_processors.py`).
- `list[str]` is a list of strings (`ALLOWED_HOSTS: list[str]` in `base.py`).

## Docstrings

```python
def healthz(request):
    """Tiny endpoint Docker uses to know the web server is alive."""
```

The first string inside a function, class or module documents it. Editors show it on
hover.

## Decorators: `@something`

```python
@shared_task                 # core/tasks.py
def ping() -> str:
    return "pong"
```

A decorator wraps a function to give it extra powers. `@shared_task` turns `ping` into
a Celery task, so you can call `ping.delay()` to run it in the worker.

## Classes and inheritance

```python
class CoreConfig(AppConfig):          # core/apps.py
    name = "bizzcheckup.core"
```

`CoreConfig` **inherits** from Django's `AppConfig`: it gets all of its behaviour and
only changes `name`. Phase 2 uses this heavily: every check inherits from `Check`.

## `if __name__ == "__main__":`

```python
if __name__ == "__main__":   # manage.py, scripts/get_tailwind.py
    main()
```

`__name__` is `"__main__"` only when you **run** the file directly
(`python manage.py`). If another file imports it, `main()` doesn't run.

## f-strings

```python
f"tailwindcss-windows-{arch}.exe"     # scripts/get_tailwind.py
```

An `f` before the quotes lets `{expression}` insert values.

## `pathlib.Path`

```python
BASE_DIR = Path(__file__).resolve().parent.parent.parent
BASE_DIR / "branding.yaml"     # / joins paths on every OS
```

`__file__` is the path of the current file. `.parent` goes up one folder.

## Conditional expression (one-line if)

```python
arch = "arm64" if machine in ("arm64", "aarch64") else "x64"
```

## Tuples and `in`

`("arm64", "aarch64")` is a **tuple**, an unchangeable list. `x in (...)` checks
membership.

## Exceptions

```python
if not settings.DEBUG:
    raise Http404              # core/views.py: stop here, Django shows "Not found"
```

`raise` stops the function with an error. Django turns `Http404` into a 404 page.

## `sys.exit("message")`

This stops a script and prints the message (`get_tailwind.py`, unsupported OS).
