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

---

# Phase 2: concepts in the audit engine

## Classes, the deeper parts

### Abstract base classes: `ABC` and `@abstractmethod` (`checks/base.py`)

```python
class Check(ABC):
    @abstractmethod
    def run(self, ctx: AuditContext) -> list[Finding]: ...
```

`Check` is a template. Python refuses to create a `Check()` or any subclass that
hasn't written its own `run()`. Forgetting `run()` fails immediately, not halfway
through an audit.

### Class variables: `ClassVar`

```python
id: ClassVar[str]           # belongs to the class itself, not to each object
weight: ClassVar[int] = 5   # default that subclasses can change
```

The registry reads `SingleH1.id` without creating a `SingleH1` object.

### `__init_subclass__`: code that runs when a subclass is *defined*

```python
def __init_subclass__(cls, register: bool = True, **kwargs: Any) -> None:
    super().__init_subclass__(**kwargs)
    if register and not inspect.isabstract(cls):
        default_registry.register(cls)
```

When Python reads `class SingleH1(Check): ...`, it calls this method with
`cls = SingleH1`. That's how checks "register themselves". Extra words in the class
line become arguments: `class X(Check, register=False)`.

### `@property` and `@cached_property` (`types.py`)

```python
@property
def is_html(self) -> bool:      # used like an attribute: page.is_html (no brackets)
    return self.content_type in ("text/html", "application/xhtml+xml")

@cached_property
def _parser(self) -> RobotFileParser:   # computed on first use, then remembered
    ...
```

### Enums: `StrEnum` (`types.py`)

```python
class Severity(StrEnum):
    PASS = "pass"
    WARN = "warn"

Severity("warn") is Severity.WARN    # True
Severity.WARN == "warn"              # True: it *is* a string, so JSON stays simple
list(Category)                       # all members, in the order written
```

An enum is a fixed set of allowed values. A typo like `Severity.WRAN` is caught
straight away.

### `@dataclass` (`context.py`)

```python
@dataclass
class AuditContext:
    crawl: CrawlResult
    capabilities: set[str] = field(default_factory=set)
```

Python writes `__init__` (and a readable `repr`) for you from the field list.
`field(default_factory=set)` gives every object its **own** new empty set.

> **Why not `capabilities: set[str] = set()`?** That one set would be shared by every
> object, which is a classic Python bug. `default_factory` (and Pydantic's
> `Field(default_factory=list)`) avoids it.

### Pydantic models vs dataclasses

| | `@dataclass` | Pydantic `BaseModel` |
|---|---|---|
| Checks values when created | No | **Yes** (`Finding(severity="oops")` raises an error) |
| Converts types | No | Yes (`"warn"` becomes `Severity.WARN`) |
| To and from JSON | Manual | `model_dump(mode="json")`, `model_validate(data)` |
| We use it for | `AuditContext` (holds parse caches) | Everything that gets saved or validated |

`model_config = ConfigDict(frozen=True)` makes `Finding` read-only after creation.

### Custom exceptions (`netguard.py`, `fetcher.py`, `runner.py`)

```python
class BlockedURLError(Exception):
    """The URL points somewhere BizzCheckup must not connect to."""

class UnusableHomepageError(FetchError):   # a more specific kind of FetchError
    ...
```

`except FetchError` also catches `UnusableHomepageError`, because it inherits from
`FetchError`.

### `raise ... from error`

```python
except TimeoutError as error:
    raise AuditError("Your website took too long...") from error
```

This replaces a technical error with a friendly one, **keeping** the original in the
traceback for debugging.

## Async programming (`fetcher.py`, `crawler.py`, `runner.py`)

Fetching a page means mostly *waiting* for the network. With `async`, Python works on
something else while it waits:

```python
async def fetch_page(fetcher, url):     # "async def" makes a coroutine function
    page = await fetcher.get(url)       # "await" means: pause here until the answer arrives
    return page

pages = await asyncio.gather(*(fetch_page(f, u) for u in urls))   # run many at once
```

