# 16. The Health Report (web page and PDF)

A finished check-up is shown at its own address, `/checkups/<uuid>/`, as the
**BizzCheckup Health Report**. The **PDF** at `/checkups/<uuid>/report.pdf` uses the
*same* template sections, so the two always match.

## The six sections (`templates/reports/_sections.html`)

The order follows the questions a business owner asks, one at a time:

| # | Section (`id`) | Question it answers | Shows | Comes from |
|---|----------------|---------------------|-------|------------|
| 1 | **Overview** (`#overview`) | *How healthy is my website?* | Domain, URL, half-circle **gauge** with the Business Health Score and band, a one-sentence **verdict**, the homepage screenshot, 4 counters (need treatment, worth fixing, quick wins, checks passed), the 5 vital signs as **bullet bars**, the summary sentences and the pages checked | `ReportView.verdict`, `.needs_treatment`, `.worth_fixing`, `.healthy_count`, `builder.diagnosis_summary()` |
| 2 | **Top risks** (`#top-issues`) | *What are the biggest problems?* | Up to 3 cards: the problem, **what it costs you**, and **the solution** side by side | `builder.top_risks()` |
| 3 | **Treatment plan** (`#plan`) | *What do I do, and in what order?* | A **checklist**: quick wins first, then next steps; each step links to its details | `engine.treatment.build_treatment_plan()` |
| 4 | **Vital signs** ×5 (`#sign-<category>`) | *Tell me more.* | Icon, score ring, a one-line **headline** ("5 issues worth fixing."), then each issue as a row that opens to show *why it matters*, *how to fix it* and *where*; "Good to know" notes; passed checks folded | `builder.vital_sign()`, `VitalSign.headline` |
| 5 | **How {first name} can help** (`#help`) | *Who can fix this?* | Each area that needs care (score < 90) mapped to the most specific service in `branding.yaml`, plus the broad "rebuild" service when 3+ areas need care, and the call to action | `builder.recommend_services()` |
| 6 | **Contact** (`#contact`) | *How do I reach them?* | Photo, name, title, intro, highlights, email, WhatsApp, website, GitHub, CV, portfolio, QR code, footer note | `branding.yaml`, `builder.qr_code_svg()` |

Every finding shows its severity ("Needs treatment", "Worth fixing", "Good to know",
"Healthy") as **an icon, a colour and a word** (never colour alone), plus impact, effort,
**why it matters for your business**, **how to fix it**, and the affected URLs (the first
5, then "and N more").

## The report's design, and why

| Pattern | Where | Why |
|---------|-------|-----|
| **Sticky bar** with the score and jump links | `report.html`, `.report-bar` | A long report needs a map. The links are real `#anchors`, so they also work without JavaScript; `scroll-mt-24` stops headings hiding under the bar |
| **Gauge** for the one big number | `reports/_gauge.html` | One KPI reads best as a gauge. `pathLength="100"` makes the score the arc length, no maths |
| **Bullet bars** with a line at 90 | `reports/_bullet.html` | Five scores compared against one target ("Healthy"). The bar is an SVG `<rect width="72">` because our CSP forbids `style="width:72%"` |
| **Problem → cost → solution** cards | Top risks | Answers "what's wrong and what do I do" without scrolling |
| **Expandable rows** (`<details>`) | `reports/_issue.html` | 40+ findings at full length make a wall of text. One line each, details on demand. `<details>` is native HTML: keyboard and screen-reader friendly, no JavaScript. In the PDF they are always `open` |
| **Checklist** | `reports/_plan_item.html`, `static/js/report.js` | Turns the report into a to-do list. Ticks are saved in the visitor's browser (`localStorage`, key `bizzcheckup-plan-<uuid>`), never on the server. If storage is blocked it still works, it just forgets. The progress bar only appears when JavaScript runs. The PDF prints empty boxes |
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
| **Jump links** (sticky bar) | Overview · Top issues · Action plan · Details · Get help |
| **Check again now** | A fresh check-up of the same site, skipping report reuse (`checkups/_recheck_form.html`, `views.recheck`; rules in [Security](17-security.md)) |

Below the buttons, the report says how old it is: `{{ checkup.finished_at|timesince }}`
gives "2 hours, 18 minutes". The buttons and this note are hidden in the PDF and when
printing (`no-print`).

## Share link and privacy

The report address contains the check-up's random UUID. **Anyone with the link can view
the report, and nobody can guess it.** The pages send `<meta name="robots"
content="noindex">` so search engines don't list reports. The "Copy share link" button
(`static/js/report.js`) copies the address to the clipboard.
