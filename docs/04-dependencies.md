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
| **django-stubs** `5.2.9` | Type information for Django | Django has no type hints of its own. This adds them, so mypy understands models, querysets and settings. Version 5.2 matches Django 5.2. It needs mypy below 1.20, so mypy is pinned to 1.19.1. |

See [Testing & code quality](13-testing-and-quality.md) for how to run them.

---

## Not Python packages

| Tool | Where | Why |
|------|-------|-----|
| Tailwind CSS standalone CLI `v4.3.3` | `.bin/` (local), Dockerfile (image) | Builds our CSS. A single program, so no Node.js is needed. |
| Fonts: Bricolage Grotesque, Public Sans, JetBrains Mono | `static/fonts/` | Self-hosted, SIL Open Font License. Faster, private (no Google requests) and reliable in PDFs. |
| PostgreSQL 17, Redis 8 | Docker images in `compose.yaml` | Database and job queue |

---

## Coming in later phases (already approved)

| Library | Phase | For |
|---------|-------|-----|
| httpx | 2 | Async HTTP fetching in the crawler |
| pydantic | 2 | Engine data models (Finding, Page, Report) with validation |
| selectolax | 3 | Very fast HTML parsing for checks |
| pytest-asyncio, respx | 2 | Testing async code; faking httpx responses (no network in tests) |
| playwright | 4 | Headless Chromium: JS rendering, screenshots, axe-core, PDF |
| PyYAML, types-PyYAML | 7 | Reading `branding.yaml` |
| segno | 7 | QR code (SVG) on the contact page |
