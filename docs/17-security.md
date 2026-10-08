# 17. Security & Abuse Protection

Strangers type addresses into BizzCheckup, and every check-up costs real resources: a
browser, dozens of requests, a PageSpeed call. This page lists every protection, where
it lives, and the test that proves it. Most are in `tests/security/test_security.py`.

## 1. SSRF: never visit internal addresses

**Risk:** someone submits `http://169.254.169.254/` (cloud servers keep secret keys
there) or `http://127.0.0.1:6379` (our Redis) and uses BizzCheckup to reach things
that should be private.

| Layer | Where | What it checks |
|-------|-------|----------------|
| The form | `checkups/forms.py::clean_url` | Runs `NetGuard.check_url` **before anything is queued**. The visitor sees a friendly error. |
| Every engine request | `engine/fetcher.py` | Runs the guard on the first URL **and every redirect hop** (it follows redirects itself) |
| Every browser request | `engine/collectors/render.py::_SafeRouter` | The same, for everything Chromium loads, including redirect hops. WebSockets and service workers are blocked. |
| The PDF | `reports/pdf.py` | Chromium has no network at all, apart from the branding photo |

The guard rules (`engine/netguard.py`): only `http`/`https`, only ports 80/443, no
`localhost`/`.local`/`.internal`, and **every** address the name resolves to must be a
public internet address. That excludes loopback, private, link-local, carrier NAT,
multicast, and IPv4 hidden inside IPv6.

**Known limit (DNS rebinding):** the name is checked, then looked up again when
connecting. A hostile DNS server could change its answer in between. For defence in
depth, run the worker in a network that **can't reach** internal services. See the
deployment notes in the README.

## 2. Rate limit: 5 check-ups per visitor per hour

`checkups/protection.py::over_rate_limit` counts the visitor's check-ups (by IP hash)
in the last hour. The 6th is refused with HTTP 429 and "You've started several
check-ups in the last hour…". The count comes from the **database**, so it works with
any number of web servers. Change it with `CHECKUP_RATE_LIMIT_PER_HOUR`.

- Check-ups that **never started** because *our* job queue was down don't count. That
  wasn't the visitor's fault. Check-ups that ran and then failed (for example, an
  unreachable site) do count, because they still cost resources.
- The development settings (`config/settings/dev.py`) default to 50 per hour, because you
  start many check-ups yourself while working. Production keeps 5.

## 3. Report reuse: same site within 24 hours

When a finished check-up of the **same normalised URL** exists from the last 24 hours
(`CHECKUP_REUSE_HOURS`), the visitor goes straight to that report. If one is still
running, they go to its progress page. Reused reports **don't count** toward the
rate limit.

### "Check again now" (`checkups/views.py::recheck`)

The button on reports skips **only** the reuse rule. It's a POST with CSRF protection.
It sends you to a check-up of the same site that's already running, runs the SSRF guard
again, applies Turnstile if it's on, counts towards the rate limit, and respects the
global cap. If it's refused, you're sent back to the report with a message (Django's
`messages` framework, shown in `base.html`).

## 4. Global capacity

- At most 3 check-ups run at the same time: per web process in `immediate` mode
  (`CHECKUP_MAX_CONCURRENT`), or per worker in `celery` mode (`--concurrency`, through
  `WORKER_CONCURRENCY`). Extra check-ups wait their turn.
- When 20 check-ups (`CHECKUP_QUEUE_CAP`) are already waiting or running, new ones are
  refused with HTTP 503 and "We're checking a lot of websites right now…".
- Check-ups run outside the request, so the form never waits. For heavy traffic, use
  `CHECKUP_RUNNER=celery` so audits run on separate worker machines.

## 5. Limits inside each check-up