| Tool | Where | What it does |
|------|-------|--------------|
| `async def` / `await` | everywhere in the engine | Define and wait for coroutines |
| `asyncio.gather(...)` | `crawler.py` | Run several coroutines at once and collect their results in order |
| `asyncio.Semaphore(2)` | `fetcher.py` | At most 2 inside `async with semaphore:` at a time |
| `asyncio.timeout(180)` | `runner.py` | Cancel everything inside it after 180 seconds and raise `TimeoutError` |
| `asyncio.sleep(0.5)` | `fetcher.py` | Wait without blocking other work (used between retries) |
| `asyncio.run(main())` | Celery task (phase 6) | Start the event loop from normal code |
| `async for chunk in ...` | `fetcher.py` | Loop over data as it arrives (the page body) |

### `async with` and context managers

```python
async with Fetcher(config) as fetcher:   # __aenter__ opens the HTTP client
    page = await fetcher.get(url)
# __aexit__ closes it here, even if an error happened inside
```

`Fetcher` implements `__aenter__` and `__aexit__` to support this. The non-async
version is `with open(...) as f:` (`__enter__` and `__exit__`).

## Type hints, the deeper parts

| Hint | Meaning | Where |
|------|---------|-------|
| `str \| None` | A string or `None` | `absolute()` returns `str \| None` |
| `list[Finding]` | List of `Finding` | `Check.run` |
| `dict[str, list[str]]` | Dictionary of string to list of strings | `FAKE_DNS` in tests |
| `tuple[bool, list[str]]` | Exactly two values: a bool and a list | `parse_sitemap` |
| `type[Check]` | The *class* `Check` (or a subclass), not an object | `Registry.register` |
| `Callable[[int, str], Awaitable[None]]` | An async function taking `(int, str)` | `ProgressCallback` |
| `Self` | "The same class as this one" | `Fetcher.__aenter__` |
| `Iterable[str]` | Anything you can loop over | `Check.finding(urls=...)` |

### `TYPE_CHECKING` and `from __future__ import annotations` (`registry.py`)

`registry.py` needs the name `Check` for type hints. But `checks/base.py` imports
`registry.py`, so importing `Check` back would be a **circular import**. The fix:

```python
from __future__ import annotations   # hints are kept as text, not evaluated
from typing import TYPE_CHECKING

if TYPE_CHECKING:                    # True only for mypy, False when the program runs
    from .checks.base import Check
```

## Functions, the deeper parts

### Keyword-only arguments: the lone `*`

```python
def finding(self, severity, message, why_it_matters, how_to_fix, *, effort=..., impact=...):
```

Everything after `*` **must** be named: `finding(..., impact=Level.HIGH)`. Calls are
self-explanatory and can't mix up `effort` and `impact`.

### `*args`, `**kwargs` and unpacking

```python
def make_context(*pages: Page, ...)       # any number of pages, as a tuple
{"content-type": "text/html", **(headers or {})}   # merge two dicts
{"check_id": ..., **extra}                # add extra keys
```

### Nested functions (closures) (`runner.py`)

```python
async def _run(..., on_progress, ...):
    async def progress(percent: int, step: str) -> None:
        if on_progress is not None:       # uses a variable from the outer function
            await on_progress(percent, step)
```

## Handy built-ins and idioms

```python
[f for f in findings if f.severity in PROBLEMS]        # list comprehension (filter)
{str(info[4][0]) for info in infos}                    # set comprehension: no duplicates
min((score(f) for f in findings), default=1.0)         # generator + default if empty
any(f.severity is Severity.FAIL for f in findings)     # True if at least one matches
next((r.note for r in skipped if r.note), "Not checked.")  # first match, or a default
sorted(checks, key=lambda c: (order.index(c.category), c.id))  # sort by two things
for index, (category, group) in enumerate(groups):     # index + tuple unpacking
groupby(checks, lambda c: c.category)                  # itertools: runs of equal keys
f"{host!r}"                                            # !r = repr(): adds quotes
```

### `is` vs `==`

`severity is Severity.FAIL` checks for the *same object*. That's the recommended way
to compare enum members and `None`. Use `==` to compare values (`score == 100`).

### `try / except / else / finally` (`fetcher.py`)

```python
try:
    response = await client.send(request)
except httpx.TransportError:     # runs only if that error happened
    ...
else:                            # runs only if NO error happened
    return response
finally:                         # always runs (used to close the response)
    ...
```

## Standard library modules used

