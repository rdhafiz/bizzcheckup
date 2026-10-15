# 22. BizzCheckup's own SEO

BizzCheckup checks other websites' SEO, so its own pages should pass the same checks.
This page explains every tag and file that tells search engines, social networks and AI
assistants what BizzCheckup is.

## The idea: one description per page

Each view describes its page with a **`PageMeta`** (`bizzcheckup/core/seo.py`):

| Field | What it's for | Example |
|-------|---------------|---------|
| `title` | The `<title>`: the blue link in Google, the browser tab | "Privacy policy \| BizzCheckup" |
| `description` | The grey text under the link (120–160 characters show in full) | "How BizzCheckup handles…" |
| `path` | The page's one true address → the **canonical** link | `/privacy/` |
| `robots` | May search engines list it? | `index, follow` or `noindex, nofollow` |
| `og_type` | `website`, or `article` for a text page | `article` |
| `image` | The picture shown when the link is shared | `img/og-image.png` |
| `updated` | When the content last changed | the legal pages' date |
| `schema` | Structured data (JSON-LD) | Organization, FAQPage, … |

`templates/partials/seo.html` turns it into tags, and `base.html` includes it in every
page's `<head>`. A page that doesn't describe itself gets a default from the context
processor `core.context_processors.seo`, so **no page is ever without tags**.

```python
# core/views.py
return render(request, "core/home.html", {..., "meta": seo.home_meta(checks, faq)})
```

### Why every address uses SITE_URL

The canonical link, the share picture, the sitemap and robots.txt are all built from the
`SITE_URL` setting (`https://bizzcheckup.ridwanlab.xyz` on the server), not from the
address the page was opened with. The site can be reached through localhost, the
Cloudflare Tunnel or a typo'd `www.`; search engines should only ever see one address.

## The tags, one by one

| Tag | Read by | Why |
|-----|---------|-----|
| `<title>`, `<meta name="description">` | Google, Bing | The search result itself |
| `<link rel="canonical">` | Search engines | "This is the real address of this page", so copies don't compete |
| `<meta name="robots">` | Search engines | `noindex` keeps private pages out of results |
| `og:title`, `og:description`, `og:image`, `og:url`, `og:type` | Facebook, LinkedIn, WhatsApp | The card shown when the link is shared ([Open Graph](https://ogp.me)) |
| `twitter:card` = `summary_large_image` | X | The same card, with a big picture |
| `theme-color` (light and dark) | Phone browsers | Colours the address bar in the brand's colours |
| `apple-touch-icon` | iPhone, Android | The icon when the site is added to the home screen |
| `<script type="application/ld+json">` | Google, AI assistants | Facts in a fixed format (below) |

## Structured data (JSON-LD)

**JSON-LD** describes the page in the vocabulary of [schema.org](https://schema.org), which
Google, Bing and AI assistants all understand. Each page sends a `@graph`, a list of facts:

| Page | Facts |
|------|-------|
| Homepage | `Person` (who runs it, from `branding.yaml`), `WebSite`, `WebApplication` (free, so `price: 0`), `WebPage`, `FAQPage` |
| Legal pages | `WebPage` (with `dateModified`), `BreadcrumbList` (Home › Privacy policy) |

The homepage's **FAQ** ("Before you start") and its `FAQPage` data come from **one list**,
`core.views.home_faq()`. Google requires structured data to match what visitors see; with
one list they can never disagree. The numbers in the answers (how many checks, pages, per
hour) come from the settings and the engine, so they never go stale.

**It's safe with our Content Security Policy.** The CSP forbids inline scripts, but a
`type="application/ld+json"` block is *data*: browsers never run it. `PageMeta.json_ld`
also escapes `<`, `>` and `&`, so no value could ever close the tag early.

## Private pages: never in search results

Reports are private links. Everything under `/checkups/` (reports, progress pages, PDFs,
pictures, unsubscribe pages), `/admin/`, `/styleguide/` and `/healthz/`:

1. gets `<meta name="robots" content="noindex, nofollow">` (`seo.is_private()`);
2. gets the **header** `X-Robots-Tag: noindex, nofollow` (`SecurityHeadersMiddleware`),
   which also covers PDFs and pictures, since they have no `<head>`;
3. is listed as `Disallow` in robots.txt.

A shared report still **previews** nicely in a chat: its `og:title` is "shop.com: health
score 72/100" and its `og:image` is the report's share card (`/checkups/<id>/share.png`).
That's only for people who received the link, not for search engines.

## Files at the root of the site

| Address | What it is | Code |
|---------|-----------|------|
| `/robots.txt` | What crawlers may read (everything public), what not (`/checkups/`, …), and where the sitemap is | `core.views.robots_txt` |
| `/sitemap.xml` | Every public page, with the date the policies last changed | `core/sitemaps.py` |
| `/llms.txt` | A Markdown guide to the site for AI assistants ([llmstxt.org](https://llmstxt.org)) | `templates/core/llms.txt` |
| `/.well-known/security.txt` | How to report a security problem ([RFC 9116](https://www.rfc-editor.org/rfc/rfc9116)); its `Expires` date moves forward by itself | `core.views.security_txt` |

## The share picture and the icon

`static/img/og-image.png` (1200 × 630) and `static/img/apple-touch-icon.png` (180 × 180)
are drawn from `templates/core/og_image.html` by a command, in the same offline Chromium
as the PDF:

```bash
SITE_URL=https://bizzcheckup.ridwanlab.xyz python manage.py make_seo_images
```

(`SITE_URL` makes the picture show the real domain.) The PNGs are committed to git: run the
command again after changing that page, the branding or the number of checks.

## Checking it yourself

- **Google:** [Rich Results Test](https://search.google.com/test/rich-results), paste the
  homepage address: it should find the FAQ and the web app.
- **Link previews:** [opengraph.xyz](https://www.opengraph.xyz) or LinkedIn's
  [Post Inspector](https://www.linkedin.com/post-inspector/) show the card.
- **Tests:** `tests/core/test_seo.py` checks the tags, the JSON-LD, the private pages,
  the crawl files and the pictures' sizes.
- **BizzCheckup itself:** run a check-up of your own site once it's live.
