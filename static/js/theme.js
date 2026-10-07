// Light/dark theme: follows the system setting until the visitor picks one.
// Loaded in <head> without "defer" so the theme is set before the page paints
// (no white flash in dark mode).
(function () {
  var KEY = "bizzcheckup-theme";
  var root = document.documentElement;

  function stored() {
    try { return localStorage.getItem(KEY); } catch (e) { return null; }
  }

  function isDark() {
    var choice = root.getAttribute("data-theme");
    if (choice) return choice === "dark";
    return window.matchMedia("(prefers-color-scheme: dark)").matches;
  }

  var saved = stored();
  if (saved === "light" || saved === "dark") root.setAttribute("data-theme", saved);

  document.addEventListener("DOMContentLoaded", function () {
    var button = document.querySelector("[data-theme-toggle]");
    if (!button) return;

    function sync() { button.setAttribute("aria-pressed", String(isDark())); }
    sync();

    button.addEventListener("click", function () {
      var next = isDark() ? "light" : "dark";
      root.setAttribute("data-theme", next);
      try { localStorage.setItem(KEY, next); } catch (e) { /* private mode */ }
      sync();
    });
  });
})();
