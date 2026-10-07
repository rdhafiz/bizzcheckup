# 11. Frontend & Brand

## Approach

- Server-rendered **Django templates**. There's no React or Vue, so the HTML arrives
  complete. That's fast, and good for SEO and accessibility.
- **Tailwind CSS** for styling, built with the **standalone CLI** (no Node.js).
- **HTMX** (phase 6) for live updates, like the progress page, without writing
  JavaScript.
- Mobile-first, light and dark themes, and WCAG AA contrast.

## Tailwind in two minutes

Tailwind gives small single-purpose classes that you combine in HTML:

```html
<p class="mt-5 max-w-2xl text-lg text-muted">...</p>
<!--      margin-top  max width   big text  our muted colour -->
```

The CLI scans `templates/` and `bizzcheckup/` for class names and writes **only the
classes we use** into `static/css/app.css`. That's about 17 KB.

```bash
python scripts/get_tailwind.py                                                # download once
.bin/tailwindcss -i frontend/tailwind.css -o static/css/app.css --watch       # while coding
.bin/tailwindcss -i frontend/tailwind.css -o static/css/app.css --minify      # one-off build
```

`sm:` means "from 640 px wide". Classes without a prefix apply to phones, which is
what mobile-first means.

## Design tokens (`frontend/tailwind.css`)

Colours are **CSS variables**. Dark mode swaps the variables, so templates use the
same class names (`bg-paper`, `text-ink`) in both themes.

| Token | Light | Dark | Used for |
|-------|-------|------|----------|
| `paper` | `#f7f6f2` | `#0c1517` | Page background (warm, like a printed report) |
| `card` | `#ffffff` | `#132124` | Cards |
| `ink` | `#0e1b1e` | `#e7efec` | Main text |
| `muted` | `#4a5a5e` | `#9fb1b0` | Secondary text |
| `line` | `#e2ded4` | `#2b4045` | Borders |
| `primary` | `#0f6e66` | `#3fbfb0` | Brand teal: links, buttons |
| `urgent` | `#c62828` | `#f26b6b` | 0–49 "Needs urgent care" |
| `attention` | `#b45309` | `#f5a524` | 50–89 "Needs attention" |
| `healthy` | `#15803d` | `#4ade80` | 90–100 "Healthy" |

**Rule:** a band colour always comes with its text label, because some people can't
tell red from green.

## Fonts

| Font | Use | Why |
|------|-----|-----|
| Bricolage Grotesque | Headings | Has character without being playful |
| Public Sans | Body text | Very readable, neutral, made for public services |
| JetBrains Mono | Scores, numbers, labels | Digits are all the same width, so scores line up |

The fonts are self-hosted in `static/fonts/` under the SIL Open Font License. No
requests go to Google, which is better for privacy, speed and PDF output.

## Reusable classes (`@utility`)

| Class | What |
|-------|------|
| `container-page` | Centred page width with side padding |
| `btn-primary` / `btn-secondary` | Buttons at least 44 px tall (a good touch target) |
| `card` | Rounded bordered panel |
| `eyebrow` | Small uppercase label above headings |
| `band-urgent` / `band-attention` / `band-healthy` / `band-none` + `band-pill` | Health band badge |

## Template pieces

| File | What |
|------|------|
| `templates/base.html` | Skeleton: `<head>`, skip link, header with logo and theme button, footer |
| `templates/partials/logo.html` | Wordmark: pulse mark + **Bizz** (teal) + **Checkup** (ink) |
| `templates/partials/score_ring.html` | Circular score gauge (see below) |
| `templates/reports/_icon.html` | The report's SVG icons: severities, the five vital signs, why/fix/where |
| `templates/reports/_gauge.html` | Half-circle gauge for the Business Health Score |
| `templates/reports/_bullet.html` | One vital sign as a bar against the "Healthy" line at 90 |
| `templates/reports/_issue.html` | One finding as an expandable `<details>` row |
| `templates/reports/_plan_item.html` | One treatment-plan step with its checkbox |

How and why the report looks the way it does: [Health report](16-health-report.md#the-reports-design-and-why).

### Score ring trick

```html
<circle pathLength="100" stroke-dasharray="72 100" .../>
```

`pathLength="100"` tells the browser that the circle's length is 100. A score of 72
then draws exactly 72 % of the ring, with no maths needed in the template.

## The live progress page (HTMX + `static/js/progress.js`)

Two pieces work together:

1. **HTMX fetches the facts.** Every second it asks the server for the latest progress,
   and puts the answer into a small **hidden** element:
   ```html
   <div id="progress-data" hidden
        hx-get="/checkups/<uuid>/progress/" hx-trigger="every 1s" hx-swap="innerHTML">
     <span data-progress="54" data-status="running" data-step="Measuring speed with Google PageSpeed…"></span>
   </div>
   ```
   When the check-up has finished, the server answers with status **286**, htmx's built-in
   signal to **stop polling**.
2. **`progress.js` animates what the visitor sees**, towards those facts:
   - the bar **glides** at a steady pace (about 15% a second) instead of jumping;
   - during a long step (Google's PageSpeed test can take 20–40 s), it **creeps** slowly
     (about 1% every 2 s), but never past the end of the current step, so it never claims
     work that isn't done;
   - steps are **ticked off one by one** as the bar passes them, even when the server
     finished several at once (the five category checks take under a second);
   - the text names the step the bar is on, or the server's detailed message ("Measuring
     speed with Google PageSpeed…") once the bar has caught up;
   - at 100%, a **success animation** plays (a circle and tick drawn with SVG
     `stroke-dashoffset`, in `frontend/tailwind.css`), then the report opens at the same URL;
   - if the check-up failed, it reloads at once to show the friendly error page;
   - with `prefers-reduced-motion`, everything jumps straight to its final state.

Each step in the list carries its range, `data-start` and `data-end`, taken from
`checkups/progress.py`. That module uses the same milestones as the engine
(`engine/runner.py`: crawl 3%, vital signs 20–70%, categories 70–86%, report 90%, PDF 94%).

Without JavaScript, a `<noscript>` meta refresh reloads the page every 5 seconds.

### No inline styles

The progress bar is a native `<progress>` element styled in `frontend/tailwind.css`
(`.progress-bar`), not a `<div style="width: 60%">`. Inline `style` attributes would
force a weaker Content Security Policy in phase 8.

### Template filters (`bizzcheckup/core/templatetags/bizz.py`)

```django
{% load bizz %}
<span class="band-{{ score|band }} band-pill">{{ score|band_label }}</span>
{# 72 → class "band-attention", text "Needs attention"; empty → "none" / "Not checked" #}
```

## Dark mode (`static/js/theme.js`)

1. By default, the site follows the system setting (`prefers-color-scheme`).
2. The moon button sets `data-theme="dark"` or `"light"` on `<html>` and remembers the
   choice in `localStorage`.
3. The script loads in `<head>` **without** `defer`, so the theme is set before the
   page appears. That prevents a white flash.

## Style guide page

<http://127.0.0.1:8000/styleguide/> shows every building block. It's only available
while `DEBUG` is on.

## Accessibility built in

- A "Skip to content" link (visible when you press Tab).
- Visible focus outline on everything you can click.
- Score rings have an `aria-label` such as "SEO: 72 out of 100, Needs attention".
- `prefers-reduced-motion` turns animations off.
