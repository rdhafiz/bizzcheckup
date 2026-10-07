# 4. Dependencies

Every library: **why** we chose it, **where** it's used and **how**.

Versions are **pinned** (`Django==5.2.18`), so every computer and the Docker image
install exactly the same thing. We only list libraries we import ourselves. pip
installs the libraries *they* need automatically. Run `pip freeze` to see everything.

| File | Contains |
|------|----------|
| `requirements/base.txt` | Needed to **run** the app (Docker installs only this) |
| `requirements/dev.txt` | `-r base.txt`, plus tools for **testing and checking** code |

---

## Runtime (`base.txt`)

### Django `5.2.18`

| | |
|---|---|
| **What** | Web framework: URLs, views, templates, database ORM, forms, admin, security |
| **Why** | It comes "batteries included", so login, admin, CSRF protection and migrations are already built. **5.2 is an LTS release**, which means it gets security fixes until April 2028. That makes it a safer base than the newest version. |
| **Where** | Everywhere: `config/`, `bizzcheckup/*/`, `manage.py` |
| **How** | See [How Django works](05-how-django-works.md) |

### django-environ `0.14.0`

| | |
|---|---|
| **What** | Reads settings from environment variables and the `.env` file, and converts their types |
| **Why** | Secrets must never be in code. It also converts text: `env.bool()` gives `True`, `env.list()` gives a list, and `env.db()` turns one `DATABASE_URL` line into Django's database dictionary. |
| **Where** | `config/settings/base.py`, `prod.py`, `dev.py` |
| **How** | `env("NAME")`, `env.bool("NAME", default=False)`, `env.db("DATABASE_URL")` |

```python
DATABASES = {"default": env.db("DATABASE_URL")}
# "postgres://user:pw@localhost:5432/bizzcheckup" becomes
# {"ENGINE": "django.db.backends.postgresql", "NAME": "bizzcheckup", "USER": "user", ...}
```

### psycopg `3.3.6` (`[binary]`)

| | |
|---|---|
| **What** | The driver that lets Python talk to PostgreSQL |
| **Why** | Django needs it for PostgreSQL. The `[binary]` version ships pre-compiled, so you don't need C build tools on Windows. |
| **Where** | Used by Django internally. We never import it ourselves. |

### redis `8.1.0`

| | |
|---|---|
| **What** | Python client for Redis, a very fast in-memory data store |
| **Why** | Celery uses Redis as its job queue. Django's cache uses it too, which we'll need for rate limiting in phase 8. |
| **Where** | `CACHES` and `CELERY_BROKER_URL` in `config/settings/base.py` |

### celery `5.6.3`

| | |
|---|---|
| **What** | Runs functions ("tasks") in a separate **worker** process |
| **Why** | A check-up takes 30–120 seconds. Running it inside a web request would block that web process and time out. See [Background jobs](12-background-jobs.md). |
| **Where** | `config/celery.py`, `bizzcheckup/*/tasks.py` |
| **How** | Mark a function with `@shared_task`, then call `my_task.delay(...)` to queue it |

### httpx `0.28.1`

| | |
|---|---|
| **What** | HTTP client: sends requests and reads responses |
| **Why** | It supports **async**, so the crawler can wait on two pages at once instead of one after the other. It has a clean API like `requests`, streams big bodies (so we can stop at 5 MB), and lets us plug in a fake transport for tests. |
| **Where** | `bizzcheckup/engine/fetcher.py` only |
| **How** | `async with httpx.AsyncClient() as client: response = await client.send(request, stream=True)` |

### pydantic `2.13.5`

| | |
|---|---|
| **What** | Data classes that **validate** their values |
| **Why** | A `Finding` with a typo'd severity, or an empty "how to fix", raises an error immediately instead of producing a broken report. `model_dump(mode="json")` turns a whole `AuditReport` into JSON for the database in one call. |
| **Where** | `engine/types.py`, `engine/config.py`, `engine/treatment.py` |
| **How** | `class Finding(BaseModel): severity: Severity`. Then `Finding(severity="warn", ...)` converts the text into `Severity.WARN`. |

### selectolax `1.0.0`

| | |
|---|---|
| **What** | A very fast HTML parser (it uses the Lexbor engine, written in C) |
| **Why** | Every check reads HTML. selectolax is many times faster than BeautifulSoup and supports CSS selectors such as `tree.css("a[href]")`. |
| **Where** | `engine/crawler.py` (links), `engine/context.py` (`ctx.tree(page)`), and every check |
| **How** | `LexborHTMLParser(html).css_first("title").text()` |

