# 19. Motion: scroll reveal and parallax

Two small motion systems make the homepage feel alive without getting in the way:

| System | What you see | Where |
|--------|--------------|-------|
| **Scroll reveal** | Content fades in as it scrolls into view, every time: rising from below when you scroll down, coming down from above when you scroll back up | Every homepage section (the hero included) and the footer columns |
| **Parallax** | Background photos drift slower than the page; the hero text and small sparkles move against them, which reads as depth | Hero photo and text, the "healthier website" photo, the sparkle accents. The hero and the "healthier website" section are each one screen tall on wide screens, so each photo crosses the screen over exactly two screen heights of scrolling |

The work is done by `static/js/motion.js` (about 7 KB, no library), helped by a tiny
`static/js/motion-boot.js` in `<head>`, plus a CSS block marked `Motion` in
`frontend/tailwind.css`.

**Why no animation library (GSAP, Motion...)?** Both systems are small. The browser already
has the hard parts: `IntersectionObserver` tells us when an element enters the screen, CSS
transitions do the animating, and `requestAnimationFrame` gives one tidy moment per frame
for the parallax maths. A library would add 30–70 KB for things we don't use.

## Using it in a template

```html
<div data-reveal>...</div>                 fade in and rise 32px (the default)
<div data-reveal="scale">...</div>         fade in and grow from 94%
<div data-reveal data-reveal-once>         animate once, then stay put for good

<div data-reveal-group>                    children that enter together are staggered:
  <div data-reveal>...</div>               0 ms
  <div data-reveal>...</div>               110 ms
  <div data-reveal>...</div>               220 ms ... never more than 550 ms
</div>

<div data-parallax="0.12" data-parallax-fill>   a background layer: drifts at 12% of the
                                                  scroll and is scaled so its edge never shows
<div data-parallax="-0.05">                       foreground: moves 5% *against* the scroll
```

Rules of thumb:

- **Up, down or zoom only.** There are no sideways entrances, by design: content comes up
  from below, down from above (when scrolling back up) or zooms in. A sideways entrance also
  pushes the element outside the page edge while it waits, which can make phones scroll
  horizontally.

- **Put `data-reveal` on a wrapper, not on a button or card.** The reveal sets its own
  `transition`, which would replace the element's hover transition.
- **Keep the first screen quick.** The hero has a slightly shorter entrance (900 ms instead
  of 1.1 s; the headline is fully visible after about 1.1 s). Fading in the first screen delays the moment the page *looks* loaded,
  which Google measures as "Largest Contentful Paint", so it's a trade-off we chose for the
  effect; keep it short.
- **Never put `data-reveal` and `data-parallax` on the same element**: both use `transform`
  and would fight. In the hero, the children reveal and their wrapper does the parallax.
- **Parallax strength up to about 0.25.** Above about 0.3 it looks like a glitch, not depth.
  The script caps it at 0.3. Ours: hero photo 0.22, hero text −0.10, benefits photo 0.14,
  sparkles −0.15.
- **A parallax layer's parent must clip** (`overflow: hidden`), or the moving layer shows
  outside its box.

## How the reveal works

**Timing.** Each entrance takes **1.1 s** with a gentle ease-out (`cubic-bezier(0.33, 1, 0.68, 1)`,
"easeOutCubic"): it starts moving straight away but glides evenly into place. Steeper curves do
most of the movement in the first few frames, which feels abrupt. Never use ease-*in* for an
entrance: a slow start looks like lag. To make everything faster or slower, change
`transition-duration` in the Motion block of `frontend/tailwind.css` and `STAGGER_MS` in
`motion.js`.

1. When the script starts it adds the class `motion-ready` to `<html>`. **Only then** does the
   CSS hide anything:

   ```css
   html.motion-ready [data-reveal] { opacity: 0; transform: translate3d(0, 32px, 0); ... }
   html.motion-ready [data-reveal].is-revealed { opacity: 1; transform: none; }
   ```

   This is called **failing open**. If the script is blocked or crashes, the class is never
   added and the page is plain, readable content. A test (`tests/core/test_motion.py`)
   checks that every rule hiding `[data-reveal]` starts with `html.motion-ready`.
2. One `IntersectionObserver` watches all marked elements. When at least **15%** of one is on
   screen, it gets `is-revealed` and the CSS transition plays.
3. When it has **completely** left the screen, `is-revealed` is removed (instantly, since
   nobody can see it), so it animates again next time. In between 0% and 15% nothing changes:
   this gap (*hysteresis*) stops an element parked at the edge from flickering.
4. **Direction.** Elements wait on the side they will come from, noted in `data-from`:
   - when one leaves, the script records the edge it left by (`above` if you scrolled past it);
   - when one enters, the **scroll direction** decides: scrolling up, it comes *down* from
     32 px above its place; scrolling down, it rises from 32 px below. Deciding at entry
     matters for big jumps (the End key, a `#link`): an element that was jumped over never
     reported leaving, so its recorded side could be wrong. The scroll direction comes from
     comparing `scrollY` in the passive scroll listener, which costs no layout work.
5. **Stagger:** the elements that enter together in the same group get delays of 0, 110, 220 ms...
   worked out at that moment (never stored), capped at 550 ms. Scrolling down they go in page
   order; scrolling up the order is reversed, so the one nearest the edge you're scrolling
   towards comes first. The delay is a CSS variable, `--reveal-delay`, read by `transition-delay`.

### Why there are two scripts

`motion.js` loads with `defer`, after the page has been drawn. If it were the one to hide
the hero, you would see the hero, then see it vanish, then see it fade in. So
`motion-boot.js` (a few lines, loaded *without* `defer` in `<head>`) sets the flags
`motion-ready` and `motion-boot` before anything is drawn, and only when motion can actually
run (no reduced motion, a modern browser, a visible tab).

