# 16. The Health Report (web page and PDF)

A finished check-up is shown at its own address, `/checkups/<uuid>/`, as the
**BizzCheckup Health Report**. The **PDF** at `/checkups/<uuid>/report.pdf` uses the
*same* template sections, so the two always match.

## Look: the homepage's theme

The report opens with a **dark band** (`_hero.html`) in the homepage hero's style: a
picture behind a dark backdrop (with the same slow parallax), the green "Health
report" badge, the domain in the green gradient with its swoosh, the diagnosis and the
actions, and a frosted panel with the score gauge and four counters (the homepage's
glossy round icons, one colour each). The header sits on the photo, as on the homepage.
In the PDF this band is the cover.

**The picture is the website's own preview image** (`og:image`, or `twitter:image`):
the one the engine downloaded and checked for the link preview check, served from our
own site (`/checkups/<id>/images/link_preview/`), so the report never loads anything
from the audited site. A website without a usable one gets a demo picture,
`static/img/report-hero-demo.svg`: a browser window with a score ring, a phone and the
heartbeat line, in the brand colours. It's an `<img>` rather than a CSS background,
because the address changes per report and our Content Security Policy forbids inline
styles. The backdrop is darker on the text side and lighter behind the score panel, and
blurs the picture a little so its own text doesn't compete with ours.

Below it, the dashboard sits on the paper background with the homepage's soft colour
blobs. Every section opens like the homepage's: a dash eyebrow ("Diagnosis") and a big
title with one highlighted word ("Fix these **first**"). Headings reveal word by word
and cards rise in, one after another, with the homepage's motion (`data-reveal`,
`static/js/motion.js`, explained in [Motion](19-motion.md)): no motion for visitors who
prefer reduced motion, none in the PDF, and everything is visible without JavaScript.

## Layout: a dashboard with a sidebar

On a computer the report is a **dashboard** (`templates/reports/report.html`):

- **Sidebar** (`_sidebar.html`, sticky): the Business Health Score gauge, the sections
  with how many items each has, and the five **vital signs** with their score and a bar.
  Clicking a vital sign shows only its issues. While you scroll, the section you're
  reading is highlighted (`setUpSectionHighlight()` in `report.js`).
- **Main column**: the sections below. The actions (Download PDF, Copy share link,
  Check again now) sit next to the domain name.

On phones and tablets (under 1024 px) the sidebar is hidden: a sticky bar keeps the
score and the section links in view, and the score and vital signs appear inside the
overview instead. The PDF has no sidebar either; it shows them in the overview too.

## The sections (`templates/reports/_sections.html`)

Each issue appears **once**. The order follows the questions a business owner asks:

| # | Section (`id`) | Question it answers | Shows | Comes from |
|---|----------------|---------------------|-------|------------|
| 1 | **Overview** (`#overview`, the dark band) and **At a glance** (`#snapshot`) | *How healthy is my website?* | The band: domain, URL, the **diagnosis** (one-sentence verdict), the actions, the score with 4 counters (need treatment, worth fixing, quick wins, checks passed). At a glance: the Desktop / Tablet / Phone screenshots, the link preview card, what we checked (pages and checks) and any notes; the vital signs on phones, tablets and paper | `ReportView.verdict`, `.needs_treatment`, `.worth_fixing`, `.healthy_count` |
| 2 | **Fix these first** (`#fix-first`) | *What should I fix first?* | Up to 3 cards: the problem and what it costs you, with "See how to fix it", which opens that issue in the list (in the PDF: the solution itself) | `builder.top_risks()`, `ReportView.risk_rows` |
| 3 | **All issues** (`#issues`) | *What do I do, and in what order?* | **One list** of every problem, quick wins first (plan order), then the "good to know" notes. Each row has a tick box and opens to show *why it matters*, *how to fix it*, *where* and any ready-made fix. Filters by vital sign and by severity; the progress bar counts what's ticked. Vital signs that weren't checked say why. Passed checks are folded under "What's healthy", grouped by vital sign | `ReportView.issues` (`builder.issue_rows()`), `.issue_filters`, `engine.treatment.build_treatment_plan()` |
| 4 | **All pages** (`#pages`) | *Which pages were checked?* | Every page address found (sitemap and links): checked ones first with a "Checked" badge, the first 30 shown and the rest behind "Show all" ("and N more" in the PDF). When some weren't checked, the **full check-up proposal** sits beside the list | `ReportView.all_pages`, `.unchecked_count`, `branding.full_audit` |
| 5 | **How {first name} can help** (`#help`) | *Who can fix this?* | Each area that needs care (score < 90) mapped to the most specific service in `branding.yaml`, plus the broad "rebuild" service when 3+ areas need care, and the call to action | `builder.recommend_services()` |
| 6 | **Contact** (`#contact`) | *How do I reach them?* | Photo, name, title, intro, highlights, email, WhatsApp, website, GitHub, CV, portfolio, QR code, footer note | `branding.yaml`, `builder.qr_code_svg()` |

