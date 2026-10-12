/* centaurXiv theme toggle: cycles auto → light → dark → auto.
   Persists choice in localStorage key `centaurxiv-theme`.
   FOUC prevention: pages also inline a tiny head script that applies a stored
   light/dark preference before paint.

   Placement: in-document header/nav chrome (scrolls away). Not position:fixed. */
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
      '</span><span class="theme-toggle-label">' +
      LABELS[mode] +
      "</span>";
  }

  function nextMode(mode) {
    return MODES[(MODES.indexOf(mode) + 1) % MODES.length];
  }

  function makeChrome(inline) {
    var el = document.createElement(inline ? "span" : "div");
    el.className =
      "theme-toggle-chrome" + (inline ? " theme-toggle-chrome--inline" : "");
    return el;
  }

  /* Prefer existing top chrome; never append to body end (would sit at footer). */
  function resolveMount() {
    var explicit = document.querySelector("[data-theme-toggle-mount]");
    if (explicit) return explicit;

    // Atlas: stable slot above #panel so panel.innerHTML rewrites don't remove it
    var sidebar = document.getElementById("sidebar");
    var panel = document.getElementById("panel");
    if (sidebar && panel) {
      var atlasChrome = document.getElementById("theme-toggle-chrome");
      if (!atlasChrome) {
        atlasChrome = makeChrome(false);
        atlasChrome.id = "theme-toggle-chrome";
        sidebar.insertBefore(atlasChrome, panel);
      }
      return atlasChrome;
    }

    var header = document.querySelector("main.page > header");
    if (header) {
      var headerNav = header.querySelector("nav");
      if (headerNav) {
        var inline = makeChrome(true);
        headerNav.appendChild(inline);
        return inline;
      }
      var headerChrome = makeChrome(false);
      header.appendChild(headerChrome);
      return headerChrome;
    }

    var topNav = document.querySelector("main.page > nav");
    if (topNav) {
      var navChrome = makeChrome(true);
      topNav.appendChild(navChrome);
      return navChrome;
    }

    var crumb = document.querySelector("main.page > .breadcrumb");
    if (crumb && crumb.parentNode) {
      var crumbChrome = makeChrome(false);
      crumb.parentNode.insertBefore(crumbChrome, crumb);
      return crumbChrome;
    }

    var main = document.querySelector("main.page");
    if (main) {
      var mainChrome = makeChrome(false);
      main.insertBefore(mainChrome, main.firstChild);
      return mainChrome;
    }

    var fallback = makeChrome(false);
    document.body.insertBefore(fallback, document.body.firstChild);
    return fallback;
  }

  function ensureButton() {
    var existing = document.querySelector(".theme-toggle");
    if (existing) return existing;
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "theme-toggle";
    resolveMount().appendChild(btn);
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