That breaks the simple "the main script sets the flag" rule, so there is a second safety net
in CSS alone:

```css
html.motion-boot [data-reveal]:not(.is-revealed) { animation: reveal-failsafe 1ms 1.5s both; }
```

If `motion.js` never arrives, this animation shows everything after 1.5 s. When `motion.js`
does start, it removes `motion-boot`, which switches the fail-safe off.

**Why CSS transitions, not `@keyframes` animations?** A transition replays by just adding and
removing a class, reverses smoothly if you scroll back halfway, and has none of the traps of
keyframe animations (paused animations can't rewind; the `animation` shorthand resets delays;
an animation must "hold" its first frame or it flashes).

### Safety nets

| Situation | What happens |
|-----------|--------------|
| `motion.js` blocked or crashes | The CSS fail-safe shows everything after 1.5 s (or `catch` removes the flags at once) |
| Both scripts blocked, or JavaScript off | No flag is ever set: nothing hidden |
| Visitor asked for **reduced motion** (system setting) | Nothing is armed: no hiding, no transforms, no delays. Switching the setting on while on the page disarms everything |
| Page opened in a **background tab** | Not armed until the tab becomes visible (background tabs get no animation frames) |
| Observer never fires (collapsed layout, odd browser) | **Watchdog:** 2 seconds after arming (while the page is visible), if anything on screen is still hidden, everything is disarmed and shown |
| Keyboard focus lands inside hidden content | Shown instantly (`focusin` listener), even mid-fade |
| Link to an `#anchor` inside hidden content | Shown instantly (on load and on `hashchange`) |
| Old browser without `IntersectionObserver` | Script does nothing: static page |
| Printing | A print rule shows everything |

Hidden elements are only *see-through and shifted*, never removed: screen readers still read
them, in page order.

## How the parallax works

On every scroll, one `requestAnimationFrame` callback does all the work, reading every
position first and only then writing, so the browser never has to recalculate the layout
mid-frame:

```
travel   = screen height + box height     how far you scroll while the box is visible
progress = screen height - box top - travel / 2     -travel/2 ... +travel/2, 0 = centred
offset   = progress × strength            the layer's translateY
```

Offsets are centred on the moment the box sits in the middle of its journey, so the layer
moves the same amount each way. For the hero (at the very top) that means it starts at
exactly 0: nothing jumps when the page loads.

**The budget rule.** A background layer must be bigger than its box, or its edge appears as it
moves. Scaled to `S`, a layer has `(S − 1) / 2` of its size spare on each side. The furthest it
moves is `strength × travel / 2`, so the script sets:

```
S = 1 + |strength| × travel / box height
```

For the hero (one screen tall, strength 0.22) that is `1 + 0.22 × 2 = 1.44`, the same value the
CSS uses before the script runs, so the photo never "pops". Tested at four screen sizes: no
gap at any scroll position.

Parallax is **off below 768 px wide** (little room to move, weakest devices) and with reduced
motion. Moving things only with `transform` keeps it on the graphics card: no layout, no repaint.

## Smooth scrolling to #links

Links to a place on the same page (`#start`, the footer's "What we examine", "Back to top",
the report's jump bar) glide there instead of jumping. It's one CSS rule:

```css
@media (prefers-reduced-motion: no-preference) {
  html { scroll-behavior: smooth; }
}
```

This is the browser's own smooth scrolling: no script takes over the wheel, keys or touch.
Visitors who asked for reduced motion keep the instant jump. Every element with an `id` gets
`scroll-margin-top: 2rem`, so a heading lands with a little room above it (report sections
use 6rem, for their sticky bar).

Two details made it land exactly right:

1. **Reveal the target before the scroll starts.** The browser works out where to scroll
   at the moment of the click. A hidden target sits 32px off (or zoomed out), so the scroll
   aimed at that spot and landed off once the element settled. `motion.js` listens for
   clicks on same-page links (in the *capture* phase, before the browser acts) and shows the
   target instantly first. It also "pins" the target as shown until it arrives, so it isn't
   reset while still off screen during the glide.
2. **`overflow: clip`, not `overflow: hidden`.** A box with `overflow: hidden` hides what
   sticks out, but script and link navigation can still *scroll inside it*. Our sections
   clip their decorations and parallax photos, so following a link into one scrolled its
   content inside the box: the hero shifted 198px, "What we examine" 92px. `overflow: clip`
   clips the same way but can't be scrolled at all. Tests check both rules.

## Performance notes

Measured in Microsoft Edge with graphics acceleration, scrolling the whole homepage:

| | Normal speed | CPU slowed down 4× |
|--|--|--|
| Motion off | ~1% frames over 20 ms | ~1.6% |
| Motion on | ~0.3% (one warm-up run: 10%) | ~4.4% (p95 still ~17 ms) |
| Long tasks (> 50 ms) | none | none |

What made the difference:

- **`will-change: transform, opacity` on hidden reveal elements** gives each its own GPU layer
  up front. Without it the browser creates and paints the layer the moment an entrance starts,
  in the middle of a scroll frame; with the cards' soft shadows that caused 65–83 ms stalls on
  the slowed CPU.
- **Hiding instantly on exit**: animating something back out while it's off screen is wasted work.
- One shared observer, one animation-frame callback, passive scroll listeners.

## Testing it yourself

- **Reduced motion:** Windows → Settings → Accessibility → Visual effects → *Animation effects*
  off, then reload: everything is in place and nothing moves.
- **No JavaScript:** in Chrome DevTools, Ctrl+Shift+P → "Disable JavaScript", reload: all content
  is visible.
- In DevTools → Elements, watch `<html class="motion-ready parallax-on">` and the
  `is-revealed` classes come and go as you scroll.