### playwright `1.63.0`

| | |
|---|---|
| **What** | Controls a real web browser (headless Chromium) from Python |
| **Why** | Many sites build their pages with JavaScript, so the raw HTML isn't what visitors see. Only a real browser can take a screenshot, run JavaScript, report JavaScript errors and cookies, and run the axe accessibility scanner. Playwright is modern, async and well maintained, and it can intercept every request the browser makes (needed for SSRF safety). |
| **Where** | `bizzcheckup/engine/collectors/render.py` only |
| **How** | `async with async_playwright() as p: browser = await p.chromium.launch()`, then `page.goto(url)`, `page.screenshot()` and `page.evaluate(js)` |
| **Browser** | Playwright downloads its own Chromium: `python -m playwright install --only-shell chromium` (done by `start.sh`, the Dockerfile and CI). `--only-shell` means the small headless build only. |

### gunicorn `26.2.0`

| | |
|---|---|
| **What** | A production web server for Python apps |
| **Why** | `manage.py runserver` is only for development: it's single-user and not hardened. Gunicorn runs several worker processes safely. |
| **Where** | `docker/Dockerfile` and `compose.yaml` (`gunicorn config.wsgi:application`) |

### whitenoise `6.12.0`

| | |
|---|---|
| **What** | Lets Django serve its own CSS, JS and fonts efficiently |
| **Why** | Without it, production needs a separate server (such as nginx) just for static files. WhiteNoise compresses files and gives them long cache lifetimes. |
| **Where** | `MIDDLEWARE` and `INSTALLED_APPS` in `base.py`, `STORAGES` in `prod.py` |

---

## Development tools (`dev.txt`)

| Library | What it does | Why |
|---------|--------------|-----|
| **pytest** `9.1.1` | Runs tests | Shorter, more readable tests than Python's `unittest` |
| **pytest-django** `4.14.0` | Connects pytest to Django | Gives fixtures like `client` (a fake browser) and `settings`, and sets up a test database |
| **ruff** `0.16.10` | Linter + formatter | Finds bugs, unused imports, security issues and style problems. Also formats code. One very fast tool replaces flake8, isort and black. |
| **mypy** `1.19.1` | Static type checker | Reads type hints and catches mistakes like passing a `str` where an `int` is expected, before the code runs |
| **pytest-asyncio** `1.4.0` | Runs `async def` tests | The engine is async. With `asyncio_mode = "auto"` in `pyproject.toml`, any `async def test_...` just works. |
| **respx** `0.23.1` | Fakes HTTP responses for httpx | Tests describe a fake website ("`GET https://shop.test/` returns this HTML"), so they never touch the real internet and always give the same result |
| **django-stubs** `5.2.9` | Type information for Django | Django has no type hints of its own. This adds them, so mypy understands models, querysets and settings. Version 5.2 matches Django 5.2. It needs mypy below 1.20, so mypy is pinned to 1.19.1. |

See [Testing & code quality](13-testing-and-quality.md) for how to run them.

---

## Not Python packages

| Tool | Where | Why |
|------|-------|-----|
| axe-core `4.14.0` (`axe.min.js`) | `bizzcheckup/engine/vendor/` | The industry-standard accessibility rules engine by Deque (also used by Lighthouse). It's a JavaScript file we run inside the browser page. It's stored in the repo (vendored) so audits never download code at runtime. Licence: MPL-2.0, see `AXE-LICENSE.txt`. |
| Tailwind CSS standalone CLI `v4.3.3` | `.bin/` (local), Dockerfile (image) | Builds our CSS. A single program, so no Node.js is needed. |
| Fonts: Bricolage Grotesque, Public Sans, JetBrains Mono | `static/fonts/` | Self-hosted, SIL Open Font License. Faster, private (no Google requests) and reliable in PDFs. |
| PostgreSQL 17, Redis 8 | Docker images in `compose.yaml` | Database and job queue |

---

## Coming in later phases (already approved)

| Library | Phase | For |
|---------|-------|-----|
| PyYAML, types-PyYAML | 7 | Reading `branding.yaml` |
| segno | 7 | QR code (SVG) on the contact page |