| Limit | Value | Where |
|-------|-------|-------|
| Pages crawled | 10 (never more than 50) | `CHECKUP_MAX_PAGES`, `EngineConfig.max_pages` |
| Page size | 5 MB (bigger bodies are cut off) | `CHECKUP_MAX_PAGE_BYTES` |
| Requests to the site at once | 2 | `EngineConfig.max_concurrency` |
| Total time | 180 s, then Celery soft and hard limits | `CHECKUP_TIMEOUT_SECONDS` |
| Internal links probed | 50 | `EngineConfig.max_link_checks` |

## 6. Bots

| Protection | How |
|------------|-----|
| **Honeypot** | A text field named `website`, moved off-screen with CSS (`.honeypot`) and hidden from screen readers (`aria-hidden`, `tabindex="-1"`). People never fill it in; simple bots fill in every field. If it's filled, no check-up is created. |
| **Cloudflare Turnstile** (optional) | Set `TURNSTILE_SITE_KEY` and `TURNSTILE_SECRET_KEY`. The widget appears on the form, the CSP allows `challenges.cloudflare.com`, and the server verifies each token with Cloudflare. If Cloudflare can't be reached, the check **fails closed** (it's refused). |

## 7. Privacy: IP addresses are never stored

`core/security.py::hash_ip` stores `HMAC-SHA256(IP_HASH_SALT, ip)`. The same visitor
gives the same hash (enough for the rate limit), but the address can't be read back. A
plain SHA-256 without a secret salt could be reversed by simply trying all 4 billion
IPv4 addresses.

`client_ip` uses `REMOTE_ADDR`. It reads `X-Forwarded-For` **only** when
`TRUST_X_FORWARDED_FOR=True`, because without a proxy in front, visitors could fake that
header and dodge the rate limit.

Behind Cloudflare, set `CLIENT_IP_HEADER=CF-Connecting-IP` instead. Cloudflare **adds**
the real address to an `X-Forwarded-For` the visitor sent, so its first entry can still
be faked, but it always **overwrites** `CF-Connecting-IP`. Only use it when every request
reaches Django through Cloudflare (for example a tunnel to a port bound to `127.0.0.1`).

## 8. Headers, CSRF, DEBUG

`core/security.py::SecurityHeadersMiddleware` adds to every response:

```
Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self';
  img-src 'self' data: <branding photo host>; font-src 'self'; connect-src 'self';
  frame-src 'none'; object-src 'none'; base-uri 'self'; form-action 'self';
  frame-ancestors 'none'
Permissions-Policy: camera=(), microphone=(), geolocation=(), payment=()
Cross-Origin-Resource-Policy: same-origin
```

Django's own settings add `X-Frame-Options: DENY`, `X-Content-Type-Options: nosniff`
and `Referrer-Policy`. Production adds HSTS, an HTTPS redirect and secure cookies.

**The CSP has no `unsafe-inline`.** That's why the project avoids inline `<script>` and
`style="..."`. The progress bar is a native `<progress>` element, and htmx is told not
to inject its indicator `<style>` (`<meta name="htmx-config">` in `base.html`).

- **CSRF:** Django's CSRF middleware protects every form (`{% csrf_token %}`).
- **DEBUG:** always `False` in `config/settings/prod.py`, even if the environment says
  otherwise.

## Settings summary

| Variable | Default | Meaning |
|----------|---------|---------|
| `CHECKUP_RATE_LIMIT_PER_HOUR` | 5 | Check-ups per visitor per hour |
| `CHECKUP_QUEUE_CAP` | 20 | Waiting + running check-ups (everyone) |
| `CHECKUP_REUSE_HOURS` | 24 | Reuse a finished report this long |
| `IP_HASH_SALT` | the secret key | Secret for hashing IPs. Set your own in production. |
| `TRUST_X_FORWARDED_FOR` | False | True only behind a proxy you control |
| `CLIENT_IP_HEADER` | empty | `CF-Connecting-IP` behind Cloudflare (wins over X-Forwarded-For) |
| `TURNSTILE_SITE_KEY` / `TURNSTILE_SECRET_KEY` | empty | Turn on Cloudflare Turnstile |
