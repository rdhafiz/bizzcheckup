# 14. The Audit Engine

`bizzcheckup/engine/` is the part that actually examines a website. It's
**plain Python with no Django**. A test (`tests/engine/test_no_django.py`) fails if
anyone imports Django there. That keeps it fast to test and reusable outside the web
app.

## The flow

```
run_audit(url)                                      runner.py
  │
  ├─ Fetcher (httpx)  ◀── NetGuard checks every request and redirect hop
  │     │                                            fetcher.py, netguard.py
  │     ▼
  ├─ crawl()          homepage → robots.txt → sitemap → up to 10 pages
  │     │                                            crawler.py
  │     ▼
  ├─ AuditContext     everything collected, in one object
  │     │                                            context.py
  │     ├─ collectors add more data (browser, PageSpeed: phases 4–5)
  │     ▼
  ├─ every Check.run(ctx) → list[Finding]            checks/*.py
  │     ▼
  ├─ scoring          check scores → category scores → Business Health Score
  │                                                  scoring.py
  ▼
AuditReport (Pydantic model, saved as JSON)          types.py
```

## Files

| File | What it does |
|------|--------------|
| `types.py` | Data models: `Category`, `Severity`, `Level`, `Band`, `Finding`, `Page`, `RobotsInfo`, `SitemapInfo`, `CrawlResult`, `CheckResult`, `CategoryScore`, `AuditReport` |
| `config.py` | `EngineConfig` (limits) and our User-Agent `BizzCheckup/0.1 (+https://ridwanulhafiz.me)` |
| `urls.py` | `normalize_url()`, `origin()`, `same_origin()`, `absolute()` |
| `netguard.py` | SSRF protection |
| `fetcher.py` | The only code that makes HTTP requests |
| `crawler.py` | Picks and fetches pages |
| `context.py` | `AuditContext`, which checks read from |
| `collectors/probes.py` | Extra requests: internal link statuses, http→https redirect |
| `checks/base.py` | The `Check` base class |
| `checks/seo.py`, `checks/best_practices.py` | The checks: see [Checks reference](15-checks-reference.md) |
| `registry.py` | The list of all checks |
| `scoring.py` | The scoring formula |
| `treatment.py` | Treatment-plan ordering and quick wins |
| `runner.py` | `run_audit()`, which ties everything together |

## Limits (`EngineConfig`)

