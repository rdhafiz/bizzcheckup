# BizzCheckup

**Check your business's online health.**

BizzCheckup is a free website health check-up for business owners. Enter a URL and
get a report like Google Lighthouse, explained in plain business language:

- **Vital signs:** Performance, Accessibility, Best Practices, SEO and Agentic
  Browsing (AI readiness), each scored 0–100.
- **Business Health Score** with clear bands: Needs urgent care, Needs attention,
  Healthy.
- **Treatment plan:** what to fix first, quick wins at the top.
- A downloadable **PDF** and a private share link.

> Status: in development towards **v0.1.0-alpha**.

## Quick start (Docker)

```bash
git clone https://github.com/rdhafiz/bizzcheckup.git
cd bizzcheckup
docker compose up --build
```

Open <http://localhost:8000>.

To develop without running the app in Docker, see
[docs/02-installation.md](docs/02-installation.md).

## Tech stack

Python 3.12 · Django 5.2 LTS · PostgreSQL · Redis · Celery · HTMX · Tailwind CSS ·
Playwright · Docker · GitHub Actions

## Documentation

Everything (setup, architecture, how scoring works, every library and why it's used)
is in [docs/](docs/README.md).

## Branding

All consultant details shown in the report come from [`branding.yaml`](branding.yaml).
Fork the project and replace that file with your own details.
