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

### Accent tones (homepage only)

The homepage gives each vital sign and step its own colour, like the reference design.
These **tones** are only used for icons, tiles and soft backgrounds, never for body text,
and they are *not* health bands (green here doesn't mean "Healthy").

| Class | Light | Dark | Used for |
|-------|-------|------|----------|
| `tone-green` | `#15803d` | `#4ade80` | Performance, "Free, no account" |
| `tone-blue` | `#2563eb` | `#60a5fa` | Accessibility, step 02 |
| `tone-rose` | `#e11d48` | `#fb7185` | Best practices, "Build more trust" |
| `tone-violet` | `#7c3aed` | `#a78bfa` | SEO, step 03 |
| `tone-amber` | `#d97706` | `#fbbf24` | AI readiness |
| `tone-teal` | brand `primary` | | Step 01, "Attract more customers" |

A `tone-*` class sets two variables, `--tone` and `--tone-soft`. `color-mix(in srgb, var(--tone) 22%, var(--card))` mixes a tone with the card colour, so tints and glows work in light and dark mode without extra colours; components such as
`tone-tile` (the coloured icon square or circle) read them. Same idea as the bands: one
component, many colours, no copy-pasted CSS.

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
| `container-page` | Centred page width with side padding (64 rem: reports, forms) |
| `container-wide` | A wider page (72 rem) for the homepage |
| `btn-pill` | The big round call-to-action button on the homepage |
| `btn-primary` / `btn-secondary` | Buttons at least 44 px tall (a good touch target) |
| `card` | Rounded bordered panel |
| `eyebrow` | Small uppercase label above headings |
| `band-urgent` / `band-attention` / `band-healthy` / `band-none` + `band-pill` | Health band badge |

## The homepage (`templates/core/home.html`)

Four sections, top to bottom:

| Section | What | How |
|---------|------|-----|
| **Hero** | Full screen height. A background photo, a dark backdrop, then two columns. Left: a glowing pill label with the pulse icon, the headline with "healthy" in a mint gradient, swoosh and sparkle strokes, the paragraph, three frosted-glass perk cards with solid round icons, and a mint "Start your free check-up" button that jumps to the form. Right: the check-up form | `.hero-full` (`min-height: 100dvh`); the backdrop is a `::before` gradient; perk cards use `backdrop-filter: blur()` on a see-through white; the icons use `--tone-solid`, a saturated shade that is the same in both themes so the white icon always shows. The jump button is hidden on phones and tablets, where the form is directly below anyway. The white button text is 20 px bold ("large text"), which needs 3:1 contrast instead of 4.5:1 |
| **Five vital signs** | Heading with "healthy" highlighted and underlined (`.text-highlight`), a divider before the intro, five cards on a soft background (coloured shapes, dot grids, sparkle strokes) | Each card: its tone as a light gradient, a wave in the top-right corner (a small SVG), a glossy round badge with a solid icon (`.sign-badge`), and a coloured glow underneath (`box-shadow` with `color-mix()`). The whole card is a link to the form (`#start`) and lifts on hover. The decoration is `aria-hidden` and the dots and sparkles only show on wide screens |
| **How it works** | Three numbered steps with dashed arrows and a handwritten "Simple. Fast. Actionable." | Arrows and the note are decorative (`aria-hidden`) and only shown on wide screens |
| **A healthier website means** | Three-line headline with "More growth." in a teal gradient and a fading wavy underline, three benefits in rounded-square tiles with dividers, a gradient pill button whose arrow sits in its own circle; next to a photo of the report on a laptop, a desktop screen and a phone | Gradient text is a `background` clipped to the letters (`background-clip: text`), with plain teal as the fallback. The soft mint shapes are the text column's `::before`/`::after`; the dot grid and sparkles are the shared `.dot-grid` and `.deco-spark` (also used in "What we examine"). The photo is `static/img/healthier-website.webp` (1448×1086, 200 KB), cropped to fit (`object-cover`) and loaded lazily because it is below the fold |

**The background image** is `static/img/hero-bg.webp` (1448×1086, 186 KB): a sunny desk
in front of a city skyline, with a laptop showing a health score. WebP keeps it small. It
is preloaded in the page `<head>` with `fetchpriority="high"` because it is the first
thing visitors see. To change it, replace the file (keep it under ~300 KB) or change the
`url()` in `.hero-full` in `frontend/tailwind.css`.

On top of it, `.hero-full::before` adds the **dark backdrop**: a gradient (darkest on the
left, behind the text) plus `backdrop-filter: blur(3px)`, so the photo's own text (book
titles, the laptop screen) doesn't compete with ours.

**Text on a photo** needs light text. Instead of new colours, the hero text and the header
get the class `on-dark`, which switches *just that area* to the dark-mode palette (the
same variables as dark mode). The form keeps the page's normal theme, so it stays a light
card in light mode. The handwriting in "How it works" uses a cursive system font
(`Segoe Print` on Windows, `Bradley Hand` on Mac), so no extra font file is needed.

`base.html` has small blocks (`body_class`, `header_class`, `header_container`) so one
page can change the header without copying it.

## Template pieces

| File | What |
|------|------|
| `templates/base.html` | Skeleton: `<head>`, skip link, header with logo and theme button, footer |
| `templates/partials/logo.html` | Wordmark: pulse mark + **Bizz** (teal) + **Checkup** (ink) |
| `templates/partials/score_ring.html` | Circular score gauge (see below) |
| `templates/partials/icon.html` | One SVG icon set for the whole site: severities, vital signs, form fields, homepage |
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
