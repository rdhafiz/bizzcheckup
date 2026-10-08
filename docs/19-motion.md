# 19. Motion: scroll reveal and parallax

Two small motion systems make the homepage feel alive without getting in the way:

| System | What you see | Where |
|--------|--------------|-------|
| **Scroll reveal** | Content fades in and rises a little as it scrolls into view, and again every time it comes back | Homepage sections below the hero, footer columns |
| **Parallax** | Background photos drift slower than the page; the hero text and small sparkles move slightly against them, which reads as depth | Hero photo and text, the "healthier website" photo, the sparkle accents |

Both live in one file, `static/js/motion.js` (about 6 KB, no library), plus a CSS block
marked `Motion` in `frontend/tailwind.css`.

**Why no animation library (GSAP, Motion...)?** Both systems are small. The browser already
has the hard parts: `IntersectionObserver` tells us when an element enters the screen, CSS
transitions do the animating, and `requestAnimationFrame` gives one tidy moment per frame
for the parallax maths. A library would add 30–70 KB for things we don't use.

## Using it in a template

```html
<div data-reveal>...</div>                 fade in and rise 32px (the default)
<div data-reveal="scale">...</div>         fade in and grow from 94%
<div data-reveal="left">...</div>          come in from the left (wide screens; phones rise)
<div data-reveal="right">...</div>         come in from the right (wide screens; phones rise)
<div data-reveal data-reveal-once>         animate once, then stay put for good

<div data-reveal-group>                    children that enter together are staggered:
  <div data-reveal>...</div>               0 ms
  <div data-reveal>...</div>               80 ms
  <div data-reveal>...</div>               160 ms ... never more than 400 ms
</div>

<div data-parallax="0.12" data-parallax-fill>   a background layer: drifts at 12% of the
                                                  scroll and is scaled so its edge never shows
<div data-parallax="-0.05">                       foreground: moves 5% *against* the scroll
```

Rules of thumb:

- **Put `data-reveal` on a wrapper, not on a button or card.** The reveal sets its own
  `transition`, which would replace the element's hover transition.
- **Never on the hero.** The first screen must appear at once; fading it in delays the moment
  the page looks loaded (Google measures this as "Largest Contentful Paint").
- **Parallax strength 0.05–0.15.** Above about 0.3 it looks like a glitch, not depth. The
  script caps it at 0.3.
- **A parallax layer's parent must clip** (`overflow: hidden`), or the moving layer shows
  outside its box.

## How the reveal works

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
4. **Stagger:** the elements that enter together in the same group get delays of 0, 80, 160 ms...
   in page order, worked out at that moment (never stored), capped at 400 ms. The delay is set
   as a CSS variable, `--reveal-delay`, read by `transition-delay`.

**Why CSS transitions, not `@keyframes` animations?** A transition replays by just adding and
removing a class, reverses smoothly if you scroll back halfway, and has none of the traps of
keyframe animations (paused animations can't rewind; the `animation` shorthand resets delays;
an animation must "hold" its first frame or it flashes).

### Safety nets

| Situation | What happens |
|-----------|--------------|
| Script blocked or crashes | `motion-ready` is never set (or removed in `catch`): nothing hidden |
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

For the hero (one screen tall, strength 0.12) that is `1 + 0.12 × 2 = 1.24`, the same value the
CSS uses before the script runs, so the photo never "pops". Tested at four screen sizes: no
gap at any scroll position.

Parallax is **off below 768 px wide** (little room to move, weakest devices) and with reduced
motion. Moving things only with `transform` keeps it on the graphics card: no layout, no repaint.

## Performance notes

Measured in Microsoft Edge with graphics acceleration, scrolling the whole homepage:

| | Normal speed | CPU slowed down 4× |
|--|--|--|
| Motion off | ~1% frames over 20 ms | ~2% |
| Motion on | ~0.3% (one warm-up run: 10%) | ~6% |
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
