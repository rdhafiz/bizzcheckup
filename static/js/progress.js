// Smooth live progress for the check-up page.
//
// HTMX fetches the latest progress every second into #progress-data (a hidden element).
// This script animates the visible bar and steps towards that value:
// - the bar glides instead of jumping, and creeps forward slowly during long steps
//   (e.g. Google's PageSpeed test) so the page never looks frozen;
// - steps are ticked off one by one as the bar passes them, even when the server
//   finished several of them at once;
// - at 100% a short success animation plays, then the report opens.
(function () {
  "use strict";

  var card = document.querySelector("[data-progress-card]");
  if (!card) return;

  var reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var bar = card.querySelector("[data-bar]");
  var percentText = card.querySelector("[data-percent]");
  var stepText = card.querySelector("[data-step-text]");
  var steps = Array.prototype.slice.call(card.querySelectorAll(".progress-step"));

  var shown = Number(bar.value) || 0; // what the visitor sees
  var target = shown; // what the server last reported
  var status = "running";
  var lastUpdate = performance.now();
  var finishing = false;
  var serverStep = stepText.textContent;

  function readServer() {
    var data = card.querySelector("#progress-data [data-progress]");
    if (!data) return;
    var progress = Number(data.getAttribute("data-progress")) || 0;
    status = data.getAttribute("data-status") || "running";
    if (status === "failed") {
      window.location.reload(); // the page now explains what went wrong
      return;
    }
    if (status === "done") progress = 100;
    if (progress > target) {
      target = progress;
      lastUpdate = performance.now();
    }
    serverStep = data.getAttribute("data-step") || serverStep;
  }

  // While a step takes long, creep a little towards its end, but never past it: the bar
  // must not claim work that isn't done yet.
  function creepLimit() {
    for (var i = 0; i < steps.length; i++) {
      var start = Number(steps[i].getAttribute("data-start"));
      var end = Number(steps[i].getAttribute("data-end"));
      if (target >= start && target < end) return Math.max(target, end - 2);
    }
    return target;
  }

  function paint() {
    var value = Math.round(shown);
    // While the bar is catching up, name the step it's on; once it has caught up, show
    // the server's more detailed message (e.g. "Measuring speed with Google PageSpeed…").
    var label = serverStep;
    if (shown < target - 1 || status === "done") {
      steps.forEach(function (li) {
        if (value >= Number(li.getAttribute("data-start")) && value < Number(li.getAttribute("data-end"))) {
          label = li.querySelector(".progress-step__label").textContent;
        }
      });
    }
    if (stepText.textContent !== label) stepText.textContent = label;
    bar.value = value;
    bar.textContent = value + "%";
    percentText.textContent = value;
    steps.forEach(function (li) {
      var start = Number(li.getAttribute("data-start"));
      var end = Number(li.getAttribute("data-end"));
      var state = value >= end ? "done" : value >= start ? "active" : "pending";
      if (!li.classList.contains("is-" + state)) {
        li.classList.remove("is-done", "is-active", "is-pending");
        li.classList.add("is-" + state);
        li.querySelector("[data-step-state]").textContent = "(" + state + ")";
      }
    });
  }

  function tick(now) {
    if (reduceMotion) {
      shown = target;
    } else if (shown < target) {
      // Glide towards the server's value at a calm, steady pace (about 15% a second), so
      // quick steps like the category checks are still ticked off one by one.
      shown = Math.min(target, shown + 0.25);
    } else if (status === "running") {
      // No news for a while: creep slowly (about 1% every 2 seconds).
      var idle = (now - lastUpdate) / 1000;
      var limit = creepLimit();
      if (idle > 1.5 && shown < limit) shown = Math.min(limit, shown + 0.008);
    }
    paint();

    if (status === "done" && shown >= 100 && !finishing) {
      finishing = true;
      card.classList.add("is-complete");
      var eyebrow = document.querySelector("[data-progress-eyebrow]");
      if (eyebrow) eyebrow.textContent = "Check-up complete";
      setTimeout(function () {
        window.location.assign(card.getAttribute("data-report-url"));
      }, reduceMotion ? 600 : 1600);
      return;
    }
    window.requestAnimationFrame(tick);
  }

  document.body.addEventListener("htmx:afterSwap", function (event) {
    if (event.target && event.target.id === "progress-data") readServer();
  });

  readServer();
  window.requestAnimationFrame(tick);
})();