| Module | Used for | Where |
|--------|----------|-------|
| `ipaddress` | Understanding IPs: `ip.is_global`, `ipv4_mapped` | `netguard.py` |
| `urllib.parse` | Splitting and joining URLs | `urls.py`, `fetcher.py` |
| `urllib.robotparser` | Reading robots.txt rules | `types.py` (`RobotsInfo`) |
| `xml.etree.ElementTree` | Reading sitemap XML | `crawler.py` |
| `pkgutil`, `importlib` | Finding and importing every module in a folder | `registry.py` |
| `inspect` | `isabstract(cls)` | `checks/base.py` |
| `logging` | Writing errors to the worker log | `runner.py` |
| `math` | `floor` for rounding | `scoring.py` |
| `ast` | Reading Python code as data (the no-Django test) | `tests/engine/test_no_django.py` |

---

# Phase 3: concepts in the checks

## Regular expressions: `re` (`best_practices.py`)

A regular expression is a small pattern language for finding text:

```python
match = re.search(r"jquery[.-](\d+\.\d+(?:\.\d+)?)(?:\.min)?\.js", src)
if match:
    version = match.group(1)      # the text inside the first ( ) group, e.g. "1.12.4"
```

| Piece | Means |
|-------|-------|
| `r"..."` | A *raw* string: backslashes are kept as they are (needed for `\d`, `\.`) |
| `\d+` | One or more digits |
| `\.` | A real dot (a plain `.` means "any character") |
| `[.-]` | One character: a dot or a dash |
| `( ... )` | A group we want to read back with `.group(1)` |
| `(?: ... )` | A group just for structure, not saved |
| `?` | The thing before it is optional |
| `re.IGNORECASE` / `re.I` | Upper and lower case count as the same |
| `re.S` | `.` also matches line breaks |

`re.search` looks anywhere in the text. `re.match` only matches at the start, which is
why the doctype check uses it.

## `json` (`seo.py`)

```python
data = json.loads(node.text())   # text → Python dict/list; raises ValueError if invalid
json.dumps({"@type": "Bakery"})  # Python → text (used in tests)
```

## `@staticmethod`

```python
@staticmethod
def has_noindex(robots_value: str | None) -> bool:
```

A method that doesn't need `self`. It lives in the class because it belongs there
logically.

## Frozen dataclasses as small records (`best_practices.py`)

```python
@dataclass(frozen=True)
class _Library:
    name: str
    patterns: tuple[str, ...]   # a tuple of any length
    safe_from: str
```

`frozen=True` makes them read-only. They're good for tables of fixed data like the
`LIBRARIES` list. A leading `_` in a name means "internal to this module".

## Class attributes vs instance attributes (`checks/base.py`)

```python
class Check(ABC):
    partial: float | None = None    # class default, shared by everyone...

    # ...until one object assigns its own:
    self.partial = 0.75             # now only THIS object has 0.75
```

That's how a check remembers its partial score between `run()` and `score()`, without
affecting other checks.

## An abstract "helper" base class (`_SecurityHeader`)

```python
class _SecurityHeader(Check):   # no run() → still abstract → not registered
    category = Category.BEST_PRACTICES
    def header(self, page, name): ...

class NoSniff(_SecurityHeader):  # has run() → registered
```

Shared code lives in one place, and the abstract middle class never shows up in
reports.

## Dictionaries, the deeper parts

```python
sources.setdefault(link, []).append(page)   # get the list, creating it first if missing
by_title = defaultdict(list)                # a dict that makes an empty list on first use
by_title[text].append(url)
page.headers.get("x-frame-options", "")     # value, or "" if the key is missing
dict(zip(urls, statuses, strict=True))      # pair two lists into a dict; strict = same length
```

## Sets for "unique" collections

```python
active: set[str] = set()
active.add(url)                    # adding the same URL twice keeps one copy
sorted(active | passive)           # | = union (everything in either set)
policies & self.UNSAFE             # & = intersection (in both). Empty means "no unsafe policy"
```

## Strings, the deeper parts

```python
error.removeprefix("HTTP ")        # "HTTP 404" → "404"
code.isdigit()                     # True if every character is a digit
text.lstrip("﻿")              # remove an invisible "byte order mark" at the start
"; ".join(parts)                   # glue a list of strings together with "; "
value.split(",")                   # the opposite: cut a string into a list
```

Long strings are split across lines by placing them next to each other inside
brackets. Python joins them automatically:

