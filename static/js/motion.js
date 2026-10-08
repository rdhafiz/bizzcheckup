// Scroll reveal and parallax, without a library.
//
// FAIL OPEN: nothing is hidden by the CSS until this script adds the class
// "motion-ready" to <html>. If the script is blocked or crashes before then, the page
// is plain static content. The class is removed again (disarm) if the browser asks for
// reduced motion or if reveals don't happen when they should (the watchdog).
//
// Reveal:   <div data-reveal>               fade in and rise (default)
//           data-reveal="scale|left|right"   other entrances
//           data-reveal-once                 settle for good, don't replay
//           data-reveal-group on a parent    children entering together are staggered
// Parallax: data-parallax="0.12"            move at 12% of the scroll (negative = against it)
//           data-parallax-fill               a layer covering its container (a background):
//                                            scaled up just enough that its edge never shows
// Details: docs/19-motion.md
(function () {
  "use strict";

  var root = document.documentElement;
  var ENTER_RATIO = 0.15; // reveal when 15% is visible...
  var STAGGER_MS = 80; // ...siblings 80ms apart...
  var STAGGER_CAP_MS = 400; // ...but never more than 400ms in total
  var WATCHDOG_MS = 2000;
  var MAX_STRENGTH = 0.3; // more than this reads as a glitch, not depth
  var reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)");
  var wideScreen = window.matchMedia("(min-width: 768px)");

  // ---------------------------------------------------------------------------------
  // Scroll reveal
  // ---------------------------------------------------------------------------------
  var revealables = [];
  var observer = null;
  var armed = false;

  function setDelay(el, ms) {
    // CSSOM writes are allowed by our Content Security Policy (style="" attributes are not).
    el.style.setProperty("--reveal-delay", ms + "ms");
  }

  function show(el, delayMs) {
    setDelay(el, delayMs);
    el.classList.add("is-revealed");
    if (el.hasAttribute("data-reveal-once") && observer) observer.unobserve(el);
  }

  // Apply a state change with transitions switched off for that one change.
  function instantly(el, change) {
    el.classList.add("reveal-instant");
    change();
    requestAnimationFrame(function () {
      requestAnimationFrame(function () { el.classList.remove("reveal-instant"); });
    });
  }

  function hide(el) {
    // Only called once the element is completely off screen, so animating it back out
    // would be invisible work: reset it instantly. The delay is cleared too, or an
    // element deep in a staggered row would carry its delay into the next entrance check.
    instantly(el, function () {
      setDelay(el, 0);
      el.classList.remove("is-revealed");
    });
  }

  // Shown at once, no transition: for keyboard focus and #anchor targets.
  function showNow(el) {
    instantly(el, function () { show(el, 0); });
  }

  function groupOf(el) {
    return el.parentElement && el.parentElement.closest("[data-reveal-group]");
  }

  function onIntersect(entries) {
    var entering = [];
    entries.forEach(function (entry) {
      var el = entry.target;
      var view = entry.rootBounds ? entry.rootBounds.height : window.innerHeight;
      // Asymmetric: in at 15% (or a quarter of the screen for tall elements), out only
      // when fully gone. In between nothing changes, so nothing flickers at the edge.
      var enter = entry.isIntersecting &&
        (entry.intersectionRatio >= ENTER_RATIO || entry.intersectionRect.height >= view * 0.25);
      if (enter && !el.classList.contains("is-revealed")) entering.push(el);
      else if (!entry.isIntersecting && el.classList.contains("is-revealed")) hide(el);
    });

    // Stagger index is worked out NOW, among the elements entering together in each
    // group, in page order. Nothing is cached: membership can differ on every visit.
    var counters = new Map();
    entering
      .sort(function (a, b) {
        return a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1;
      })
      .forEach(function (el) {
        var group = groupOf(el);
        var index = group ? (counters.get(group) || 0) : 0;
        if (group) counters.set(group, index + 1);
        show(el, Math.min(index * STAGGER_MS, STAGGER_CAP_MS));
      });
  }

  function revealTarget(target) {
    if (!target || !armed) return;
    var holder = target.closest("[data-reveal]");
    if (holder) showNow(holder);
    target.querySelectorAll("[data-reveal]").forEach(showNow);
  }

  function onFocusIn(event) {
    // Always snap, even if it's already revealing: it may still be mid-fade (for example a
    // footer column that started its staggered entrance a moment ago), and focus must
    // never land on something you can't see.
    var holder = armed && event.target.closest && event.target.closest("[data-reveal]");
    if (holder) showNow(holder);
  }

  function onHash() {
    var id = decodeURIComponent(location.hash.slice(1));
    if (id) revealTarget(document.getElementById(id));
  }

  function disarm() {
    armed = false;
    if (observer) observer.disconnect();
    observer = null;
    root.classList.remove("motion-ready");
    revealables.forEach(function (el) {
      el.classList.remove("is-revealed", "reveal-instant");
      el.style.removeProperty("--reveal-delay");
    });
  }

  // If anything on screen is still hidden a while after arming, the observer isn't
  // doing its job (collapsed layout, odd browser...): give up and show everything.
  // Judged only while the page is actually visible.
  function startWatchdog() {
    function check() {
      if (!armed) return;
      if (document.visibilityState !== "visible") {
        document.addEventListener("visibilitychange", startWatchdog, { once: true });
        return;
      }
      var stuck = revealables.some(function (el) {
        if (el.classList.contains("is-revealed")) return false;
        var r = el.getBoundingClientRect();
        return r.height > 0 && r.bottom > 0 && r.top < window.innerHeight;
      });
      if (stuck) disarm();
    }
    setTimeout(check, WATCHDOG_MS);
  }

  function arm() {
    if (armed || reducedMotion.matches || !revealables.length) return;
    // A background tab gets no animation frames: an entrance would run unseen or stall.
    // Wait until the page is visible; until then nothing is hidden.
    if (document.visibilityState !== "visible") {
      document.addEventListener("visibilitychange", arm, { once: true });
      return;
    }
    observer = new IntersectionObserver(onIntersect, { threshold: [0, 0.05, 0.1, ENTER_RATIO, 0.3] });
    root.classList.add("motion-ready");
    armed = true;
    revealables.forEach(function (el) { observer.observe(el); });
    onHash(); // opened at an #anchor: show it at once
    startWatchdog();
  }

  // ---------------------------------------------------------------------------------
  // Parallax
  // ---------------------------------------------------------------------------------
  var containers = []; // [{ box, layers: [{ el, strength, fill }] }]
  var ticking = false;
  var parallaxOn = false;

  function collectParallax() {
    var byBox = new Map();
    document.querySelectorAll("[data-parallax]").forEach(function (el) {
      var strength = parseFloat(el.getAttribute("data-parallax"));
      if (!isFinite(strength) || !strength) return;
      strength = Math.max(-MAX_STRENGTH, Math.min(MAX_STRENGTH, strength));
      var box = el.parentElement; // must clip (overflow: hidden) - see the CSS
      if (!byBox.has(box)) byBox.set(box, { box: box, layers: [] });
      byBox.get(box).layers.push({ el: el, strength: strength, fill: el.hasAttribute("data-parallax-fill") });
    });
    containers = Array.from(byBox.values());
  }

  function update() {
    ticking = false;
    if (!parallaxOn) return;
    var view = window.innerHeight;
    // Read everything first, then write: no layout thrashing.
    var frames = containers.map(function (c) { return c.box.getBoundingClientRect(); });
    containers.forEach(function (c, i) {
      var rect = frames[i];
      if (!rect.height || rect.bottom < -view || rect.top > 2 * view) return; // far away
      // The box crosses the screen over `travel` pixels of scrolling. Offsets are centred
      // on the middle of that journey, so each direction gets half of the movement.
      var travel = view + rect.height;
      var progress = view - rect.top - travel / 2; // -travel/2 ... +travel/2
      c.layers.forEach(function (layer) {
        var y = progress * layer.strength;
        var transform = "translate3d(0," + y.toFixed(1) + "px,0)";
        if (layer.fill) {
          // Budget rule: scaled to S, a layer can travel (S-1)/2 of its size each way.
          // The furthest it travels is |strength| * travel / 2, so pick S to cover that.
          var scale = 1 + Math.abs(layer.strength) * travel / rect.height;
          transform += " scale(" + scale.toFixed(3) + ")";
        }
        layer.el.style.transform = transform;
      });
    });
  }

  function requestUpdate() {
    if (!ticking) {
      ticking = true;
      requestAnimationFrame(update);
    }
  }

  function setParallax(on) {
    parallaxOn = on;
    root.classList.toggle("parallax-on", on);
    if (on) {
      requestUpdate();
    } else {
      containers.forEach(function (c) {
        c.layers.forEach(function (layer) { layer.el.style.removeProperty("transform"); });
      });
    }
  }

  function refreshParallax() {
    // Small screens have little travel to spend and the weakest devices: no parallax.
    setParallax(containers.length > 0 && wideScreen.matches && !reducedMotion.matches);
  }

  // ---------------------------------------------------------------------------------
  // Start
  // ---------------------------------------------------------------------------------
  function onMotionPreference() {
    if (reducedMotion.matches) disarm();
    else arm();
    refreshParallax();
  }

  function listen(query, handler) {
    if (query.addEventListener) query.addEventListener("change", handler);
    else query.addListener(handler); // older Safari
  }

  function start() {
    if (!("IntersectionObserver" in window) || !window.requestAnimationFrame) return;
    revealables = Array.prototype.slice.call(document.querySelectorAll("[data-reveal]"));
    collectParallax();

    arm();
    refreshParallax();

    document.addEventListener("focusin", onFocusIn);
    window.addEventListener("hashchange", onHash);
    window.addEventListener("scroll", requestUpdate, { passive: true });
    window.addEventListener("resize", requestUpdate, { passive: true });
    listen(reducedMotion, onMotionPreference);
    listen(wideScreen, refreshParallax);
  }

  try {
    start();
  } catch (error) {
    // Fail open: whatever went wrong, show the page as plain static content.
    try { disarm(); setParallax(false); } catch (ignored) { /* nothing more to do */ }
  }
})();
