/* centaurXiv theme toggle: cycles auto → light → dark → auto.
   Persists choice in localStorage key `centaurxiv-theme`.
   FOUC prevention: pages also inline a tiny head script that applies a stored
   light/dark preference before paint. */
(function () {
  var STORAGE_KEY = "centaurxiv-theme";
  var MODES = ["auto", "light", "dark"];
  var LABELS = { auto: "Auto", light: "Light", dark: "Dark" };
  var ICONS = { auto: "◐", light: "☀", dark: "☾" };

  function storedMode() {
    try {
      var v = localStorage.getItem(STORAGE_KEY);
      if (v === "light" || v === "dark" || v === "auto") return v;
    } catch (e) {}
    return "auto";
  }

  function applyMode(mode) {
    var root = document.documentElement;
    if (mode === "light" || mode === "dark") {
      root.setAttribute("data-theme", mode);
    } else {
      root.removeAttribute("data-theme");
    }
  }

  function persist(mode) {
    try {
      if (mode === "auto") localStorage.removeItem(STORAGE_KEY);
      else localStorage.setItem(STORAGE_KEY, mode);
    } catch (e) {}
  }

  function updateButton(btn, mode) {
    btn.setAttribute("data-mode", mode);
    btn.setAttribute(
      "aria-label",
      "Color theme: " + LABELS[mode] + ". Click to change."
    );
    btn.title = "Theme: " + LABELS[mode] + " (click to cycle)";
    btn.innerHTML =
      '<span class="theme-toggle-icon" aria-hidden="true">' +
      ICONS[mode] +
      "</span><span class=\"theme-toggle-label\">" +
      LABELS[mode] +
      "</span>";
  }

  function nextMode(mode) {
    return MODES[(MODES.indexOf(mode) + 1) % MODES.length];
  }

  function ensureButton() {
    var existing = document.querySelector(".theme-toggle");
    if (existing) return existing;
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "theme-toggle";
    document.body.appendChild(btn);
    return btn;
  }

  function init() {
    var mode = storedMode();
    applyMode(mode);
    var btn = ensureButton();
    updateButton(btn, mode);
    btn.addEventListener("click", function () {
      mode = nextMode(mode);
      persist(mode);
      applyMode(mode);
      updateButton(btn, mode);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
