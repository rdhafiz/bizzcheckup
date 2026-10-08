// Runs in <head> before the page is drawn (loaded without "defer"), so content that will
// animate in - the hero included - is hidden from the very first paint. Without this, the
// hero would appear, vanish when motion.js starts, and then fade in: a visible flash.
//
// Still fail-open: this only sets the flags when motion can actually run, motion.js takes
// over (or removes them) as soon as it loads, and a CSS fail-safe shows everything after
// 1.5 s if motion.js never arrives. See docs/19-motion.md.
(function () {
  try {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    if (!("IntersectionObserver" in window)) return;
    if (document.visibilityState !== "visible") return; // motion.js arms once the tab is shown
    document.documentElement.classList.add("motion-ready", "motion-boot");
  } catch (e) { /* never block the page */ }
})();
