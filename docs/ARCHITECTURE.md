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

- **web** answers page requests quickly. The form submission **never waits** for an
  audit: it redirects at once to the live progress page.
- **How the audit runs** depends on `CHECKUP_RUNNER`:
  - `immediate` (default): a background thread of the web app starts it straight away,
    at most 3 at once. No Redis or worker is needed.
  - `celery`: a job goes to Redis and a separate **worker** runs it (best for heavy
    traffic; Docker Compose uses this).
- **PostgreSQL** (or SQLite locally) stores check-ups, findings and leads.

## Layers

| Layer | Where | Rule |
|-------|-------|------|
| Audit engine | `bizzcheckup/engine/` | Pure Python. **No Django imports.** It can be reused outside Django. |
| Django apps | `bizzcheckup/core`, `checkups`, `reports` | Web concerns: models, views, templates, admin, tasks |
| Config | `config/` | Settings, URLs, Celery app. No business logic. |

### Engine design (details: [14-audit-engine.md](14-audit-engine.md))

1. **Collectors** do all the network work: crawler, robots.txt, sitemap, Playwright,
   PageSpeed, probes. Their results go into one `AuditContext`.
2. **Checks** are pure: `run(ctx) -> list[Finding]`. They never fetch anything, so
   they're tested with local HTML fixtures.
3. Every check is **one class** that registers itself (through `__init_subclass__`).
4. **Scoring** turns findings into category scores and the Business Health Score.
5. **Safety**: every outgoing request, and every redirect hop, passes the SSRF guard
   (`netguard.py`). That includes every request headless Chromium makes, through
   `_SafeRouter` in `collectors/render.py`. There are size, time and concurrency limits
   on everything.

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
- No inline `<script>` or `style=""`: the Content Security Policy forbids them
  ([Security](17-security.md)).
- New dependencies need approval first, and each one gets documented in
  [Dependencies](04-dependencies.md).
- Commits are small, one per module or task, with a short one-line message.
