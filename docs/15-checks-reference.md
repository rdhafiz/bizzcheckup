# 15. Checks Reference

Every check BizzCheckup runs: what it looks at, and when it passes, warns or fails.
Weights (1–10) say how much a check counts **within its category**. See
[ARCHITECTURE.md](ARCHITECTURE.md#scoring) for how scores are calculated.

Severity meanings:

| Severity | Meaning | Score |
|----------|---------|-------|
| **pass** | Healthy | 1.0 |
| **info** | Worth knowing; no penalty | 1.0 |
| **warn** | Should be fixed | 0.5 |
| **fail** | Must be fixed | 0.0 |

"Partial" means the check gives partial credit by page: 1 bad page out of 4 scores
0.75 instead of 0.

---

## SEO (`bizzcheckup/engine/checks/seo.py`)

| Id | Title | Weight | Looks at | Pass | Warn | Fail |
|----|-------|--------|----------|------|------|------|
| `seo.title` | Page titles | 8 | `<title>` on every page (partial) | 10–60 characters | Under 10 or over 60 | Missing (high impact) |
| `seo.meta_description` | Search result descriptions | 6 | `<meta name="description">` (partial) | 50–160 characters | Missing (medium impact) or wrong length (low impact) | — |
| `seo.single_h1` | Main heading | 5 | `<h1>` count per page (partial) | Exactly one | None, or more than one | — |
| `seo.canonical` | Preferred page address | 3 | `<link rel="canonical">` on the homepage | One absolute URL on the same domain | Missing, several, or relative | Points to **another domain** (high impact) |
| `seo.robots_txt` | robots.txt | 5 | `/robots.txt` | Exists, Googlebot allowed | Missing | Blocks Googlebot from the homepage (high impact) |
| `seo.sitemap` | Sitemap | 4 | Sitemaps from robots.txt or `/sitemap.xml` | Found with pages (plus info if robots.txt doesn't mention it) | Missing or empty | — |
| `seo.indexable` | Visible to Google | 9 | `noindex` in meta robots, meta googlebot or the `X-Robots-Tag` header | No noindex | — (other pages with noindex give **info**) | Homepage is noindex (high impact) |
| `seo.social_tags` | Link previews | 4 | `og:title`, `og:description`, `og:image`, `twitter:card` on **every page** (partial); the homepage's `og:image` is downloaded to check it (needs PROBES for that part) | All four on every page, and the picture loads | Tags missing, `og:image` not a full address, or the picture is missing, not an image or over 5 MB. Each page gets a ready-made block of tags. | — |
| `seo.page_schema` | Page schema | 4 | JSON-LD on every page, compared with what that **kind** of page should have (see below) | Every page has its expected types with their required properties (only optional extras missing gives **info**) | A type is missing, or a required property is missing (medium impact on the homepage, low elsewhere) | Invalid JSON (search engines ignore the whole block) |
| `seo.broken_links` | Broken links | 6 | Status of internal links (needs PROBES) (partial) | All work | — | Any status ≥ 400 or unreachable, with a list of the pages each one is on |
| `seo.duplicate_titles` | Unique page titles | 4 | Same title on several pages | All unique | Duplicates found | — |

### Technical SEO (`bizzcheckup/engine/checks/technical_seo.py`)

These go deeper than the basic checks above: each one reviews every page and adds a
**page-by-page breakdown** (a `Snippet`) to the report, so the owner sees exactly what
to change where.

| Id | Title | Weight | Looks at | Pass | Info | Warn | Fail |
|----|-------|--------|----------|------|------|------|------|
| `seo.heading_structure` | Heading structure | 4 | Every heading (H1–H6) per page, as an outline (partial) | Clear outline | Only notes: no H1, several H1s, skipped levels, an H1 over 70 characters, a 300+ word page without H2s | Empty headings, the same H1 on several pages, or the H1 not the first heading | — |
| `seo.image_seo` | Image descriptions and file names | 4 | Every `<img>` (partial) | All described | Only camera-style file names (`IMG_4821.jpg`) or alt text over 125 characters | Missing alt, alt that is a file name, or a word like "image" | — |
| `seo.url_structure` | Clean page addresses (URLs) | 3 | Crawled pages and internal links (partial) | All clean | Over 115 characters, more than 4 folders deep, many `?` parameters, technical endings (`.php`) | Capital letters, underscores, spaces, double slashes, session ids, or links to the `http://` version. Each comes with a suggested clean address. | — |
| `seo.meta_tags` | Essential meta tags | 4 | `title`, `description`, `viewport`, `charset`, `canonical` and `<html lang>` on every page, plus meta refresh (partial) | All present | Only the language missing | Any of the five core tags missing (with a complete `<head>` block per page), or a meta refresh | — |
| `seo.broken_external_links` | Links to other websites | 3 | Up to 30 links to other sites (needs PROBES) (partial) | All work | — | Any 404/410/5xx or unreachable. 401, 403, 429 and 999 (LinkedIn) mean "robots not allowed", so they don't count. | — |
| `seo.broken_images` | Broken images | 4 | Up to 40 images on any site (needs PROBES) (partial) | All load | — | — | Any that don't load |

Not applicable: `heading_structure` without headings, `image_seo` without images, and
the two probe checks when nothing was probed. Requests to other websites have a short
timeout (`external_timeout`, 8 s), run 4 at a time, and share a 30-second budget
(`outside_budget`): whatever hasn't answered by then is left out, never counted as broken.

Not applicable (left out of the score): `seo.broken_links` when there are no internal
links, and `seo.duplicate_titles` when only one page was crawled.

### Page schema in detail (`bizzcheckup/engine/schema.py`)

Schema (structured data, JSON-LD) tells Google and AI assistants *what* a page is: a
business, an article, a product, an FAQ. The check works in three steps for **each page**:

1. **What kind of page is this?** `classify()` looks at the address (`/blog/...`,
   `/products/...`, `/contact`), `og:type`, product price tags and question headings.
2. **What should it have?** Each kind has a list of expected types:

   | Kind | Expected types |
   |------|----------------|
   | Homepage | `Organization` (or a more specific one, e.g. `Bakery`) + `WebSite` |
   | About / Contact | `AboutPage` / `ContactPage` |
   | Article (blog post) | `Article` (or `BlogPosting`, `NewsArticle`) + `BreadcrumbList` |
   | Product | `Product` + `BreadcrumbList` |
   | Service | `Service` + `BreadcrumbList` |
   | FAQ | `FAQPage` |
   | Listing (`/blog`, `/products`) | `CollectionPage` + `BreadcrumbList` |
   | Any other page | `WebPage` + `BreadcrumbList` |

   Each type has **required** properties (Google needs them, e.g. a product's `offers`
   with `price` and `priceCurrency`) and **recommended** ones (nice extras, e.g. a logo).
3. **The suggestion.** If something is missing, the check builds the **complete** JSON-LD
   for that page: it keeps everything the site already has, fills in what it can read
   from the page (name, title, description, image, phone, email, social links, FAQ
   questions and answers, breadcrumbs from the address) and marks the rest
   `"REPLACE: ..."`, so the owner knows exactly what to fill in.

The suggestions travel on the finding as `snippets` (a `Snippet` has a `title` and the
`code`), one per page, and the report shows each one with a **Copy** button.

## Best practices (`bizzcheckup/engine/checks/best_practices.py`)

| Id | Title | Weight | Looks at | Pass | Warn | Fail |
|----|-------|--------|----------|------|------|------|
| `best_practices.https` | Secure connection (HTTPS) | 10 | Final homepage URL | `https://` | — | `http://` only (high impact) |
| `best_practices.http_redirect` | http:// sends visitors to https:// | 6 | Where `http://<host>/` ends up (needs PROBES) | Redirects to https | Stays on http. (No answer on http gives **info**.) | — |
| `best_practices.mixed_content` | Mixed content | 7 | `http://` scripts, styles, frames, images and media on https pages | None | Images or media only | Scripts, styles or frames (high impact) |
| `best_practices.hsts` | Always-secure setting (HSTS) | 4 | `Strict-Transport-Security` header | `max-age` ≥ 180 days | Missing or too short | — |
| `best_practices.csp` | Content Security Policy | 3 | `Content-Security-Policy` header or meta tag | Present | Missing. (Report-only gives **info**.) | — |
| `best_practices.nosniff` | File type protection | 2 | `X-Content-Type-Options` | `nosniff` | Missing | — |
| `best_practices.frame_protection` | Protection from being framed | 3 | `X-Frame-Options`, or CSP `frame-ancestors` | DENY / SAMEORIGIN / frame-ancestors | Missing | — |
| `best_practices.referrer_policy` | Referrer privacy | 2 | `Referrer-Policy` header or meta tag | A safe policy | Missing, or `unsafe-url` / `no-referrer-when-downgrade` | — |
| `best_practices.outdated_libraries` | Outdated code libraries | 5 | Version numbers in `<script src>`, plus versions read from the running page when the browser ran | None outdated | — | jQuery < 3.5, Bootstrap < 4.3.1, AngularJS 1.x, Lodash < 4.17.21 |
| `best_practices.doctype` | Modern page standard | 2 | `<!doctype html>` at the start | Present | Missing | — |
| `best_practices.charset` | Character encoding | 2 | `charset` in the header or the first 1024 bytes | Declared | Missing | — |
| `best_practices.viewport` | Mobile-friendly setup | 7 | `<meta name="viewport">` | Has `width=device-width` | Present but fixed width | Missing (high impact) |
| `best_practices.console_errors` | JavaScript errors | 4 | Errors in the browser console (needs RENDER) | None | Any (duplicates counted once; up to 3 shown) | — |
| `best_practices.third_party_cookies` | Third-party cookies | 3 | Cookies from other sites when the homepage loads (needs RENDER) | None | Any, with the company domains listed | — |
| `best_practices.mobile_layout` | Fits phone and tablet screens | 7 | The homepage opened as a 390 px phone and an 820 px tablet (needs RENDER) | No shrinking, no sideways scrolling | The same problems on the tablet | On the phone: the desktop page shown shrunk (no mobile layout), or wider than the screen, with the elements sticking out listed (high impact) |
| `best_practices.tap_targets` | Easy to tap on phones | 4 | Links and buttons on the phone view smaller than 24 × 24 px (WCAG 2.5.8); links inside a sentence are exempt (partial) | None too small | 1–2 too small (**info**), with examples | 3 or more, or 10%+ | — |
| `best_practices.mobile_text_size` | Readable text on phones | 4 | Share of visible text smaller than 12 px on the phone view | Under 5% | 5–25% (**info**) | 25% or more, or the page is shown shrunk | — |

The HTTPS-only checks (`http_redirect`, `mixed_content`, `hsts`) don't apply to a
site that is plain `http://`. The `https` check already reports that problem.

## Accessibility (`bizzcheckup/engine/checks/accessibility.py`)

The first five checks read every crawled page, using the browser-rendered homepage
when available (`ctx.dom()`).

| Id | Title | Weight | Looks at | Pass | Warn | Fail |
|----|-------|--------|----------|------|------|------|
| `accessibility.image_alt` | Image descriptions | 8 | `<img>` without an `alt` attribute (partial). `alt=""` is fine for decoration. | All have alt | — | Any missing (high impact) |
| `accessibility.html_lang` | Page language | 5 | `<html lang>` on the homepage | Valid code (`en`, `en-GB`, `bn`) | Invalid code | Missing |
| `accessibility.heading_order` | Heading structure | 3 | Heading levels in page order (partial) | No skipped levels | A skip such as H2 to H4 | — |
| `accessibility.form_labels` | Form field labels | 8 | `input`/`select`/`textarea` (not hidden or buttons) need a `<label for>`, a wrapping `<label>`, `aria-label`, `aria-labelledby` or `title`. A placeholder is **not** a label. (partial) | All labelled | — | Any unlabelled (high impact) |
| `accessibility.accessible_names` | Link and button names | 6 | `<a href>`, `<button>` and submit inputs need text, `aria-label`, `title` or an image alt (partial) | All named | Any nameless | — |
| `accessibility.axe_scan` | Automated accessibility scan | 10 | axe-core on the rendered homepage, **excluding** rules the checks above already cover (needs RENDER) | Nothing found | Moderate issues | Serious or critical issues (high impact). Minor issues give **info**. |

The axe scan gives **one finding per failing rule**, with plain-language business
impact for common rules (contrast, landmarks…) and a link to Deque's step-by-step fix
guide. Under **"Where on the page"** it shows up to 5 of the failing elements: a
screenshot of the spot with the element outlined in red (up to 10 pictures per
check-up), axe's explanation in words, the element's HTML and its CSS selector. For
colour contrast the report also draws the text in its real colours with the current and
required ratio. Its partial score is (rules checked − penalties) ÷ rules checked, where the
penalties are critical 1.0, serious 0.7, moderate 0.3 and minor 0.1.

Not applicable: `image_alt` with no images, `heading_order` with no headings,
`form_labels` with no form fields, and `accessible_names` with no links or buttons.

## Performance (`bizzcheckup/engine/checks/performance.py`)

The first four need PageSpeed Insights (`PSI_API_KEY`). Without a key they're
**skipped**, the category says "Speed wasn't measured because no PageSpeed API key is
configured", and the Business Health Score re-balances without it. The last three
also work from the HTML alone, and use PageSpeed's more precise data when it's there.

| Id | Title | Weight | Looks at | Pass | Warn | Fail |
|----|-------|--------|----------|------|------|------|
| `performance.mobile_speed` | Speed on phones | 10 | Lighthouse mobile score (the score *is* the check score) | ≥ 90 | 50–89 | < 50 (high impact) |
| `performance.desktop_speed` | Speed on computers | 5 | Lighthouse desktop score | ≥ 90 | 50–89 | < 50 (high impact) |
| `performance.core_web_vitals` | Core Web Vitals | 8 | **Real-visitor** data (Chrome UX Report, 28 days) when Google has it, otherwise the lab test (partial) | All good | Any "needs improvement" | Any "poor" (high impact) |
| `performance.page_weight` | Page weight | 4 | Total bytes downloaded (mobile) | ≤ 2 MB | ≤ 4 MB | > 4 MB |
| `performance.image_dimensions` | Image sizes declared | 3 | `<img>` without both `width` and `height` (partial) | All sized | Any unsized | — |
| `performance.lazy_images` | Images load when needed | 3 | PageSpeed's off-screen images, or pages with 4+ images and no `loading="lazy"` | Fine | Images load too early | — |
| `performance.render_blocking` | Files that block the first screen | 4 | PageSpeed's render-blocking files, or `<head>` scripts without `defer`/`async`/`type="module"` | None | Any (medium impact if they cost ≥ 0.5 s) | — |

Core Web Vitals thresholds (Google's own):

| Metric | Means | Good | Poor |
|--------|-------|------|------|
| LCP | Main content visible | ≤ 2.5 s | > 4 s |
| CLS | Page jumping around | ≤ 0.1 | > 0.25 |
| INP | Reaction to taps (real visitors only) | ≤ 200 ms | > 500 ms |
| TBT | Page frozen by scripts (lab stand-in for INP) | ≤ 200 ms | > 600 ms |
| FCP | Anything visible at all | ≤ 1.8 s | > 3 s |

## Agentic browsing (`bizzcheckup/engine/checks/agentic.py`)

Can AI assistants (ChatGPT, Claude, Perplexity, Google's AI answers) find, read and
recommend the business?

| Id | Title | Weight | Looks at | Pass | Warn | Fail |
|----|-------|--------|----------|------|------|------|
| `agentic.llms_txt` | AI guide (llms.txt) | 5 | `/llms.txt` as real text, not an HTML soft-404 (needs PROBES) | Present (plus **info** if it lacks a `# Name` heading) | Missing | — |
| `agentic.ai_crawlers` | AI crawlers allowed | 8 | robots.txt rules for OAI-SearchBot, PerplexityBot, GPTBot, ClaudeBot | All allowed, or no robots.txt | — (blocking **training** bots GPTBot/ClaudeBot gives **info**: a valid choice) | Blocking **search** bots (high impact) |
| `agentic.bot_blocking` | Not blocked by firewall | 8 | The homepage fetched as an AI agent vs as a normal browser (needs PROBES) | Same page | Everyone blocked, or AI gets < 50 % of the page | AI refused, unanswered, or challenged while browsers get through (high impact) |
| `agentic.structured_data` | Machine-readable business facts | 5 | JSON-LD with an `@type` on the homepage | Present | Missing | — |
| `agentic.landmarks` | Clear page structure | 4 | `main`, `nav`, `header`, `footer` (or ARIA roles) (partial) | All four | Some missing (medium impact if `main` is missing) | — |
| `agentic.named_controls` | Buttons AI agents can use | 4 | Homepage links and buttons with an accessible name (partial) | All named | Any nameless | — |
| `agentic.content_without_js` | Content readable without JavaScript | 8 | Raw-HTML text ÷ rendered text (needs RENDER) (partial) | ≥ 70 % | 30–69 % | < 30 % (high impact) |

**Bot-protection detection:** a response counts as a "challenge" when Cloudflare sends
`cf-mitigated: challenge`, or when a short page or an error page (403/429/503)
contains phrases like "Just a moment..." or "verify you are human". A normal homepage
that mentions "captcha" (for example on a contact form) doesn't count. Even then, the
check only fails when the AI agent is treated **differently** from a browser.

---

## Writing style for findings

Every finding answers three questions, in this order:

1. **`message`**: what we found, in plain words a business owner understands.
   "Your homepage has no title." Not "Missing `<title>` element".
2. **`why_it_matters`**: the business impact: customers, trust, Google, money.
3. **`how_to_fix`**: the technical fix, concrete enough to act on, with an example.

Pages are counted with `on_pages()`: "Your homepage has…" when only one page was
crawled, otherwise "2 of the 5 pages we checked have…".
