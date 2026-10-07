// "Copy share link" on the report page.
document.addEventListener("DOMContentLoaded", function () {
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
});
