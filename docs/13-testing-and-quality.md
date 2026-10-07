# 13. Testing & Code Quality

Four commands. Run them before every commit:

```bash
ruff check .            # lint: bugs, security issues, unused code, import order
ruff format .           # format: consistent spacing and quotes (changes files)
mypy .                  # types: wrong argument types, missing returns
pytest -q               # tests: does the code do what it should?
```

All their settings are in `pyproject.toml`.

## pytest

Tests live in `tests/`, mirroring the package (`tests/core/` tests `bizzcheckup/core/`).

```python
def test_healthz_returns_ok(client: Client) -> None:
    response = client.get(reverse("core:healthz"))

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
```

- A test is a function whose name starts with `test_`.
- `assert` checks that something is true. If it isn't, the test fails and shows both
  values.
- `client` is a **fixture**: pytest-django passes in a fake browser automatically,
  matched by the parameter name.
- `settings` is another fixture. It changes a setting for one test only
  (`test_styleguide_visible_when_debug_on`).
- Structure each test as **arrange, act, assert**: set up, do the thing, check the
  result.

Useful options:

| Command | Does |
|---------|------|
| `pytest -q` | Quiet summary |
| `pytest tests/core` | One folder only |
| `pytest -k healthz` | Only tests with "healthz" in the name |
| `pytest -x` | Stop at the first failure |
| `pytest -vv` | Show each test name and full differences |

Tests use `config.settings.test`: SQLite in memory, an in-memory cache, and tasks run
inline. They never touch the real network. From phase 2, HTTP is faked with `respx`
and HTML comes from files in `tests/fixtures/`.

## Ruff

Rules enabled (see `[tool.ruff.lint]`):

| Code | Catches |
|------|---------|
| `E`, `W` | Basic style |
| `F` | Unused imports and variables, undefined names |
| `I` | Import order |
| `B` | Common bug patterns |
| `UP` | Old syntax that has a modern equivalent |
| `SIM` | Code that can be simpler |
| `N` | Naming (`snake_case` functions, `CamelCase` classes) |
| `S` | Security (bandit), e.g. opening URLs with any scheme or hard-coded passwords |
| `DJ` | Django mistakes, e.g. `null=True` on text fields |
| `PT` | pytest style |
| `RUF` | Ruff's own checks, e.g. a `# noqa` that isn't needed |

`# noqa: S310` on a line tells Ruff "I checked this one". Always add a comment
explaining why.

## mypy

`strict = true` means every function needs type hints, and mypy checks every call.
The `django-stubs` plugin teaches mypy about Django.

Two exceptions are in `pyproject.toml`:

- `celery` and `environ` ship without type information, so mypy skips analysing them
  (`ignore_missing_imports`).
- In `*.tasks` modules, Celery's `@shared_task` decorator is allowed to be untyped.

## Current tests

| Test | Checks |
|------|--------|
| `test_home_shows_brand_name_and_tagline` | Landing page title has the brand name and tagline |
| `test_healthz_returns_ok` | Docker health endpoint |
| `test_styleguide_hidden_when_debug_off` | Style guide gives a 404 in production |
| `test_styleguide_visible_when_debug_on` | Style guide works in dev |
| `test_ping_task_runs` | Celery is wired up |

---

## Testing the engine (phase 2)

### No real internet, ever

Engine tests use two fakes, both defined in `tests/engine/conftest.py`:

| Fake | Replaces | How |
|------|----------|-----|
| `fake_resolver` | DNS | A dict: `"shop.test"` maps to a public IP, `"evil.test"` to `10.0.0.1` |
| `router` (respx) | The internet | Routes like `router.get("https://shop.test/").respond(200, html="...")` |

The `fetcher` fixture builds a real `Fetcher` wired to both fakes:

```python
async def test_redirect_to_private_address_is_blocked(fetcher, router):
    router.get("https://shop.test/").respond(302, headers={"Location": "http://169.254.169.254/"})
    with pytest.raises(BlockedURLError):
        await fetcher.get("https://shop.test/")
```

`assert_all_mocked=True` means any request to an address without a route **fails the
test**. A test can't secretly reach the internet.

### `conftest.py` and fixtures