### The issue list (`_issue.html`, `builder.IssueRow`)

Every row has a **key** that stays the same within a report, such as `seo-title-1` (the
check id, then a number when a check gives more than one finding). It's used for:

- the row's anchor, `#issue-seo-title-1`, which "See how to fix it" links to;
- the tick box (`data-plan-key`). Ticks are saved per report in the browser's
  `localStorage`, and a ticked row turns green and is struck through.

The filters are plain buttons with `aria-pressed`. Rows carry `data-category` and
`data-severity`, and `setUpIssueFilters()` hides the ones that don't match. Without
JavaScript the filters stay hidden and every issue shows. In the PDF every row is open,
and the tick box is an empty square to tick by hand.

Every finding shows its severity ("Needs treatment", "Worth fixing", "Good to know",
"Healthy") as **an icon, a colour and a word** (never colour alone), plus impact, effort,
**why it matters for your business**, **how to fix it**, and the affected URLs (the first
5, then "and N more").

When a check can write the fix itself (**Page schema**, **Essential meta tags**, **Link
previews**), the issue also shows **"Ready to use"** code blocks, one per page, each folded under its page and what's
missing. A **Copy** button copies the code (`static/js/report.js`, `setUpCopyCode()`).
If the browser blocks the clipboard, the code is selected instead and the button says
"press Ctrl+C". In the PDF the blocks are open, the button is hidden and long lines wrap.
Checks that explain rather than fix (heading outlines, image lists, URL suggestions,
broken links with the pages they're on) use the same blocks under **"Page by page"**
(`Snippet.language == "text"`).

Accessibility scan findings use **"Where on the page"** (`Snippet.language ==
"element"`): each element gets its screenshot with a red outline (`Snippet.image`),
"What's wrong" in words (`Snippet.note`) and, below, its HTML and CSS selector. For
colour contrast the `contrast` template filter reads the two colours and ratios from the
explanation and draws a sample in an SVG. (An SVG's `fill` is an attribute, not a
`style`, so the Content Security Policy allows it; the filter only accepts real hex
colours.)

### Device screenshots (`templates/reports/_devices.html`)

The overview shows the homepage on a **computer, a tablet and a phone** as tabs
(`setUpDeviceTabs()` in `report.js`, the standard ARIA tabs pattern: arrow keys, Home
and End). Without JavaScript all three are shown one under the other, and the PDF
shows the computer view with the tablet and phone side by side underneath. The tablet
and phone pictures sit in a box the same shape as the desktop one, so switching tabs
doesn't move the page. The tabs only appear when those pictures exist. Hidden views
use the browser's own `hidden` attribute, so the tabs work even if an old stylesheet is
cached; when printing, `beforeprint` shows all three and `afterprint` restores the tab.

### Link preview card (`templates/reports/_link_preview.html`)

At the top of the SEO section: how the homepage looks when shared (picture, domain,
title, description), from `AuditReport.link_preview`. The picture is the one the
engine downloaded and checked, served from **our** site (`/checkups/<id>/images/link_preview/`),
so the report never loads anything from the audited site (the CSP forbids it, and it
would tell that site who is reading the report).

## The report's design, and why

| Pattern | Where | Why |
|---------|-------|-----|
| **Sticky bar** with the score and jump links | `report.html`, `.report-bar` | A long report needs a map. The links are real `#anchors`, so they also work without JavaScript; `scroll-mt-24` stops headings hiding under the bar |
| **Gauge** for the one big number | `reports/_gauge.html` | One KPI reads best as a gauge. `pathLength="100"` makes the score the arc length, no maths |
| **Bullet bars** with a line at 90 | `reports/_bullet.html` | Five scores compared against one target ("Healthy"). The bar is an SVG `<rect width="72">` because our CSP forbids `style="width:72%"` |
| **Problem → cost → solution** cards | Top risks | Answers "what's wrong and what do I do" without scrolling |
| **Expandable rows** (`<details>`) | `reports/_issue.html` | 40+ findings at full length make a wall of text. One line each, details on demand. `<details>` is native HTML: keyboard and screen-reader friendly, no JavaScript. In the PDF they are always `open` |
| **Checklist** | The tick box on each row of `reports/_issue.html`, `static/js/report.js` | Turns the report into a to-do list. Ticks are saved in the visitor's browser (`localStorage`, key `bizzcheckup-plan-<uuid>`), never on the server. If storage is blocked it still works, it just forgets. The progress bar only appears when JavaScript runs. The PDF prints empty boxes |
| **One icon set** | `partials/icon.html` | SVG line icons (2 px stroke), `aria-hidden` because the text next to them says the same thing. No emoji |

Responsive: one column on phones (bars go under the names, the nav scrolls sideways),
two on tablets, the full grid on desktop. Long CSS selectors and URLs in the fix text use
`overflow-wrap: anywhere` so they never make the page scroll sideways. Animations (the
gauge filling, a row opening) are short and switched off with *reduce motion*.

## How the pieces fit

```
checkups.views.detail (status DONE)
   └─ reports.views.report_page
        └─ reports.builder.build_report(checkup) → ReportView    (plain Python, tested)
             ├─ AuditReport.model_validate(checkup.raw_results)
             ├─ branding.load_branding()                         (branding.yaml)
             └─ vital signs, summary, top risks, plan, recommendations, QR code
        └─ templates/reports/report.html
             └─ {% include "reports/_sections.html" with pdf=False %}

Celery task, after save_report():
   └─ reports.pdf.ensure_pdf(checkup)
        └─ render_pdf → templates/reports/report_pdf.html (same sections, pdf=True)
                      → headless Chromium → checkup.pdf (stored in the database)
```

**Why a builder?** Templates should only *display* things. Picking the strongest and
weakest vital sign, choosing services and sorting risks is logic, and logic belongs in
Python where it can be tested (`tests/reports/test_reports.py`).

## `branding.yaml` → `Branding`

`reports/branding.py` reads the file with `yaml.safe_load` and validates it with a
Pydantic model:

- `related_categories` must be real category ids, so a typo like `speed` is an error.
- URLs must be valid URLs.
- `call_to_action` must have a heading, text, button label and URL.
- `full_audit` (optional) is the "check every page" proposal: heading, text, the list of
  what's included, and a button. Without `button_url` it uses the call to action's.

`load_branding()` caches the result and **re-reads the file automatically when it
changes**. The cache key includes the file's modified time.

**A broken branding file can't go unnoticed.** `reports/apps.py` registers a Django
*system check*, so `python manage.py check`, `runserver` and CI all report
`reports.E001` (file missing) or `reports.E002` (a mistake, with the details).

## PDF generation (`reports/pdf.py`)

1. Render `reports/report_pdf.html`: the same sections, a light theme forced with
   `data-theme="light"`, and no site header.
2. Open it in headless Chromium at the made-up address `http://report.local/`.
3. **Chromium gets no network.** Every request it makes is answered by our code:
   - `/static/...`: our CSS and fonts, read from disk (`static_file()` works in
     development and after `collectstatic`),
   - `/checkups/<id>/screenshot.jpg`: the bytes from the database,
   - the consultant's photo (`branding.photo_url`): the only outside address allowed.
     Our code downloads it (`fetch_photo()`, with httpx) with a **5-second limit**; if the
     photo site is slow or down, the PDF is made without the photo instead of failing.
     (Letting Chromium fetch it directly meant a slow photo site held up the whole PDF
     until it timed out after 30 seconds.)
   - anything else is blocked.
4. `page.pdf(format="A4", print_background=True, ...)` with a footer on **every page**:
   "Generated by BizzCheckup — Check your business's online health · page N / M".
5. The CSS `@media print` rules start each section on a new page
   (`break-before: page`) and keep findings from being split (`break-inside: avoid`).

The worker makes the PDF right after the check-up and stores it in `Checkup.pdf`, so
downloads are instant. If that failed, `ensure_pdf()` makes it on the first download.
If Chromium is missing or crashes, the visitor sees a friendly "The PDF isn't available
right now" page (HTTP 503), never an error page.

## Actions above the report

| Button | Does |
|--------|------|
| **Download PDF** | `/checkups/<uuid>/report.pdf`, ready straight away because the PDF is made before the report appears |
| **Copy share link** | Copies the report's address (`static/js/report.js`) |
| **Section links** | In the sidebar (with counts and a "you are here" highlight), or the sticky bar on phones: Overview · Fix these first · All issues · All pages · Get help · Contact |
| **Check again now** | A fresh check-up of the same site, skipping report reuse (`checkups/_recheck_form.html`, `views.recheck`; rules in [Security](17-security.md)) |

Below the buttons, the report says how old it is: `{{ checkup.finished_at|timesince }}`
gives "2 hours, 18 minutes". The buttons and this note are hidden in the PDF and when
printing (`no-print`).

## Share link and privacy

The report address contains the check-up's random UUID. **Anyone with the link can view
the report, and nobody can guess it.** The pages send `<meta name="robots"
content="noindex">` so search engines don't list reports. The "Copy share link" button
(`static/js/report.js`) copies the address to the clipboard.
