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
| `seo.social_tags` | Social media previews | 3 | `og:title`, `og:description`, `og:image`, `twitter:card` on the homepage | All four | Some or all missing | — |
| `seo.structured_data` | Structured data | 4 | `<script type="application/ld+json">` on all pages | Valid, with `@type` | Item without `@type` | Invalid JSON. (None at all gives **info**.) |
| `seo.broken_links` | Broken links | 6 | Status of internal links (needs PROBES) (partial) | All work | — | Any status ≥ 400 or unreachable |
| `seo.duplicate_titles` | Unique page titles | 4 | Same title on several pages | All unique | Duplicates found | — |

Not applicable (left out of the score): `seo.broken_links` when there are no internal
links, and `seo.duplicate_titles` when only one page was crawled.

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
| `best_practices.outdated_libraries` | Outdated code libraries | 5 | Version numbers in `<script src>` | None outdated | — | jQuery < 3.5, Bootstrap < 4.3.1, AngularJS 1.x, Lodash < 4.17.21 |
| `best_practices.doctype` | Modern page standard | 2 | `<!doctype html>` at the start | Present | Missing | — |
| `best_practices.charset` | Character encoding | 2 | `charset` in the header or the first 1024 bytes | Declared | Missing | — |
| `best_practices.viewport` | Mobile-friendly setup | 7 | `<meta name="viewport">` | Has `width=device-width` | Present but fixed width | Missing (high impact) |

The HTTPS-only checks (`http_redirect`, `mixed_content`, `hsts`) don't apply to a
site that is plain `http://`. The `https` check already reports that problem.

**Coming in phase 4** (these need the real browser): console errors, third-party
cookies, and libraries detected from the running page instead of only from file names.

## Accessibility, Performance, Agentic browsing

Added in phases 4 and 5.

---

## Writing style for findings

Every finding answers three questions, in this order:

1. **`message`**: what we found, in plain words a business owner understands.
   "Your homepage has no title." Not "Missing `<title>` element".
2. **`why_it_matters`**: the business impact: customers, trust, Google, money.
3. **`how_to_fix`**: the technical fix, concrete enough to act on, with an example.

Pages are counted with `on_pages()`: "Your homepage has…" when only one page was
crawled, otherwise "2 of the 5 pages we checked have…".