pytest automatically loads `conftest.py` files. A **fixture** is a function marked
`@pytest.fixture`. Any test with a parameter of the same name receives its return
value. A fixture that uses `yield` runs its cleanup code after the test, which is how
the `fetcher` fixture closes the client.

### `@pytest.mark.parametrize`: one test, many inputs

```python
@pytest.mark.parametrize("url", ["http://127.0.0.1/", "http://10.0.0.1/", ...])
async def test_internal_addresses_are_blocked(guard, url):
```

Each value becomes its own test in the results, so you see exactly which one failed.
`test_netguard.py` checks 22 blocked addresses this way.

### `pytest.raises`

```python
with pytest.raises(AuditError, match="took too long"):
    await run_audit(...)
```

The test passes only if that error is raised **and** its message matches.

### `monkeypatch`

`test_registry.py` uses `monkeypatch.setattr(...)` to swap in an empty registry for
one test. It's put back automatically afterwards.

### Factories (`tests/engine/factories.py`)

`make_page()`, `make_context()`, `make_finding()` and `make_result()` build test
objects with sensible defaults, so each test only states what matters to it. Phase 3's
check tests build their contexts with `make_context(make_page(html))`.

### Engine test files

| File | Covers |
|------|--------|
| `test_urls.py` | URL normalising and link resolution |
| `test_types.py` | Pydantic validation of findings and pages |
| `test_netguard.py` | Every kind of blocked address, port and scheme |
| `test_fetcher.py` | User-Agent, redirects, SSRF on redirect, size cap, retries |
| `test_crawler.py` | robots.txt, sitemap, link fallback, max pages, XML bomb safety |
| `test_registry.py` | Self-registration, duplicates, validation, ordering |
| `test_scoring.py` | Severity scores, band boundaries, weights, cap, rebalancing |
| `test_treatment.py` | Quick wins and ordering |
| `test_runner.py` | A full audit with fake checks: skips, crashes, progress, timeouts, errors |
| `test_no_django.py` | The engine never imports Django or Celery |

---

## Testing checks (phase 3)

### Healthy vs neglected fixtures

`tests/fixtures/html/` holds two complete pages:

| File | What it is |
|------|------------|
| `healthy.html` | Does everything right: title, description, one H1, canonical, social tags, valid JSON-LD, viewport, doctype, secure files, modern jQuery |
| `neglected.html` | Does almost everything wrong: noindex, no title, two H1s, broken JSON-LD, `http://` files, jQuery 1.12.4, Bootstrap 3.3.7, no viewport, no doctype |

Every check is tested twice with them, using `@pytest.mark.parametrize`:

```python
@pytest.mark.parametrize("check", SEO_CHECKS, ids=lambda c: c.id)
def test_healthy_page_passes(check):
    assert severities(check, healthy_context()) == [Severity.PASS]
```

```python
(seo.Title, [Severity.FAIL]),        # neglected.html has no <title>
(seo.Indexable, [Severity.FAIL]),    # neglected.html says noindex
```

Then smaller tests cover the edge cases with tiny inline HTML. Examples: a 61-character
title, a canonical pointing at a competitor, `<!DOCTYPE HTML>` with a byte order mark,
and eleven jQuery/Bootstrap/AngularJS/Lodash script addresses.

Security headers are tested by passing `headers={...}` to `make_page()`. No web server
is needed.

### Check test files

| File | Tests |
|------|-------|
| `tests/engine/checks/test_seo.py` | All 11 SEO checks |
| `tests/engine/checks/test_best_practices.py` | All 12 best-practice checks |
| `tests/engine/test_probes.py` | Link statuses, http→https probe, HEAD→GET fallback, link limit |

---

## Browser tests (phase 4)

`tests/engine/test_render.py` starts **real headless Chromium** against a tiny web
server running inside the test (Python's built-in `http.server`, on `127.0.0.1` and
a random free port). There's still no internet.

The test page deliberately misbehaves: a JavaScript error, an image redirecting to
`10.0.0.1`, an image pointing at the cloud metadata address, a cookie set from another
host, a fake old jQuery, and an image without alt text. The test then checks that
everything was recorded **and** that both internal addresses were blocked.

`LocalTestGuard` is the real `NetGuard` with one exception: the test server itself is
allowed. Every other address follows the normal SSRF rules.

