# 3. Directory Layout

```
bizzcheckup/
├── bizzcheckup/              Our Python package: all app code lives here
│   ├── __init__.py           Package marker + __version__ ("0.1.0a0")
│   ├── core/                 Django app: site-wide pages and helpers
│   │   ├── apps.py           App configuration (name "bizzcheckup.core")
│   │   ├── context_processors.py  Puts product_name/tagline into every template
│   │   ├── security.py       IP hashing, Turnstile, security headers middleware
│   │   ├── templatetags/bizz.py  Template filters: band, band_label, severity_label...
│   │   ├── tasks.py          Celery jobs (just "ping" for now)
│   │   ├── urls.py           URLs of this app: /, /healthz/, /styleguide/
│   │   └── views.py          CONTROLLER: functions that handle requests
│   ├── engine/               Audit engine: pure Python, NO Django (docs/14-audit-engine.md)
│   │   ├── types.py          Data models: Finding, Page, CrawlResult, AuditReport...
│   │   ├── config.py         Limits (EngineConfig) and our User-Agent
│   │   ├── urls.py           normalize_url(), origin(), absolute()...
│   │   ├── netguard.py       SSRF protection: blocks private/internal addresses
│   │   ├── fetcher.py        The only code making HTTP requests (httpx)
│   │   ├── crawler.py        Homepage → robots.txt → sitemap → up to 10 pages
│   │   ├── context.py        AuditContext: everything checks can read
│   │   ├── registry.py       List of all checks; load_builtin_checks()
│   │   ├── scoring.py        Category scores, Business Health Score, bands
│   │   ├── treatment.py      Treatment plan ordering, quick wins
│   │   ├── runner.py         run_audit(): ties it all together
│   │   ├── collectors/       Extra data gathered after the crawl
│   │   │   ├── probes.py     Internal link statuses + does http:// redirect to https://
│   │   │   ├── render.py     Headless Chromium: rendered page, screenshot, axe scan
│   │   │   └── pagespeed.py  Google PageSpeed Insights (mobile + desktop)
│   │   ├── vendor/           Third-party files shipped with the engine
│   │   │   ├── axe.min.js    axe-core 4.14.0 accessibility scanner (MPL-2.0)
│   │   │   └── AXE-LICENSE.txt
│   │   └── checks/           One module per category (docs/15-checks-reference.md)
│   │       ├── base.py       The Check base class
│   │       ├── _helpers.py   meta_content(), on_pages(), share_score()...
│   │       ├── seo.py        11 SEO checks
│   │       ├── best_practices.py  14 security & standards checks
│   │       ├── accessibility.py   6 accessibility checks
│   │       ├── performance.py     7 speed checks
│   │       └── agentic.py         7 AI-readiness checks
│   ├── checkups/             Django app: check-ups
│   │   ├── models.py         MODEL: Checkup, Finding, Lead
│   │   ├── migrations/       Database changes (0001_initial.py)
│   │   ├── forms.py          CheckupForm: the URL field
│   │   ├── services.py       Business logic: create_checkup, save_report, mark_failed
│   │   ├── protection.py     Report reuse, rate limit, global capacity
│   │   ├── admin.py          Admin pages, health-band filter, lead CSV export
│   │   ├── tasks.py          Celery job run_checkup: runs the engine in the worker
│   │   ├── progress.py       Steps shown on the progress page
│   │   ├── views.py          CONTROLLER: start, detail, progress (HTMX), screenshot
│   │   └── urls.py           /checkups/new/, /checkups/<uuid>/, .../progress/, .../recheck/, .../screenshot.jpg
│   └── reports/              Django app: the Health Report (docs/16-health-report.md)
│       ├── apps.py           Registers the branding.yaml system check
│       ├── branding.py       Reads and validates branding.yaml (Pydantic)
│       ├── builder.py        Report data: vital signs, diagnosis, risks, services, QR
│       ├── pdf.py            Headless Chromium → PDF, with no network access
│       ├── views.py          report_page (used by checkups.detail), pdf download
│       └── urls.py           /checkups/<uuid>/report.pdf
├── config/                   Django project configuration
│   ├── __init__.py           Loads the Celery app when Django starts
│   ├── celery.py             The Celery app (background jobs)
│   ├── settings/
│   │   ├── base.py           Settings shared by every environment
│   │   ├── dev.py            Your computer (DEBUG on)
│   │   ├── test.py           pytest (SQLite in memory, fake cache, no worker)
│   │   └── prod.py           Live server (DEBUG off, HTTPS, secure cookies)
│   ├── urls.py               Main URL list. Hands paths to each app's urls.py.
│   ├── wsgi.py / asgi.py     Entry points for web servers (gunicorn)
├── templates/                HTML templates (VIEW layer)
│   ├── base.html             Page skeleton every page extends: header, footer, theme
│   ├── partials/             Small reusable pieces: logo, icons, illustrations, score ring, footer
│   ├── core/                 home (landing page + form), styleguide, legal/ (privacy, terms, cookies, ...)
│   ├── checkups/             progress.html, _progress_data.html (HTMX data), _recheck_form.html, failed.html
│   └── reports/              report.html (web), report_pdf.html (PDF), _sections.html (shared), ...
├── frontend/tailwind.css     Design system source (colours, fonts, components)
├── static/                   Files sent to the browser as they are
│   ├── css/app.css           BUILT by Tailwind (not in git)
│   ├── fonts/                Self-hosted fonts + their licences
│   ├── img/favicon.svg       Browser tab icon
│   ├── js/theme.js           Light/dark mode switch
│   ├── js/motion.js          Scroll reveal and parallax (see 19-motion.md)
│   ├── js/motion-boot.js     Hides animated content before the first paint (see 19-motion.md)
│   └── vendor/htmx.min.js    htmx 2.0.11 (+ licence)
├── tests/                    pytest tests, mirroring the package layout
│   ├── core/                 Tests for the core app
│   └── engine/               Engine tests (fake DNS + fake internet, no network)
│       ├── conftest.py       Shared fixtures: router (respx), fetcher, fake_resolver
│       ├── factories.py      make_page(), make_context(), fixture_html()...
│       └── checks/           One test file per check module
│   └── fixtures/html/        healthy.html and neglected.html test pages
├── start.sh                  One-click local start (see 02-installation.md)
├── scripts/get_tailwind.py   Downloads the Tailwind CLI into .bin/
├── docker/Dockerfile         How to build the app image
├── compose.yaml              Runs web, worker, postgres and redis together
├── .github/workflows/ci.yml  Automatic checks on GitHub
├── requirements/
│   ├── base.txt              Libraries the app needs to run
│   └── dev.txt               + test and code-quality tools
├── pyproject.toml            Settings for Ruff, mypy and pytest
├── branding.yaml             Consultant details used in the report
├── CHANGELOG.md              What changed in each version
├── LICENSE                   MIT licence: anyone may use, change and share the code
├── manage.py                 Django command-line tool
├── .env / .env.example       Your secrets (not in git) / the template (in git)
├── .gitignore                Files git never saves
├── .gitattributes            Forces Linux line endings (needed for Docker)
└── .dockerignore             Files left out of the Docker image
```

## Project vs app

- The **project** (`config/`) is the whole site's configuration. There is only one.
- An **app** (`bizzcheckup/core/` and others) is one feature area. Apps keep code
  organised: each has its own views, URLs, models and templates.

Our apps sit inside the `bizzcheckup/` package, which gives clean imports like
`from bizzcheckup.core.views import home`. It also means the engine can live at
`bizzcheckup.engine`.

## Why some files are not in git

| Ignored | Why |
|---------|-----|
| `.venv/` | Each computer creates its own from `requirements/` |
| `.env` | Secrets |
| `db.sqlite3` | Local test data |
| `.bin/`, `static/css/app.css` | Downloaded tool and its build output. Rebuilt anywhere. |
| `staticfiles/` | Output of `collectstatic` |
| `.run/` | Logs (`bizzcheckup.log`, `tailwind.log`, ...) and markers written by `start.sh` |
| `.playwright/` | Headless Chromium, downloaded by `start.sh` (about 150 MB) |
| `__pycache__/` | Compiled Python, recreated automatically |
