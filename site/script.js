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

// Lightbox for the screenshots: <figure class="shot"><a href="full-size image"><img alt="..."></a></figure>.
// Click opens it large; click the image (or press Z) for actual size; arrows, swipe and the buttons move between screenshots;
// Esc or a click outside closes. Plain links without this script (or without <dialog> support), so nothing depends on it.
(function () {
  var links = Array.prototype.slice.call(document.querySelectorAll(".shot > a[href]"));
  var probe = document.createElement("dialog");
  if (!links.length || typeof probe.showModal !== "function") return;

  var icon = function (d) { return '<svg viewBox="0 0 24 24" aria-hidden="true"><path d="' + d + '"/></svg>'; };
  var dialog = document.createElement("dialog");
  dialog.className = "lb";
  dialog.setAttribute("aria-label", "Screenshot viewer");
  dialog.innerHTML =
    '<div class="lb-bar">' +
      '<div class="lb-nav">' +
        '<button type="button" class="lb-prev" aria-label="Previous screenshot">' + icon("M15 5l-7 7 7 7") + "</button>" +
        '<span class="lb-count" aria-live="polite"></span>' +
        '<button type="button" class="lb-next" aria-label="Next screenshot">' + icon("M9 5l7 7-7 7") + "</button>" +
      "</div>" +
      '<div class="lb-tools">' +
        '<button type="button" class="lb-zoom" aria-pressed="false">' + icon("M10.5 4.5a6 6 0 1 0 0 12 6 6 0 0 0 0-12zM15 15l5 5M10.5 8v5M8 10.5h5") + "<span>Actual size</span></button>" +
        '<button type="button" class="lb-close" aria-label="Close" autofocus>' + icon("M6 6l12 12M18 6L6 18") + "</button>" +
      "</div>" +
    "</div>" +
    '<div class="lb-stage"><img alt=""></div>' +
    '<p class="lb-cap"></p>';
  document.body.appendChild(dialog);
  document.documentElement.classList.add("lb-ready");

  var $ = function (s) { return dialog.querySelector(s); };
  var stage = $(".lb-stage"), img = $(".lb-stage img"), cap = $(".lb-cap"), count = $(".lb-count");
  var zoomBtn = $(".lb-zoom"), zoomText = zoomBtn.querySelector("span");
  var index = 0, opener = null, loading = 0;

  function thumbOf(a) { return a.querySelector("img"); }
  function captionOf(a) {
    var fig = a.parentNode.querySelector("figcaption");
    var t = fig && fig.textContent.trim();
    return t || (thumbOf(a) && thumbOf(a).alt) || "";
  }
  function setZoom(on, focalX, focalY) {
    on = !!on && !dialog.classList.contains("fits");
    dialog.classList.toggle("zoomed", on);
    zoomBtn.setAttribute("aria-pressed", String(on));
    zoomText.textContent = on ? "Fit to screen" : "Actual size";
    if (on) { // keep the point that was clicked under the pointer, like a magnifier
      stage.scrollLeft = (focalX == null ? 0.5 : focalX) * img.naturalWidth - stage.clientWidth / 2;
      stage.scrollTop = (focalY == null ? 0.5 : focalY) * img.naturalHeight - stage.clientHeight / 2;
    } else { stage.scrollLeft = stage.scrollTop = 0; }
  }
  function measure() { // zooming only helps when the screenshot is larger than the space it is shown in
    var fits = img.naturalWidth <= stage.clientWidth - 2 && img.naturalHeight <= stage.clientHeight - 2;
    dialog.classList.toggle("fits", fits);
    zoomBtn.disabled = fits;
    if (fits) setZoom(false);
  }
  function preload(i) { var a = links[(i + links.length) % links.length]; (new Image()).src = a.href; }
  function show(i) {
    index = (i + links.length) % links.length;
    var a = links[index], ticket = ++loading, thumb = thumbOf(a);
    setZoom(false);
    img.alt = thumb ? thumb.alt : "";
    img.classList.remove("ready");
    img.src = thumb ? thumb.currentSrc || thumb.src : a.href;     // the thumbnail is already cached: show it at once ...
    void img.offsetWidth;                                           // commit the hidden state, then reveal: the pop-in transition
    img.classList.add("ready");
    var full = new Image();                                         // ... and swap in the sharp one when it has loaded
    full.onload = function () { if (ticket === loading) { img.src = a.href; measure(); } };
    full.src = a.href;
    cap.textContent = captionOf(a);
    count.textContent = (index + 1) + " / " + links.length;
    var single = links.length < 2;
    $(".lb-prev").disabled = $(".lb-next").disabled = single;
    preload(index + 1); preload(index - 1);
    measure();
  }
  function open(i, from) {
    opener = from || null;
    document.documentElement.style.paddingRight = (window.innerWidth - document.documentElement.clientWidth) + "px";
    document.documentElement.classList.add("lb-open");
    dialog.showModal();
    show(i);
  }
  function cleanup() { // safe to run twice: Esc closes the dialog natively (the "close" event), the buttons call close()
    document.documentElement.classList.remove("lb-open");
    document.documentElement.style.paddingRight = "";
    loading++;
    if (opener && opener.focus) opener.focus({ preventScroll: true });
  }
  function close() { if (dialog.open) { dialog.close(); cleanup(); } }
  dialog.addEventListener("close", cleanup);
  links.forEach(function (a, i) {
    a.addEventListener("click", function (e) {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return; // let "open in a new tab" work
      e.preventDefault();
      open(i, a);
    });
  });
  $(".lb-close").addEventListener("click", close);
  $(".lb-prev").addEventListener("click", function () { show(index - 1); });
  $(".lb-next").addEventListener("click", function () { show(index + 1); });
  zoomBtn.addEventListener("click", function () { setZoom(!dialog.classList.contains("zoomed")); });
  img.addEventListener("click", function (e) {
    var r = img.getBoundingClientRect();
    setZoom(!dialog.classList.contains("zoomed"), (e.clientX - r.left) / r.width, (e.clientY - r.top) / r.height);
  });
  dialog.addEventListener("click", function (e) { if (e.target === dialog || e.target === stage) close(); }); // outside the image
  dialog.addEventListener("keydown", function (e) {
    if (e.altKey || e.ctrlKey || e.metaKey) return;
    var k = e.key;
    if (k === "ArrowLeft") { show(index - 1); e.preventDefault(); }
    else if (k === "ArrowRight") { show(index + 1); e.preventDefault(); }
    else if (k === "Home") { show(0); e.preventDefault(); }
    else if (k === "End") { show(links.length - 1); e.preventDefault(); }
    else if (k === "z" || k === "Z" || k === "+" || k === "=") { setZoom(!dialog.classList.contains("zoomed")); e.preventDefault(); }
  });
  var startX = 0, startY = 0;                                       // swipe between screenshots on a touch screen
  stage.addEventListener("touchstart", function (e) { startX = e.touches[0].clientX; startY = e.touches[0].clientY; }, { passive: true });
  stage.addEventListener("touchend", function (e) {
    if (dialog.classList.contains("zoomed")) return;                // when zoomed, a swipe scrolls the image
    var dx = e.changedTouches[0].clientX - startX, dy = e.changedTouches[0].clientY - startY;
    if (Math.abs(dx) > 50 && Math.abs(dx) > 2 * Math.abs(dy)) show(index + (dx < 0 ? 1 : -1));
  }, { passive: true });
  window.addEventListener("resize", function () { if (dialog.open) measure(); });
})();
