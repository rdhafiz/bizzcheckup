// Scroll reveal and parallax, without a library.
//
// FAIL OPEN: nothing is hidden by the CSS until this script adds the class
// "motion-ready" to <html>. If the script is blocked or crashes before then, the page
// is plain static content. The class is removed again (disarm) if the browser asks for
// reduced motion or if reveals don't happen when they should (the watchdog).
//
// Reveal:   <div data-reveal>               fade in and rise (default); scrolling back up,
//                                            it comes down from above instead
//           data-reveal="scale"              zoom in instead (no sideways entrances, by design)
//           data-reveal="words"              a heading: each word sharpens out of a blur in turn
//           data-word (inside a heading)     keep this part as one word (gradient text, highlights)
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
  var STAGGER_MS = 110; // ...siblings 110ms apart...
  var STAGGER_CAP_MS = 550; // ...but never more than 550ms in total
  var WORD_MS = 90; // headings: each word 90ms after the previous one...
  var WORD_CAP_MS = 900; // ...the last one starting by 900ms at most
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
  var lastScrollY = window.scrollY;
  var scrollingUp = false;

  // Direction of the latest scroll. Reading scrollY costs no layout work.
  function trackDirection() {
    var y = window.scrollY;
    if (y !== lastScrollY) {
      scrollingUp = y < lastScrollY;
      lastScrollY = y;
    }
  }

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

  // `from` is the edge it left by: "above" (scrolled past) or "below" (not reached yet).
  // It will come back from that side, so it waits there: scrolling up, content slides
  // down into place instead of rising.
  function hide(el, from) {
    // Only called once the element is completely off screen, so animating it back out
    // would be invisible work: reset it instantly. The delay is cleared too, or an
    // element deep in a staggered row would carry its delay into the next entrance check.
    instantly(el, function () {
      setDelay(el, 0);
      el.classList.remove("is-revealed");
      el.setAttribute("data-from", from);
    });
  }

  // Shown at once, no transition: for keyboard focus and #anchor targets.
  function showNow(el) {
    instantly(el, function () { show(el, 0); });
  }

  function groupOf(el) {
    return el.parentElement && el.parentElement.closest("[data-reveal-group]");
  }

  // Move a hidden element to the side it will enter from, without animating that move,
  // so its entrance starts from the right place.
  function waitOn(el, from) {
    if (el.getAttribute("data-from") === from) return;
    el.classList.add("reveal-instant");
    el.setAttribute("data-from", from);
    void getComputedStyle(el).transform; // apply the new start position now...
    el.classList.remove("reveal-instant"); // ...so the entrance transition starts from it
  }

  // Wrap each word of a heading in <span class="word"> so the words can blur in one by one.
  // Only text is split: tags inside stay as they are. Parts marked data-word (gradient text,
  // highlights) move as one word, because splitting would break their colouring. Screen-reader
  // only text is left alone. The spaces between words stay real spaces, so the heading reads
  // exactly as before.
  function splitWords(heading) {
    var walker = document.createTreeWalker(heading, NodeFilter.SHOW_TEXT, {
      acceptNode: function (node) {
        if (!node.nodeValue.trim()) return NodeFilter.FILTER_REJECT;
        if (node.parentElement.closest("[data-word], .sr-only, svg")) return NodeFilter.FILTER_REJECT;
        return NodeFilter.FILTER_ACCEPT;
      }
    });
    var textNodes = [];
    while (walker.nextNode()) textNodes.push(walker.currentNode);
    textNodes.forEach(function (node) {
      var pieces = document.createDocumentFragment();
      node.nodeValue.split(/(\s+)/).forEach(function (part) {
        if (!part) return;
        if (/^\s+$/.test(part)) {
          pieces.appendChild(document.createTextNode(part));
        } else {
          var word = document.createElement("span");
          word.className = "word";
          word.textContent = part;
          pieces.appendChild(word);
        }
      });
      node.parentNode.replaceChild(pieces, node);
    });
    heading.querySelectorAll("[data-word]").forEach(function (unit) { unit.classList.add("word"); });
    heading.querySelectorAll(".word").forEach(function (word, i) {
      word.style.setProperty("--word-delay", Math.min(i * WORD_MS, WORD_CAP_MS) + "ms");
    });
    heading.classList.add("words-ready");
  }

  function inPageOrder(a, b) {
    return a.compareDocumentPosition(b) & Node.DOCUMENT_POSITION_FOLLOWING ? -1 : 1;
  }

  function onIntersect(entries) {
    var entering = [];
    entries.forEach(function (entry) {
      var el = entry.target;
      var top = entry.rootBounds ? entry.rootBounds.top : 0;
      var view = entry.rootBounds ? entry.rootBounds.height : window.innerHeight;
      // Asymmetric: in at 15% (or a quarter of the screen for tall elements), out only
      // when fully gone. In between nothing changes, so nothing flickers at the edge.
      var enter = entry.isIntersecting &&
        (entry.intersectionRatio >= ENTER_RATIO || entry.intersectionRect.height >= view * 0.25);
      if (entry.isIntersecting) pinned.delete(el); // arrived
      if (enter) {
        if (!el.classList.contains("is-revealed")) {
          // Scrolling up, anything that appears is arriving from above. Decided here, at entry,
          // because an element that was jumped over (End key, #anchor) never reported leaving.
          waitOn(el, scrollingUp ? "above" : "below");
          entering.push(el);
        }
      } else if (!entry.isIntersecting) {
        if (pinned.has(el)) return; // a #link target on its way into view: keep it shown
        var from = entry.boundingClientRect.bottom <= top ? "above" : "below";
        if (el.classList.contains("is-revealed") || el.getAttribute("data-from") !== from) hide(el, from);
      }
    });

    // Stagger index is worked out NOW, among the elements entering together in each
    // group. Nothing is cached: membership can differ on every visit. Scrolling down
    // they cascade in page order; scrolling up, from the bottom one (nearest the edge).
    var counters = new Map();
    var fromBelow = entering.filter(function (el) { return el.getAttribute("data-from") !== "above"; });
    var fromAbove = entering.filter(function (el) { return el.getAttribute("data-from") === "above"; });
    fromBelow.sort(inPageOrder).concat(fromAbove.sort(inPageOrder).reverse()).forEach(function (el) {
      var group = groupOf(el);
      var index = group ? (counters.get(group) || 0) : 0;
      if (group) counters.set(group, index + 1);
      show(el, Math.min(index * STAGGER_MS, STAGGER_CAP_MS));
    });
  }

  // A #link target is shown at once and "pinned" while the page glides to it, so it isn't
  // reset to hidden while it is still off screen. The pin comes off once it is in view.
  var pinned = new Set();

  function pin(el) {
    showNow(el);
    pinned.add(el);
    setTimeout(function () { pinned.delete(el); }, 3000); // in case it never arrives
  }

  function revealTarget(target) {
    if (!target || !armed) return;
    var holder = target.closest("[data-reveal]");
    if (holder) pin(holder);
    target.querySelectorAll("[data-reveal]").forEach(pin);
  }

  // Clicks on links to this page: reveal the target BEFORE the browser works out where to
  // scroll. While hidden it is shifted (or zoomed out), and the smooth scroll would aim at
  // that shifted spot and land a little off once it settles.
  function onLinkClick(event) {
    var link = event.target.closest && event.target.closest("a[href*='#']");
    if (!link || link.host !== location.host || link.pathname !== location.pathname) return;
    var id = decodeURIComponent(link.hash.slice(1));
    if (id) revealTarget(document.getElementById(id));
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
    root.classList.remove("motion-ready", "motion-boot");
    revealables.forEach(function (el) {
      el.classList.remove("is-revealed", "reveal-instant");
      el.removeAttribute("data-from");
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
    if (armed) return;
    if (reducedMotion.matches || !revealables.length) {
      root.classList.remove("motion-ready", "motion-boot"); // motion-boot.js may have set them
      return;
    }
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
    // From here on this script is in charge: switch off the CSS fail-safe from motion-boot.js.
    root.classList.remove("motion-boot");
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
    if (!reducedMotion.matches) document.querySelectorAll('[data-reveal="words"]').forEach(splitWords);
    collectParallax();

    arm();
    refreshParallax();

    document.addEventListener("focusin", onFocusIn);
    document.addEventListener("click", onLinkClick, true); // capture: before the scroll
    window.addEventListener("hashchange", onHash);
    window.addEventListener("scroll", function () {
      trackDirection();
      requestUpdate();
    }, { passive: true });
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
