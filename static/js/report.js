// Report page: "Copy share link" and the treatment-plan checklist.
document.addEventListener("DOMContentLoaded", function () {
  setUpCopyLink();
  setUpPlanChecklist();
});

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

// Ticks are remembered per report in this browser only (localStorage). If storage is
// blocked (private mode, strict settings) the checklist still works, it just forgets.
function setUpPlanChecklist() {
  var plan = document.querySelector("[data-plan]");
  if (!plan) return;
  var storageKey = "bizzcheckup-plan-" + plan.getAttribute("data-plan");
  var boxes = Array.prototype.slice.call(plan.querySelectorAll("[data-plan-key]"));
  var panel = document.querySelector("[data-plan-progress]");
  var count = document.querySelector("[data-plan-count]");
  var bar = document.querySelector("[data-plan-bar]");
  var reset = document.querySelector("[data-plan-reset]");

  function load() {
    try { return JSON.parse(window.localStorage.getItem(storageKey)) || []; }
    catch (e) { return []; }
  }
  function save(keys) {
    try {
      if (keys.length) window.localStorage.setItem(storageKey, JSON.stringify(keys));
      else window.localStorage.removeItem(storageKey);
    } catch (e) { /* storage unavailable: keep working without it */ }
  }
  function update() {
    var done = boxes.filter(function (box) { return box.checked; });
    save(done.map(function (box) { return box.getAttribute("data-plan-key"); }));
    if (bar) bar.value = done.length;
    if (count) {
      count.textContent = done.length === boxes.length
        ? "All " + boxes.length + " steps done. Check again to see your new score."
        : done.length + " of " + boxes.length + " steps done";
    }
  }

  var saved = load();
  boxes.forEach(function (box) {
    box.checked = saved.indexOf(box.getAttribute("data-plan-key")) !== -1;
    box.addEventListener("change", update);
  });
  if (reset) {
    reset.addEventListener("click", function () {
      boxes.forEach(function (box) { box.checked = false; });
      update();
    });
  }
  if (panel) panel.hidden = false;  // only shown when JavaScript can run it
  update();
}
