# Architecture & Conventions

The one-page map of how BizzCheckup is built and the rules the code follows.
Keep it current whenever the structure changes.

## Big picture

```
 Browser ──HTTP──▶ web (Django + gunicorn) ──writes job──▶ Redis ──▶ worker (Celery)
    ▲                    │                                              │
    │ HTMX polls         │ reads/writes                                 │ runs the audit engine
    │ every 2 s          ▼                                              ▼
    └──────────────── PostgreSQL ◀─────────── saves progress, scores, findings
```

- **web** answers page requests quickly. It **never** runs an audit itself.
- **worker** picks up jobs from Redis and runs the audit engine. Slow work (crawling,
  Chromium, PageSpeed) happens here, so many check-ups never slow the website down.
- **PostgreSQL** stores check-ups, findings and leads. **Redis** is the job queue and
  the cache (for rate limiting).

## Layers

| Layer | Where | Rule |
|-------|-------|------|
| Audit engine | `bizzcheckup/engine/` | Pure Python. **No Django imports.** It can be reused outside Django. |
| Django apps | `bizzcheckup/core`, `checkups`, `reports` | Web concerns: models, views, templates, admin, tasks |
| Config | `config/` | Settings, URLs, Celery app. No business logic. |

### Engine design (phase 2 onwards)

1. **Collectors** do all the network work: crawler, robots.txt, sitemap, Playwright,
   PageSpeed, probes. Their results go into one `AuditContext`.
2. **Checks** are pure: `run(ctx) -> list[Finding]`. They never fetch anything, so
   they're tested with local HTML fixtures.
3. Every check is **one class** that registers itself (through `__init_subclass__`).
4. **Scoring** turns findings into category scores and the Business Health Score.

## Scoring

- **Check score** (0–1): from the worst finding. Pass and info count as 1, warn as 0.5,
  fail as 0. A check may override this; for example, the PSI check uses the Lighthouse
  score.
- **Category score** = `round(100 × Σ(weight × score) / Σ weight)`, skipping checks
  that didn't run. A category with a high-impact fail is capped at 89.
- **Business Health Score**: a weighted mean of the categories that were checked.
  The weights are Performance 25, SEO 25, Best practices 20, Accessibility 15 and
  Agentic 15.
- **Bands**:

| Score | Colour | Label |
|-------|--------|-------|
| 0–49 | red | Needs urgent care |
| 50–89 | orange | Needs attention |
| 90–100 | green | Healthy |

## Conventions

- Python 3.12+, type hints everywhere (mypy `strict`), Ruff for lint and format, and a
  line length of 100.
- Settings come only from environment variables (django-environ). Secrets never go in
  code.
- Views stay thin. Logic lives in the engine or in plain-Python service modules.
- Every check has a unit test that uses a local fixture. Tests never use the real
  network.
- User-facing copy is friendly and non-technical. Business impact comes first, then
  the fix. The health check-up theme is used without gimmicks.
- Branding and proposal content come only from `branding.yaml`.
- New dependencies need approval first, and each one gets documented in
  [Dependencies](04-dependencies.md).
- Commits are small, one per module or task, with a short one-line message.
