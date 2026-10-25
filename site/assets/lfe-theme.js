/* LFE theme mechanism — load this in <head> (it sets the theme before paint).
   Pairs with lfe.css. A page opts in by having a button:
     <button class="theme-toggle" id="themeToggle">
       <span class="glyph">◐</span> <span id="themeLabel">Dark</span>
     </button>
*/
(function () {
  var root = document.documentElement;

  // 1. Set theme before first paint: saved choice, else system preference.
  var saved = null;
  try { saved = localStorage.getItem("lfe-theme"); } catch (e) {}
  root.dataset.theme =
    saved || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");

  // 2. Wire the toggle once the DOM exists.
  function sync() {
    var toggle = document.getElementById("themeToggle");
    var label = document.getElementById("themeLabel");
    if (!toggle) return;
    var next = root.dataset.theme === "dark" ? "Light" : "Dark";
    // Icon toggles name the whole action ("Dark mode"); older text toggles keep one word.
    if (toggle.classList.contains("icon-toggle")) {
      next += " mode";
      toggle.setAttribute("aria-label", next);
    }
    if (label) label.textContent = next;
  }
  function wire() {
    var toggle = document.getElementById("themeToggle");
    if (!toggle) return;
    toggle.addEventListener("click", function () {
      root.dataset.theme = root.dataset.theme === "dark" ? "light" : "dark";
      try { localStorage.setItem("lfe-theme", root.dataset.theme); } catch (e) {}
      sync();
    });
    sync();
  }

  // 3. Scroll-spy for the sticky house nav (.lfe-nav): the section currently
  //    in view gets .is-current on its nav link — darker, bolder. Opt-in by
  //    simply having a .lfe-nav whose links are same-page hash links.
  //
  //    Deliberately NOT IntersectionObserver-based: IO only reports elements
  //    whose visibility CHANGED, so a slow continuous scroll can leave a stale
  //    highlight (short section wins a boundary moment; tall neighbour never
  //    re-fires). Instead we measure directly: the current section is the
  //    LAST one whose top has crossed the reading line (~28% down the
  //    viewport). A handful of getBoundingClientRect calls per animation
  //    frame — cheap, deterministic, no event-ordering traps.
  function spy() {
    var nav = document.querySelector(".lfe-nav");
    if (!nav) return;
    var pairs = [];
    var links = [].slice.call(nav.querySelectorAll('a[href^="#"]'));
    links.forEach(function (link) {
      var id = link.getAttribute("href").slice(1);
      var el = id && document.getElementById(id);
      if (el) pairs.push({ link: link, el: el });
    });
    if (!pairs.length) return;

    // No rAF throttling on purpose: rAF suspends in unfocused windows, which
    // makes the highlight go stale; seven rect reads per scroll event are
    // cheap enough to run directly (scroll events are already coalesced).
    function update() {
      var line = window.innerHeight * 0.28;
      var current = null;
      pairs.forEach(function (pair) {
        if (pair.el.getBoundingClientRect().top <= line) current = pair.link;
      });
      links.forEach(function (link) {
        link.classList.toggle("is-current", link === current);
      });
    }
    window.addEventListener("scroll", update, { passive: true });
    window.addEventListener("resize", update, { passive: true });
    update();
  }

  function boot() { wire(); spy(); }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }

  // Keep other tabs (and same-origin iframes that load this script) in step
  // when the theme changes anywhere.
  window.addEventListener("storage", function (event) {
    if (event.key === "lfe-theme" && event.newValue) {
      root.dataset.theme = event.newValue;
      sync();
    }
  });
})();