These tests are marked `@pytest.mark.browser`:

| Command | Runs |
|---------|------|
| `pytest` | Everything, including browser tests (about 2 extra seconds) |
| `pytest -m "not browser"` | Everything except browser tests |
| `pytest -m browser` | Only browser tests |

If Chromium isn't installed, the browser test is **skipped** with a hint, not failed.
CI installs Chromium, so it always runs there.

Browser-only *checks* (axe scan, console errors, cookies) are tested without a browser
by building a `RenderResult` by hand. See `rendered()` in `test_accessibility.py`.

---

## Performance and agentic tests (phase 5)

- `tests/fixtures/pagespeed/mobile.json` is a **trimmed real PageSpeed answer**. Tests
  parse it exactly as the collector would, so there's no API key and no network.
- `test_collector_calls_api_with_key_in_header` fakes Google's API with respx and checks
  that the key is sent in the header and **never** appears in the URL.
- Agentic tests build `AgentProbe` results by hand: an AI agent refused with 403, shown
  a challenge, or given half the page, compared with a normal browser.

---

## Check-up app tests (phase 6)

| File | Covers |
|------|--------|
| `tests/checkups/test_checkups.py` | URL normalising and queueing (`django_capture_on_commit_callbacks` runs `on_commit` code), the queue-down failure, the full task with a **fake engine** (status flow queued → running → done, scores, findings, screenshot, JSON), friendly versus hidden errors, and progress steps |
| `tests/checkups/test_views.py` | Form on home, instant redirect, bad URL error, HTMX polling attributes, the partial, `HX-Refresh` when finished, report at the same URL, failure page, 404, screenshot |

- `pytestmark = pytest.mark.django_db` at the top of a file gives every test in it a
  database (wiped after each test).
- The fake engine is an `async` function with the same signature as `run_audit`. It
  reports progress, checks the status is `running`, and returns a ready-made report from
  `tests/checkups/conftest.py`.

---

## Report tests (phase 7)

`tests/reports/test_reports.py`:

| Area | Tests |
|------|-------|
| branding.yaml | The real file is valid, a wrong category is rejected, the system check reports missing or broken files, the most specific service is chosen |
| Builder | Vital signs split into problems / healthy, the exact three summary sentences, the service mapping (3+ areas also suggest the rebuild), no services for a healthy site, top-risk order, QR SVG |
| Report page | All six sections present, contact links from branding.yaml, Download PDF, share link |
| PDF | Download headers, the stored PDF reused (rendered once), friendly 503 on failure, 404 while not finished, static file lookup (only under `/static/`), and **one real Chromium render** (marked `browser`) |

The check-up tests switch off real PDF rendering with an autouse fixture in
`tests/checkups/conftest.py`, so they stay fast.

---

## Security tests (phase 8)

`tests/security/test_security.py` follows the acceptance checklist: 9 internal or
invalid addresses refused at the form, the 6th check-up from one IP refused (and the
limit is per IP and per hour), 24-hour reuse (also for running check-ups, not counted
towards the limit, and expiring after 24 h), the global cap, the honeypot, Turnstile
(off by default, token verified, fails closed), IP hashing and salts, ignoring
`X-Forwarded-For` unless trusted, every security header, CSRF, and production settings.

**Offline DNS everywhere:** `tests/conftest.py` gives every test an SSRF guard with fake
DNS. `*.test` resolves to a public address and `internal.test` to `10.0.0.7`, so the
real SSRF rules run without touching the internet.

Turnstile tests fake Cloudflare with `respx.mock()` and check what was sent (secret and
token).

---

## Landing and admin tests (phase 9)

| File | Covers |
|------|--------|
| `tests/core/test_landing.py` | Brand and tagline, all form fields, the privacy link, five vital-sign cards, required consent, the lead saved (tidied, lowercased) only with an email, invalid email, the lead kept on reuse, the privacy page content, the footer link |
| `tests/checkups/test_admin.py` | All three admin lists load, search by lead email, the health-band filter, the severity filter, the detail page (report link, findings), no manual adding, CSV export (headers, values, formula neutralised), and `safe_cell` cases |

The `admin_client` fixture creates a superuser and logs in. `client.login(...)` works
like a real login, without the login page.
