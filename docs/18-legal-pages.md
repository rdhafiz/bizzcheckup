# 18. Legal pages and the footer

BizzCheckup has five legal pages, linked from the footer on every page:

| Page | Address | What it says |
|------|---------|--------------|
| **Privacy policy** | `/privacy/` | What we collect (the address, optional name and email, a scrambled IP), why, who sees a report, how long we keep data, how to ask for deletion |
| **Terms of service** | `/terms/` | The rules: free service, fair use and limits, reports are "as is", liability limits, the law of the operator's country |
| **Cookie policy** | `/cookies/` | Every cookie and browser-storage key the site uses, and why |
| **Acceptable use** | `/acceptable-use/` | Only check websites you may check; no attacks, scripts or reselling; how we visit sites; how owners can opt out |
| **Disclaimer** | `/disclaimer/` | Scores are automated estimates, not a security audit or legal compliance proof |

> These texts are a solid, honest starting point written to match what the app really
> does. They are **not legal advice**: if the service grows or earns money, have a lawyer
> in your country review them.

## Where the details come from

Nothing personal is typed into the templates. It comes from two places:

1. **`branding.yaml`**, section `legal`:

   ```yaml
   legal:
     operator: Ridwanul Hafiz   # who runs the service and is responsible for it
     country: Bangladesh        # whose law the terms follow
     updated: 2026-10-08        # "Last updated" date on every legal page
   ```

   The email address, name and links come from the rest of `branding.yaml`.

2. **The settings**, for numbers that can change: `CHECKUP_RATE_LIMIT_PER_HOUR`,
   `CHECKUP_MAX_PAGES` and `CHECKUP_REUSE_HOURS`. If you change a limit in `.env`, the
   terms change with it, so the text never promises something the app doesn't do.
   Cloudflare Turnstile is only mentioned when it is switched on.

**When you change what the app collects or stores** (a new cookie, a new form field,
a new outside service), update the matching page *and* the `updated` date.

## How the pages are built (MVC)

| Layer | File | What it does |
|-------|------|--------------|
| URL | `bizzcheckup/core/urls.py` | Five addresses, all pointing at one view. The page name is passed as an extra argument: `path("terms/", views.legal_page, {"page": "terms"}, name="terms")` |
| View | `bizzcheckup/core/views.py` → `legal_page()` | Picks the template `core/legal/<page>.html` and passes the limits from the settings. `LEGAL_PAGES` lists the pages for the side menu |
| Template | `templates/core/legal/_layout.html` | The shared layout: title band with the date, side menu (the open page is marked with `aria-current="page"`), the text |
| Template | `templates/core/legal/<page>.html` | Only the words. Each page fills the blocks `legal_title`, `heading`, `lead` and `body` |
| Model | `bizzcheckup/reports/branding.py` → `Legal` | Checks the `legal` section of `branding.yaml` (a wrong date fails `manage.py check`) |

**Why one view for five pages?** They differ only in their words. One view plus a template
per page avoids five copies of the same Python code.

**Template inheritance** goes three levels deep here: `base.html` (header, footer) →
`legal/_layout.html` (title band, menu) → `legal/terms.html` (the words). Each level fills
the `{% block %}`s of the one above it.

## The footer (`templates/partials/footer.html`)

Included at the bottom of `base.html`, so it appears on every page. It's hidden when
printing and in the PDF.

| Column | Contents |
|--------|----------|
| Brand | Logo, one-line description, "Start a free check-up" button |
| Product | Links to the homepage sections (`/#start`, `/#signs-title`, ...) |
| Legal | The five legal pages |
| Get in touch | Email, WhatsApp, website, and round icon links to GitHub, portfolio, CV and website |
| Bottom bar | © year and operator, app version, "Back to top" |

The footer needs `branding` on *every* page, not only on pages whose view passes it. So
`bizzcheckup/core/context_processors.py` adds it to every template automatically.
`load_branding()` is cached, so this costs nothing: the file is only read again when it
changes.

The footer is always dark: it has the class `on-dark`, which switches that area to the
dark-mode colours (see [Frontend & brand](11-frontend-and-brand.md)). The year comes from
Django's `{% now "Y" %}` tag, so it never needs updating.

## Tests

`tests/core/test_legal.py` checks that every page opens, shows the operator and links to
all the others; that the terms use the country and the real limits from the settings; that
the cookie policy names every cookie and storage key; and that the footer is on every page.
