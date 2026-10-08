# 6. Configuration

| Place | Contains | In git? |
|-------|----------|---------|
| `config/settings/*.py` | How Django is set up | Yes |
| Environment variables / `.env` | Secrets and per-machine values | **No** (`.env.example` is) |
| `branding.yaml` | Consultant details for the report | Yes |

## Settings files

```
config/settings/
├── base.py   shared by everything
├── dev.py    from .base import *   + DEBUG on by default
├── test.py   from .base import *   + SQLite in memory, fake cache, tasks run inline
└── prod.py   from .base import *   + DEBUG off, HTTPS redirect, HSTS, secure cookies
```

`from .base import *` copies every setting from `base.py`. The file then changes only
what's different. Django picks the file from the `DJANGO_SETTINGS_MODULE` variable:

| Who | Uses |
|-----|------|
| `python manage.py ...` | `config.settings.dev` (default in `manage.py`) |
| pytest | `config.settings.test` (set in `pyproject.toml`) |
| gunicorn (`wsgi.py`) | `config.settings.prod` (default), but `compose.yaml` sets `dev` locally |

## Environment variables

| Variable | Required | Default | Meaning |
|----------|----------|---------|---------|
| `DJANGO_SECRET_KEY` | yes | — | Signs cookies and tokens. If it leaks, attackers can forge sessions. |
| `DJANGO_DEBUG` | no | `False` (`True` in dev) | Detailed error pages. **Never on in production.** |
| `DJANGO_ALLOWED_HOSTS` | no | `localhost,127.0.0.1` | Domain names the site answers to |
| `DATABASE_URL` | yes | — | e.g. `postgres://user:pw@host:5432/db` |
| `REDIS_URL` | no | `redis://localhost:6379/0` | Cache (only with `celery`) |
| `CELERY_BROKER_URL` | no | `redis://localhost:6379/1` | Job queue (a separate Redis database, number 1) |
| `PSI_API_KEY` | no | empty | Google PageSpeed key. Empty means performance checks are skipped and the report says so. |
| `DJANGO_SECURE_SSL_REDIRECT` | prod only | `True` | Redirect http to https |
| `DJANGO_CSRF_TRUSTED_ORIGINS` | prod only | empty | e.g. `https://bizzcheckup.example.com` |
| `WORKER_CONCURRENCY` | compose only | `3` | How many check-ups run at once |
| `CHECKUP_MAX_PAGES` | no | `10` | Pages crawled per check-up |
| `CHECKUP_TIMEOUT_SECONDS` | no | `180` | Total time per check-up |
| `CHECKUP_MAX_PAGE_BYTES` | no | `5242880` | Largest page body read (5 MB) |
| `CHECKUP_RATE_LIMIT_PER_HOUR` | no | `5` | Check-ups per visitor per hour |
| `CHECKUP_QUEUE_CAP` | no | `20` | Waiting + running check-ups for everyone |
| `CHECKUP_REUSE_HOURS` | no | `24` | Reuse a finished report of the same URL this long |
| `IP_HASH_SALT` | prod: yes | the secret key | Secret used to hash visitor IPs |
| `TRUST_X_FORWARDED_FOR` | no | `False` | Read the client IP from the proxy header |
| `TURNSTILE_SITE_KEY`, `TURNSTILE_SECRET_KEY` | no | empty | Cloudflare Turnstile on the form |
| `CHECKUP_RUNNER` | no | `immediate` | `immediate`: run in the web app right away (no Redis). `celery`: use the queue and worker. |
| `CHECKUP_MAX_CONCURRENT` | no | `3` | Check-ups running at the same time per web process (`immediate` mode) |

The security-related ones are explained in [Security](17-security.md).

### Getting a PageSpeed API key (free)

1. Go to <https://developers.google.com/speed/docs/insights/v5/get-started> and click
   **Get a Key**.
2. Choose or create a Google Cloud project. The key is created for you.
3. Put it in `.env` as `PSI_API_KEY=...` and restart the server and the worker.

The free quota is about 25,000 tests a day (each check-up uses 2). Keep the key secret:
`.env` is never committed.

## How `base.py` reads them

```python
import environ

BASE_DIR = Path(__file__).resolve().parent.parent.parent   # the project root
env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")                      # load .env if present

SECRET_KEY = env("DJANGO_SECRET_KEY")                        # required: crashes if missing
DEBUG = env.bool("DJANGO_DEBUG", default=False)              # "True" → True
ALLOWED_HOSTS = env.list("DJANGO_ALLOWED_HOSTS", default=["localhost", "127.0.0.1"])
DATABASES = {"default": env.db("DATABASE_URL")}
```

- `BASE_DIR` goes up three `.parent`s because the file is now at
  `config/settings/base.py`.
- **Which wins, `.env` or the environment?**
  - On your computer (`config.settings.dev`): **`.env` wins**. A terminal can hold old
    copies of variables. For example, an editor may have loaded `PSI_API_KEY=` (empty)
    into it before you added your key. Making `.env` win means editing `.env` and
    restarting is always enough.
  - On a server (`prod`, Docker): **real environment variables win**, which is how
    servers and containers are normally configured.
  - In tests: `.env` is **not read at all**, so your personal settings can't change
    test results.
- A required variable that's missing stops Django with a clear message. That's better
  than running with a bad configuration.

## Log file (development)

`config/settings/dev.py` writes warnings and errors, with full tracebacks, from
BizzCheckup's code to **`.run/bizzcheckup.log`** as well as the terminal. If a check-up
skips something unexpectedly (for example, "We couldn't open your site in a browser"),
the reason is in that file.

## Production security (`prod.py`)

| Setting | Protects against |
|---------|------------------|
| `DEBUG = False` | Leaking code and settings in error pages |
| `SECURE_SSL_REDIRECT` | Traffic sent unencrypted over http |
| `SECURE_HSTS_SECONDS` (1 year) | Browsers ever using http for the site again |
| `SESSION_COOKIE_SECURE`, `CSRF_COOKIE_SECURE` | Cookies being sent over http |
| `X_FRAME_OPTIONS = "DENY"` (base) | Our pages being embedded in other sites (clickjacking) |
| `SECURE_CONTENT_TYPE_NOSNIFF` (base) | Browsers guessing file types |

Check them with:

```bash
DJANGO_SETTINGS_MODULE=config.settings.prod python manage.py check --deploy
```

## Custom BizzCheckup settings

| Setting | Meaning |
|---------|---------|
| `PSI_API_KEY` | From the environment. Used by the performance collector. |
| `BRANDING_FILE` | Path to `branding.yaml` |

Read them anywhere with `from django.conf import settings` and then
`settings.BRANDING_FILE`.

## `branding.yaml`

This file controls everything personal in the report: product name, consultant intro,
contact links, services and the call to action. Someone who forks the project only
edits this file.

The `legal` section (operator, country, "last updated" date) feeds the legal pages; see
[Legal pages & footer](18-legal-pages.md).

`services[].related_categories` must use the engine's category ids: `performance`,
`accessibility`, `best_practices`, `seo` and `agentic`. A failing category recommends
the services linked to it.
