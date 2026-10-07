# BizzCheckup Documentation

These pages explain **everything** about BizzCheckup in plain language: what it does,
how to install it, how the code is organised, and why each library is used.

Read them in order the first time. Later, jump to the page you need.

| # | Page | What you learn |
|---|------|----------------|
| — | [Architecture](ARCHITECTURE.md) | The big picture, main design decisions and code conventions |
| 1 | [Prerequisites](01-prerequisites.md) | What must be installed on your computer first |
| 2 | [Installation](02-installation.md) | Running it with Docker, or from a virtual environment |
| 3 | [Directory layout](03-directory-layout.md) | What every folder and file is for |
| 4 | [Dependencies](04-dependencies.md) | Every library: why, where and how we use it |
| 5 | [How Django works (MVC / MTV)](05-how-django-works.md) | Model, View, Template, URLs, the request flow |
| 6 | [Configuration](06-configuration.md) | Settings files, environment variables, `branding.yaml` |
| 7 | [Database](07-database.md) | PostgreSQL, models, migrations |
| 8 | [Use cases](08-use-cases.md) | What visitors and the consultant can do |
| 9 | [Python concepts used](09-python-concepts.md) | Python features you meet in this code, explained |
| 10 | [Git workflow & CI](10-git-workflow.md) | Daily git commands and the automatic checks on GitHub |
| 11 | [Frontend & brand](11-frontend-and-brand.md) | Tailwind, colours, fonts, dark mode, templates |
| 12 | [Background jobs](12-background-jobs.md) | Celery and Redis: why check-ups run in a worker |
| 13 | [Testing & code quality](13-testing-and-quality.md) | pytest, Ruff, mypy: what each one catches |
| 14 | [The audit engine](14-audit-engine.md) | Crawler, SSRF guard, checks, scoring: how a website gets examined |
| 15 | [Checks reference](15-checks-reference.md) | Every check: what it looks at, when it passes, warns or fails |
| 16 | [The Health Report](16-health-report.md) | The six report sections, branding.yaml, how the PDF is made |
| 17 | [Security & abuse protection](17-security.md) | SSRF, rate limits, reuse, bots, IP privacy, headers |

## What is BizzCheckup?

A business owner types in their website address. BizzCheckup gives them a
**Health Report**, like a medical check-up for their website:

| Category id | "Vital sign" | What it measures |
|-------------|--------------|------------------|
| `performance` | Speed | How fast the site loads (Core Web Vitals, via Google PageSpeed) |
| `accessibility` | Accessibility | Whether people with disabilities can use it |
| `best_practices` | Security & standards | HTTPS, security headers, outdated libraries |
| `seo` | Google visibility | Whether Google can find and understand it |
| `agentic` | AI readiness | Whether AI assistants and AI search can read it |

The report ends with a **treatment plan** of what to fix first, and a proposal page
offering the consultant's services. All of that content comes from `branding.yaml`.

## Project status: v0.1.0-alpha released

| Phase | What | Status |
|-------|------|--------|
| 1 | Project setup: Django, Docker Compose, Celery, CI, Tailwind, brand style | Done |
| 2 | Engine core: crawler, Check/Finding models, registry, scoring | Done |
| 3 | SEO and Best Practices checks | Done |
| 4 | Playwright rendering, screenshots, accessibility checks | Done |
| 5 | PageSpeed performance + Agentic Browsing checks | Done |
| 6 | Models, Celery task, live progress page | Done |
| 7 | Report page, treatment plan, proposal, PDF | Done |
| 8 | Security & abuse protection | Done |
| 9 | Landing page, lead capture, admin, privacy | Done |
| 10 | Final docs, sample report, release tag | Done: **v0.1.0-alpha** |
