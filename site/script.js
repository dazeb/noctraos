// Copy buttons: <button data-copy="id-of-code-element">
(function () {
  document.querySelectorAll("button[data-copy]").forEach(function (btn) {
    var target = document.getElementById(btn.getAttribute("data-copy"));
    if (!target) return;
    btn.addEventListener("click", function () {
      var reset = function (label, ms) { btn.textContent = label; setTimeout(function () { btn.textContent = "Copy"; }, ms); };
      var fallback = function () {
        var r = document.createRange(); r.selectNodeContents(target);
        var s = window.getSelection(); s.removeAllRanges(); s.addRange(r);
        reset("Press Ctrl+C", 2200);
      };
      try {
        navigator.clipboard.writeText(target.textContent).then(function () { reset("Copied", 1600); }, fallback);
      } catch (e) { fallback(); }
    });
  });
})();