```python
WHY = (
    "The title is the blue headline people click in Google results "
    "and the name on the browser tab."
)
```

## `getattr(obj, "name", default)`

This reads an attribute whose name is in a variable, or returns a default. The tests
use it to name parametrized cases: `ids=lambda value: getattr(value, "id", "")`.

---

# Phase 4: concepts in the browser collector

## Event handlers (callbacks)

```python
def on_console(message: ConsoleMessage) -> None:
    if message.type == "error":
        errors.append(message.text)

page.on("console", on_console)   # "call this function every time a console message appears"
```

You hand Playwright a function. It calls the function later, whenever the event
happens. `on_console` can use `errors` from the surrounding function (a closure).

## `contextlib.suppress`

```python
with contextlib.suppress(PlaywrightError):
    await page.wait_for_load_state("networkidle", timeout=5000)
```

"Try this, and if that specific error happens, just carry on." It's a shorter way to
write `try: ... except PlaywrightError: pass`.

## `itertools.pairwise`

```python
for previous, current in pairwise([1, 2, 4]):   # (1, 2), then (2, 4)
```

This compares each item with the one before it. It's how `HeadingOrder` spots a jump
from H2 to H4.

## Reading files next to the code

```python
AXE_SOURCE = (Path(__file__).resolve().parent.parent / "vendor" / "axe.min.js").read_text(encoding="utf-8")
```

`__file__` is this module's own path. Going up and into `vendor/` finds the file no
matter which folder you start Python from.

## `bytes`

```python
screenshot: bytes                      # raw binary data, not text
screenshot[:2] == b"\xff\xd8"          # b"..." is a bytes literal; JPEGs start with FF D8
bytes.fromhex("474946...")             # build bytes from hex digits (the test GIF)
```

## Running JavaScript from Python

```python
libraries = await page.evaluate("() => ({ jQuery: window.jQuery?.fn?.jquery })")
```

`page.evaluate` sends JavaScript to the browser, runs it inside the page and returns
the result converted to Python (`dict`, `list`, `str`…).

## `Field(exclude=True)` in Pydantic

```python
screenshot_jpeg: bytes | None = Field(default=None, exclude=True, repr=False)
```

The field exists on the object, but `model_dump()` (the JSON saved to the database)
leaves it out, and `print()` doesn't show 80 KB of binary data.

---

# Phase 5: concepts in performance and agentic checks

## Methods on a dataclass (`performance.py`)

```python
@dataclass(frozen=True)
class _Metric:
    good: float
    poor: float

    def rating(self, value: float) -> float:
        return 1.0 if value <= self.good else 0.5 if value <= self.poor else 0.0
```

Dataclasses are normal classes, so they can have methods. `a if x else b if y else c`
chains two conditions, like `if / elif / else` in one line.

## Default arguments capture a value *now* (`pagespeed.py`)

```python
for key in ("loadingExperience", "originLoadingExperience"):
    metrics = ...
    def percentile(name: str, metrics: dict[str, Any] = metrics) -> float | None:
        ...
```

A function defined inside a loop sees the loop variable as it is **when the function
runs**, not when it was defined. That's a classic bug (Ruff rule B023). Passing it as a
default argument freezes the current value.

## `getattr` with a computed name

```python
test = getattr(ctx.pagespeed, self.strategy)   # self.strategy is "mobile" or "desktop"
```

This is the same as `ctx.pagespeed.mobile` or `ctx.pagespeed.desktop`, picked at runtime.
It lets `MobileSpeed` and `DesktopSpeed` share one `run()` method.

## Reading deeply nested JSON safely

```python
lighthouse.get("categories", {}).get("performance", {}).get("score")
```

Each `.get(key, {})` returns an empty dict if the key is missing, so a missing piece
gives `None` at the end instead of a crash.

## `asyncio.gather(..., return_exceptions=True)`

```python
mobile, desktop = await asyncio.gather(
    run_test(..., "mobile"), run_test(..., "desktop"), return_exceptions=True
)
if isinstance(mobile, SpeedTest): ...
```

Normally one failure cancels everything. With `return_exceptions=True`, each result is
either the value or the exception object, so one failed test still leaves the other.

## `model_copy(update=...)` (Pydantic)

```python
FAST.model_copy(update={"score": 0.3})   # a copy with one field changed
```

The tests use this to make variations of one sample object.
