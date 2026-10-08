# Changelog

All notable changes to BizzCheckup are listed here.
Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions follow
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.0-alpha] - 2026-10-08

### Added
- **9 new checks (54 in total)**:
  - **Technical SEO**, page by page: heading outline review, image alt text and file
    names, clean URLs (with a suggested clean address for each) and essential meta tags
    (with a complete `<head>` block per page).
  - **Page schema** (`seo.page_schema`, replaces `seo.structured_data`): works out what
    kind each page is (homepage, about, contact, article, product, service, FAQ, listing,
    other), checks its JSON-LD has what that kind needs, and when something is missing
    suggests the **complete** schema for the page: the site's own values kept, facts read
    from the page filled in, the rest marked `REPLACE:`.
  - **Broken links to other websites and broken images**, each listed with the pages
    they're on. Sites that refuse robots (LinkedIn's 999, 403, 429) aren't counted as
    broken, and slow sites can't hold up the check-up (a 30-second budget).
  - **Phone and tablet checks**: the homepage is opened as a 390 px phone and an 820 px
    tablet to check for a shrunken desktop page, sideways scrolling, links too small to
    tap and tiny text.
- **Link previews on every page** (was the homepage only), with a ready-made block of
  Open Graph tags per page; the preview picture is downloaded and checked.
- **Ready-to-use fixes in the report**: schema, meta tags and link preview tags as code
  with a **Copy** button, one per page; page-by-page breakdowns for headings, images,
  URLs and broken links.
- **Accessibility problems show where they are**: each element the scan flags comes with
  a screenshot of the spot (outlined in red), what's wrong in words, its HTML and CSS
  selector, and for colour contrast a sample of the text in its real colours with the
  current and required ratio.
- **"We found N pages"**: every page address found (sitemap and links), which ones were
  checked, and a proposal to check the whole website (`full_audit` in `branding.yaml`).
- Desktop / Tablet / Phone screenshots as tabs, and a card showing how the homepage looks
  when shared on Facebook, WhatsApp or LinkedIn.
- New `Finding.snippets` field and `CheckupImage` table for the report's extra pictures
  (migrations `0003`–`0005`).
- **New homepage**: a full-screen hero on a photo with the check-up form, colourful cards
  for the five vital signs, a one-screen "How it works" timeline with illustrations, and a
  closing "More visibility. More trust. More growth." section. Works in dark mode and on
  phones.
- **Motion** (`static/js/motion.js`, no library): sections, cards and headings reveal as
  they scroll into view in both directions (headings word by word, sharpening out of a
  blur), with parallax on the hero photos and smooth scrolling for in-page links. It
  fails open, respects reduced motion, has no blur or parallax on small screens, and a
  watchdog shows everything if reveals stall.
- **Site footer**, **legal pages** (terms, cookies, acceptable use, disclaimer and a
  restyled privacy policy, from the new `legal` section in `branding.yaml`), and
  **`/robots.txt`**, **`/sitemap.xml`** and **`/llms.txt`**.
- **Check again now** on reports and on the "couldn't finish" page: a fresh check-up that
  skips report reuse but keeps every other protection.
- Reports show how old they are ("Checked 2 hours, 18 minutes ago"), and messages (for
  example "rate limit reached") appear at the top of any page.

### Changed
- **The report is redesigned as a dashboard in the homepage's theme**:
  - a dark opening band with the website's own preview image (or a demo picture) behind
    it, the domain in the green gradient, the diagnosis, the actions and a frosted score
    panel (the PDF's cover too);
  - a sticky sidebar with the score, the sections and the five vital signs (click one to
    see only its issues);
  - "Fix these first", then **one list of every issue** that you can filter by vital
    sign and severity. Each issue appears once, so the page is about 40% shorter;
  - "How … can help" with the homepage's vital-sign cards, each linking to the issues
    it treats, and a green call to action;
  - a dark contact card with credential badges, a tile per way to get in touch, and a QR
    code that now fills its box.
- **Theme colour #31ac64** (green) across the site, with white bold text on it and a
  deeper green for text.
- The progress page animates smoothly to 100% and plays a "Your report is ready"
  animation; the PDF is ready when the report appears.
- Check-ups start **immediately** in the web app by default (`CHECKUP_RUNNER=immediate`,
  at most `CHECKUP_MAX_CONCURRENT` at once); Celery stays available with
  `CHECKUP_RUNNER=celery`, which Docker Compose uses. Check-ups interrupted by a restart
  are marked as failed instead of showing progress forever.
- Development: 50 check-ups per hour, SQLite waits up to 20 s instead of "database is
  locked", and a log file at `.run/bizzcheckup.log`.

### Fixed
- Sites behind Vercel's bot protection (and similar) answered "HTTP 429". The User-Agent
  is now a browser identity with `BizzCheckup/0.1 (+https://ridwanulhafiz.me)` at the end.
  If a firewall still blocks the visit, the message names the provider and explains what
  to allow.
- When a firewall shows the browser a "verifying your browser" checkpoint, its screenshot
  and browser results are discarded instead of being reported as the website.
- Sites behind CDNs that reject requests without browser `Accept` headers (for example
  Hostinger's) failed with "HTTP 403".
- PDFs could fail when the consultant's photo website was slow; the photo is now fetched
  with a 5-second limit.
- Screenshots, PDFs and browser checks failed when the server couldn't find Chromium; it
  is now installed inside the project (`.playwright/`) and used automatically.
- Reports said "no PageSpeed API key" even when a key existed but Google's test failed.
- Check-ups that never started because the job queue was down no longer count towards the
  visitor's hourly limit.
- Following a link into a section scrolled that section's content inside itself
  (`overflow: clip` now).
- In development, `.env` wins over an old empty variable left in a terminal; tests no
  longer read the developer's `.env`.

### Removed
- The treatment-plan checklist (tick boxes and the "issues fixed" progress bar) and the
  browser storage it used.
- The summary sentences and the "We checked N pages" list under the report overview (the
  pages checked are in **All pages**).

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

[Unreleased]: https://github.com/rdhafiz/bizzcheckup/compare/v0.2.0-alpha...HEAD
[0.2.0-alpha]: https://github.com/rdhafiz/bizzcheckup/releases/tag/v0.2.0-alpha
[0.1.0-alpha]: https://github.com/rdhafiz/bizzcheckup/releases/tag/v0.1.0-alpha
