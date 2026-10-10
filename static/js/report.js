// Report page: "Copy share link", the issue filters, "Copy" on code
// blocks and the sidebar's "you are here" highlight.
document.addEventListener("DOMContentLoaded", function () {
  setUpCopyLink();
  setUpIssueFilters();
  setUpIssueLinks();
  setUpCopyCode();
  setUpSectionHighlight();
});

// Filter the issue list by vital sign and by severity. Without JavaScript the filters
// stay hidden and every issue is shown. A vital sign in the sidebar filters too.
function setUpIssueFilters() {
  var tools = document.querySelector("[data-issue-tools]");
  if (!tools) return;
  var rows = Array.prototype.slice.call(document.querySelectorAll(".issue-row"));
  var empty = document.querySelector("[data-issue-empty]");
  var state = { category: "", severity: "" };

  function press(attribute, value) {
    tools.querySelectorAll("[" + attribute + "]").forEach(function (chip) {
      chip.setAttribute("aria-pressed", chip.getAttribute(attribute) === value ? "true" : "false");
    });
  }
  function apply() {
    var shown = 0;
    rows.forEach(function (row) {
      var visible = (!state.category || row.getAttribute("data-category") === state.category)
        && (!state.severity || row.getAttribute("data-severity") === state.severity);
      row.hidden = !visible;
      if (visible) shown += 1;
    });
    if (empty) empty.hidden = shown > 0;
    press("data-filter-category", state.category);
    press("data-filter-severity", state.severity);
    document.querySelectorAll("a[data-filter-category]").forEach(function (link) {
      link.classList.toggle("is-active", link.getAttribute("data-filter-category") === state.category);
    });
  }

  tools.addEventListener("click", function (event) {
    var chip = event.target.closest("button");
    if (!chip) return;
    if (chip.hasAttribute("data-filter-category")) state.category = chip.getAttribute("data-filter-category");
    if (chip.hasAttribute("data-filter-severity")) state.severity = chip.getAttribute("data-filter-severity");
    apply();
  });
  // Vital signs (sidebar, or the overview on small screens): show that sign's issues.
  // The link itself scrolls to the list.
  document.querySelectorAll("a[data-filter-category]").forEach(function (link) {
    link.addEventListener("click", function () {
      var category = link.getAttribute("data-filter-category");
      state.category = state.category === category ? "" : category;
      state.severity = "";
      apply();
    });
  });
  tools.hidden = false;
  apply();
}

// "See how to fix it" (and any link to an issue): open that issue and show it, even if
// a filter was hiding it.
function setUpIssueLinks() {
  document.addEventListener("click", function (event) {
    var link = event.target.closest && event.target.closest('a[href^="#issue-"]');
    if (!link) return;
    var row = document.getElementById(link.getAttribute("href").slice(1));
    if (!row) return;
    if (row.hidden) {
      var all = document.querySelectorAll('[data-filter-category=""], [data-filter-severity=""]');
      all.forEach(function (chip) { chip.click(); });
    }
    var details = row.querySelector("details.issue");
    if (details) details.open = true;
  });
}

// Sidebar: mark the section being read, so the reader always knows where they are.
function setUpSectionHighlight() {
  var links = Array.prototype.slice.call(document.querySelectorAll(".side-nav a[href^='#']"));
  if (!links.length || !("IntersectionObserver" in window)) return;
  var byId = {};
  links.forEach(function (link) { byId[link.getAttribute("href").slice(1)] = link; });
  var observer = new IntersectionObserver(function (entries) {
    entries.forEach(function (entry) {
      if (!entry.isIntersecting) return;
      links.forEach(function (link) { link.removeAttribute("aria-current"); });
      byId[entry.target.id].setAttribute("aria-current", "true");
    });
  }, { rootMargin: "-30% 0px -60% 0px" });
  Object.keys(byId).forEach(function (id) {
    var section = document.getElementById(id);
    if (section) observer.observe(section);
  });
}

// "Copy" on a suggested fix (e.g. a page's JSON-LD): copies the code exactly as shown.
function setUpCopyCode() {
  document.addEventListener("click", function (event) {
    var button = event.target.closest && event.target.closest("[data-copy-code]");
    if (!button) return;
    var code = button.parentElement.querySelector("code");
    if (!code) return;
    var text = code.textContent;

    function done(label) {
      button.textContent = label;
      setTimeout(function () { button.textContent = "Copy"; }, 2000);
    }
    function selectIt() {  // fallback: select the code so Ctrl+C works
      var range = document.createRange();
      range.selectNodeContents(code);
      var selection = window.getSelection();
      selection.removeAllRanges();
      selection.addRange(range);
      done("Selected: press Ctrl+C");
    }

    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(function () { done("Copied"); }, selectIt);
    } else {
      selectIt();
    }
  });
}

function setUpCopyLink() {
  var button = document.querySelector("[data-copy-link]");
  var status = document.querySelector("[data-copy-status]");
  if (!button) return;

  button.addEventListener("click", function () {
    var url = button.getAttribute("data-copy-link");
    function done(message) { if (status) status.textContent = message; }

    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(url).then(
        function () { done("Link copied. Anyone with it can open this report."); },
        function () { window.prompt("Copy this link:", url); }
      );
    } else {
      window.prompt("Copy this link:", url);  // older browsers / plain http
    }
  });
}