| Setting | Default | Why |
|---------|---------|-----|
| `max_pages` | 10 | Enough to judge a small business site. Never more than 50 (out of scope). |
| `max_concurrency` | 2 | Polite: never hammer a small business's server |
| `request_timeout` | 15 s | One slow page shouldn't hold everything up |
| (headers) | `Accept`, `Accept-Language` like a browser | Some CDNs (for example Hostinger's) answer **403** to requests without them, even with an honest User-Agent. We still identify as `BizzCheckup/0.1`. |
| `retries` | 2 | Retry temporary failures (timeouts, 429, 502, 503, 504) with growing waits |
| `max_redirects` | 5 | Stop redirect loops |
| `max_page_bytes` | 5 MB | Huge pages are cut off (`truncated=True`) so they can't exhaust memory |
| `total_timeout` | 180 s | The whole check-up is cancelled after 3 minutes |

## SSRF protection (`netguard.py`)

Because strangers type in URLs, an attacker could ask BizzCheckup to "check"
`http://169.254.169.254/` (cloud servers keep secret keys there) or
`http://127.0.0.1:6379` (our Redis). `NetGuard.check_url()` refuses:

- any scheme except `http` and `https`
- any port except 80 and 443
- `localhost`, `*.local` and `*.internal` names
- any host where **even one** of its DNS addresses is not a normal public address.
  That includes loopback, private networks, link-local, carrier NAT, multicast, and
  IPv4 hidden inside IPv6 (`::ffff:127.0.0.1`).

The fetcher follows redirects **itself**, one hop at a time, and runs the guard on
**every hop**. A public site that redirects to `http://10.0.0.1/` is blocked too.

Known limit: the guard checks DNS just before the request, and the connection then
looks the name up again. A malicious DNS server could change the answer in between
(this is called "DNS rebinding"). Running the worker in a network with no access to
internal services removes that risk. See the deployment notes in phase 10.

## Collectors

A collector runs after the crawl and adds data to the `AuditContext` that some checks
need. When it succeeds, it adds its **capability** name. Checks that list that name in
`requires` are skipped (not failed) when the data is missing.

| Collector | Capability | Adds | Used by |
|-----------|------------|------|---------|
| `collect_probes` (`collectors/probes.py`) | `PROBES` | `ctx.probes.http_final_url` (where `http://` ends up); `link_status` (internal link to HTTP status, 0 = unreachable); `link_sources` (which pages contain each link); `llms_txt_text`; `as_ai_agent` / `as_browser` (the homepage fetched with a GPTBot and a Chrome User-Agent: status, length, challenge page?) | `seo.broken_links`, `best_practices.http_redirect`, `agentic.llms_txt`, `agentic.bot_blocking` |
| `collect_render` (`collectors/render.py`) | `RENDER` | `ctx.render`: rendered HTML, visible text length, JPEG screenshot, console errors, cookies (first- or third-party), library versions, axe-core violations and passes, blocked requests | `accessibility.axe_scan`, `best_practices.console_errors`, `best_practices.third_party_cookies`, `best_practices.outdated_libraries`, and all accessibility checks (through `ctx.dom()`) |
| `collect_pagespeed` (`collectors/pagespeed.py`) | `PAGESPEED` | `ctx.pagespeed.mobile` / `.desktop`: Lighthouse score, LCP, CLS, TBT, FCP, speed index, page weight, render-blocking files, off-screen and unsized images, plus real-visitor field data | All performance checks |

**All collectors run at the same time** (`asyncio.gather`), because PageSpeed alone can
take 20–30 seconds. If one fails, its error is logged and the others carry on.

### PageSpeed Insights

`collect_pagespeed` runs Google's mobile and desktop tests in parallel. Notes:

- The API key goes in the `X-Goog-Api-Key` **header**, never the URL. URLs end up in
  logs and error messages, and a key there would leak.
- These requests use `polite=False`, so they don't take one of the two
  "requests at once" slots meant for the audited site.
- They get a longer timeout (`psi_timeout`, 90 s) because Lighthouse runs a full page load.
- With no key, the collector simply does nothing, and the performance checks that need
  it are skipped with a clear note.

Link probing uses cheap `HEAD` requests, falling back to `GET` when a server refuses
`HEAD` (403/405/501). It checks at most `max_link_checks` (50) same-origin links that
robots.txt allows. `run_audit()` uses `DEFAULT_COLLECTORS` unless you pass
`collectors=()`.

## The browser collector (`collectors/render.py`)

It opens the homepage in headless Chromium at 1280×800, waits for it to load (plus up
to 5 seconds for late scripts), then collects the data below. A typical site takes
3–6 seconds.

| Data | How |
|------|-----|
| Rendered HTML and text length | `page.content()`, `document.body.innerText.length` |
| Screenshot | `page.screenshot(type="jpeg", quality=70)`, saved on `AuditReport.screenshot_jpeg` (kept out of the JSON) |
| JavaScript errors | `console.error` messages and uncaught exceptions |
| Cookies | `context.cookies()`. Third-party means a different *site* (`urls.site_domain()`: `www.shop.co.uk` and `shop.co.uk` count as the same site) |
| Library versions | Reads `jQuery.fn.jquery`, Bootstrap's `VERSION`, `angular.version` and lodash `_.VERSION` from the running page |
| Accessibility | Runs axe-core with the WCAG 2.0/2.1/2.2 A and AA rules plus best practices |

**`ctx.dom(page)`**: accessibility checks read the *rendered* homepage when the
browser ran, and the raw HTML otherwise. A site built with JavaScript (React, Vue…)
is judged on what visitors actually see.

### SSRF safety inside the browser

The browser loads images, scripts and frames by itself, so it could be tricked into
visiting internal addresses just like the fetcher. An experiment showed that
**Playwright's request interception does not see redirect hops**. A page could
redirect an image request to `http://10.0.0.1/` without the interception hook noticing.
So `_SafeRouter` handles **every** browser request itself:

1. Run `NetGuard.check_url()` on the URL. If it's blocked, abort the request.
2. Fetch it with `route.fetch(max_redirects=0)`.
3. If the answer is a redirect, check the next address (back to step 1).
4. Hand the final response to the browser with `route.fulfill()`.

On top of that, WebSockets are closed and service workers are disabled, because both
would bypass interception. Blocked addresses are listed in `render.blocked_requests`,
and the console errors they cause are filtered out (they aren't the site's fault).
`tests/engine/test_render.py` proves that the metadata address and a redirect to
`10.0.0.1` are both stopped.

axe-core is run with `page.evaluate()` rather than an injected `<script>` tag. That
way the site's Content-Security-Policy can't block the scan.

If the browser fails (timeout, crash), the collector's error is logged, `RENDER` isn't
added, and browser-only checks are **skipped** with "We couldn't open your site in a
browser". They aren't failed.

**Skip messages say what really happened.** `ctx.unavailable[capability]` holds the
reason a data source is missing. For PageSpeed, "no PageSpeed API key is configured"
appears **only** when there's no key. If a key exists but Google's test failed (timeout,
quota), the note says "Google PageSpeed couldn't measure your site this time".

**Where Chromium lives:** `start.sh` installs it into `.playwright/` inside the project,
and `config/settings/base.py` points Playwright there (`PLAYWRIGHT_BROWSERS_PATH`)
whenever that folder exists. Every process (your terminal, an editor, `start.sh`) then
uses the same browser. The Docker image sets its own path (`/ms-playwright`).

## Crawling rules (`crawler.py`)

1. Fetch the homepage. If it answers with an error (HTTP 400 or higher) or isn't
   HTML, the audit stops with a friendly message.
2. Read `/robots.txt`. A "soft 404" (an HTML page returned with status 200) counts as
   *missing*.
3. Read the sitemaps listed in robots.txt, or `/sitemap.xml`. It follows one level of
   `<sitemapindex>` and reads at most 3 files.
4. Candidate pages are sitemap URLs first, then links on the homepage. Each one must
   be on the same origin, not a file (`.pdf`, `.jpg`, ...), not already chosen, and
   allowed by robots.txt for `BizzCheckup`.
5. Fetch the chosen pages two at a time. A page that fails, or answers with HTTP 400
   or higher, is noted in `errors` instead of being analysed. It doesn't stop the crawl.

The homepage is fetched even if robots.txt disallows it, because the owner asked for
it. Discovering extra pages always respects robots.txt.

## Writing a check

```python
from ..context import AuditContext
from ..types import Category, Finding, Level, Severity
from .base import Check

WHY = "Google uses your main heading to understand what the page is about."


class SingleH1(Check):
    id = "seo.single_h1"            # unique: "<category>.<name>"
    category = Category.SEO
    title = "One main heading"      # shown in the report
    weight = 5                      # 1–10, importance inside the category

    def run(self, ctx: AuditContext) -> list[Finding]:
        count = len(ctx.tree(ctx.homepage).css("h1"))
        if count == 1:
            return [self.passed("Your homepage has exactly one main heading.", WHY)]
        return [
            self.finding(
                Severity.WARN,
                f"Your homepage has {count} main headings instead of one.",
                WHY,
                "Use one <h1> for the page's main topic and <h2>/<h3> for sections.",
                effort=Level.LOW,
                impact=Level.MEDIUM,
                urls=[ctx.homepage.final_url],
            )
        ]
```

That's everything. There's no list to update. **How does it register itself?**
`Check.__init_subclass__` runs automatically whenever Python defines a subclass, and
it calls `default_registry.register(cls)`. `load_builtin_checks()` imports every module
in `checks/`, so every class gets defined.

| Rule | Why |
|------|-----|
| `run()` never fetches anything | Checks stay fast and are testable with local HTML |
| Return at least one finding, or `[]` if the check doesn't apply | `[]` becomes "Not applicable" and is left out of the score |
| Write `message` for a business owner, not a developer | It's what the report shows first |
| `why_it_matters` is the business impact. `how_to_fix` is the technical fix. | This is the brief's tone rule |
| Use `requires = frozenset({RENDER})` if you need the browser | The check is skipped cleanly when that data is missing |
| Set `self.partial` in `run()` for partial credit | e.g. 18 of 20 images with alt text gives 0.9 (`share_score()` helps) |
| Use `on_pages(count, total, has, have)` for messages | "Your homepage has…" or "2 of the 5 pages we checked have…" |

A check that crashes is recorded as `error` and left out of the score. The audit
carries on.

## Scoring

The full formula is in [ARCHITECTURE.md](ARCHITECTURE.md#scoring). Worked example:

| Category | Score | Weight |
|----------|-------|--------|
| Performance | not checked (no API key) | — |
| SEO | 80 | 25 |
| Best practices | 100 | 20 |
| Accessibility | 60 | 15 |
| Agentic | 20 | 15 |

The health score is (25×80 + 20×100 + 15×60 + 15×20) ÷ (25+20+15+15) = 5200 ÷ 75 =
69.3, which rounds to **69: "Needs attention"**.

## Progress

`run_audit(..., on_progress=callback)` awaits `callback(percent, step)` at each stage:

| % | Step |
|---|------|
| 5 | Visiting your website |
| 25 | Taking your website's vital signs |
| 40–90 | Checking Performance / Accessibility / Best practices / SEO / Agentic browsing |
| 95 | Preparing your report |

## Errors the visitor can see

`run_audit` raises `AuditError` with a message that's safe to show:

| Situation | Message (short) |
|-----------|-----------------|
| Private or internal address | "...points to a private or internal network..." |
| Site unreachable | "We couldn't reach your website..." |
| Homepage HTTP 4xx/5xx | "Your website answered with an error (HTTP 500)..." |
| Not a web page | "That address doesn't show a web page..." |
| Over 3 minutes | "Your website took too long to check..." |
