# Changelog

All notable changes to BizzCheckup are listed here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added
- **New homepage**: "Is your business website healthy?" with a live-looking report
  preview on a laptop next to the form, colourful cards for the five vital signs, a
  "How it works" strip with numbered steps, and a closing "More visibility. More trust.
  More growth." section with an illustration. Works in dark mode and on phones.
- Privacy link and version in the header.
- **Redesigned report page**, easier to act on: a sticky bar with the score and jump
  links; an overview with a score gauge, a one-sentence verdict, counters and the five
  vital signs as bars against the "Healthy" line; the top risks as problem, cost and
  solution cards; the treatment plan as a checklist saved in your browser; issues as rows
  that open to show why they matter and how to fix them. The PDF uses the same layout.
- **Check again now** button on reports and on the "couldn't finish" page: a fresh
  check-up of the same site that skips report reuse but keeps every other protection
  (an already-running check-up is reused, SSRF check, Turnstile, rate limit, capacity).
- Reports show how old they are ("Checked just now", "Checked 2 hours, 18 minutes ago").
- Messages (for example "rate limit reached") are shown at the top of any page.

### Fixed
- Sites behind Vercel's bot protection (and similar) answered "HTTP 429" with a challenge
  page. The User-Agent is now a browser identity with `BizzCheckup/0.1
  (+https://ridwanulhafiz.me)` at the end (as Lighthouse does). If a firewall still blocks
  the visit, the message says so, names the provider, and explains what to allow.
- When a firewall shows the **browser** a "verifying your browser" checkpoint, its
  screenshot and browser-based results are discarded instead of being reported as the
  website. The cover and notes explain why (`engine/firewall.py`, shared by the crawler,
  the browser and the AI-agent probe).
- Sites behind CDNs that reject requests without browser `Accept` headers (for example
  Hostinger's) failed with "HTTP 403". The fetcher now sends `Accept` and
  `Accept-Language` like a browser, and still identifies itself as BizzCheckup.
- Check-ups that never started because the job queue was down no longer count towards
  the visitor's hourly limit.
- Screenshots, PDFs and browser checks failed when the server couldn't find Chromium.
  Chromium is now installed inside the project (`.playwright/`) and used automatically.
- Reports said "no PageSpeed API key" even when a key existed but Google's test failed.
  Skip messages now give the real reason.
- In development, an old empty variable left in a terminal could hide the key in `.env`.
  `.env` now wins in development (servers still prefer real environment variables).
- Tests no longer read the developer's `.env`.

### Changed
- The progress page animates smoothly from 0% to 100%: real progress while each data
  source finishes, gentle creeping during slow steps, steps ticked off one by one, and a
  "Your report is ready" animation before the report opens. The PDF is ready when the
  report appears.
- Check-ups now start **immediately** in the web app by default (`CHECKUP_RUNNER=immediate`),
  with no Redis or worker needed, at most `CHECKUP_MAX_CONCURRENT` (3) at once. The Celery
  queue stays available with `CHECKUP_RUNNER=celery`, which Docker Compose uses.
- Check-ups interrupted by a server restart are marked as failed instead of showing
  progress forever.
- The development settings allow 50 check-ups per hour (production keeps 5).
- SQLite waits up to 20 s for the database instead of failing with "database is locked".
- Development log file `.run/bizzcheckup.log` with warnings, errors and tracebacks.

## [0.1.0-alpha] - 2026-10-07

First public release: the complete check-up flow from landing page to PDF.

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
- `Checkup`, `Finding` and `Lead` models with UUID share links, indexes for report reuse
  and rate limiting, and the screenshot stored in the database.
- Celery task `run_checkup` with the status flow queued → running → done/failed, friendly
  error messages, and soft and hard time limits.
- Check-up form on the landing page, an instant redirect, and a live HTMX progress page
  (polling every 2 s) that turns into the result at the same URL.
- Check-ups fail politely when the job queue is unavailable.
- Full Health Report at the check-up URL: cover with screenshot, score and five rings;
  diagnosis summary and top 3 risks; one section per vital sign; treatment plan with
  quick wins; services mapped to failing areas with a call to action; contact details
  with a QR code. All personal content comes from `branding.yaml`.
- `branding.yaml` validation (Pydantic) and a Django system check.
- PDF export with identical content (headless Chromium, no network access), generated by
  the worker and stored; a friendly fallback page if it fails.
- "Copy share link" button.
- Security and abuse protection: an SSRF check on the form (before queueing), 5
  check-ups per IP per hour, reuse of the same URL's report within 24 hours (not counted
  towards the limit), a global queue cap, a honeypot field, optional Cloudflare
  Turnstile, IPs stored only as salted HMAC hashes, and a strict Content Security Policy
  without `unsafe-inline` plus Permissions-Policy.
- Landing page: hero, the check-up form with optional name/email and required consent,
  the five vital signs, and "How it works".
- Lead capture (only when an email is given; also kept when a report is reused).
- Privacy note page, linked from every footer.
- Django admin for check-ups (search, status and health-band filters, inline findings,
  screenshot), findings (severity/category/impact/effort filters) and leads (CSV export
  protected against CSV injection).
- End-to-end test (form → worker → engine with Chromium → report → PDF) and a CI job
  that starts the full `docker compose` stack from a fresh clone.
- README with screenshots, an architecture diagram, scoring, how to add a check,
  deployment and responsible-use notes, plus a sample report of ridwanulhafiz.me.
- MIT licence.
- `start.sh`: a one-click local start (virtual env, libraries, `.env`, Docker services,
  Tailwind watcher, migrations, worker, dev server).

[Unreleased]: https://github.com/rdhafiz/bizzcheckup/compare/v0.1.0-alpha...HEAD
[0.1.0-alpha]: https://github.com/rdhafiz/bizzcheckup/releases/tag/v0.1.0-alpha
