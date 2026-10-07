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

### Score ring trick

```html
<circle pathLength="100" stroke-dasharray="72 100" .../>
```

`pathLength="100"` tells the browser that the circle's length is 100. A score of 72
then draws exactly 72 % of the ring, with no maths needed in the template.

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
