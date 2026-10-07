# Changelog

All notable changes to BizzCheckup are listed here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- Django 5.2 LTS project with split settings (`base`, `dev`, `test`, `prod`) configured
  through environment variables.
- Celery worker with Redis broker.
- Docker Compose stack: web (gunicorn), worker, PostgreSQL 17, Redis 8.
- GitHub Actions CI: Ruff, mypy, Django checks, migration check, pytest on PostgreSQL,
  Docker image build.
- Brand style: wordmark, colour tokens with light/dark themes, self-hosted fonts,
  buttons, cards, health-band pills, score rings, style guide page.
- Tailwind CSS standalone build with a download script.
- `/healthz/` endpoint for container health checks.
- Beginner-friendly documentation in `docs/`.
- Audit engine core (`bizzcheckup.engine`, no Django imports):
  - async fetcher (httpx) with timeouts, retries, 2 concurrent requests and a 5 MB page cap
  - SSRF guard on every request and redirect hop (private, loopback, link-local,
    metadata and IPv4-mapped addresses; only http/https on ports 80/443)
  - crawler: robots.txt, sitemap.xml (with index files), internal links, up to 10 pages
  - self-registering `Check` base class and registry
  - weighted scoring with health bands, a high-impact cap and the Business Health Score
  - treatment plan with quick wins
  - `run_audit()` with progress callbacks, a 3-minute total timeout and friendly errors
- Probes collector: internal link statuses (HEAD with GET fallback, max 50) and an
  http-to-https redirect probe.
- 11 SEO checks: titles, meta descriptions, single H1, canonical, robots.txt, sitemap,
  noindex, Open Graph/Twitter tags, JSON-LD validity, broken internal links, duplicate
  titles.
- 12 best-practice checks: HTTPS, http-to-https redirect, mixed content, HSTS, CSP,
  X-Content-Type-Options, frame protection, Referrer-Policy, outdated jQuery, Bootstrap,
  AngularJS and Lodash, doctype, charset, viewport.
- Healthy and neglected HTML fixtures, with a test for every check.
- Browser collector (Playwright + headless Chromium): rendered HTML, screenshot,
  JavaScript errors, cookies, runtime library versions and an axe-core 4.14 scan. Every
  browser request and redirect hop passes the SSRF guard; WebSockets and service workers
  are blocked.
- 6 accessibility checks: image alt text, page language, heading order, form labels,
  link/button names, and the axe-core scan (by impact, without double-counting).
- Best-practice checks for JavaScript errors and third-party cookies; the outdated
  libraries check also uses versions detected in the running page.
- Chromium installed in the Docker image, CI and `start.sh`.
- PageSpeed Insights collector (mobile + desktop in parallel; the key is sent in a header,
  never in the URL). Performance is skipped cleanly without `PSI_API_KEY`.
- 7 performance checks: mobile and desktop scores, Core Web Vitals (real-visitor data
  first, lab fallback), page weight, image dimensions, lazy loading, render-blocking files.
- 7 agentic browsing checks: llms.txt, AI crawlers in robots.txt (search vs training
  bots), firewall/CDN blocking of AI agents, JSON-LD, landmarks, named controls, content
  without JavaScript.
- Collectors run in parallel.
- `start.sh`: a one-click local start (virtual env, libraries, `.env`, Docker services,
  Tailwind watcher, migrations, worker, dev server).
