// Prototype chrome shared by the variants: one screen at a time (#landing,
// #inicio, #aviso) and a small switcher that stays out of each design's way.
(function () {
  const SCREENS = [
    ["landing", "Landing"],
    ["inicio", "Inicio"],
    ["aviso", "Aviso"],
  ];

  function show() {
    const want = location.hash.slice(1);
    const current = SCREENS.some(([id]) => id === want) ? want : "landing";
    document.querySelectorAll("body > [data-screen]").forEach((el) => {
      el.hidden = el.dataset.screen !== current;
    });
    document.querySelectorAll(".proto-switch a[data-to]").forEach((a) => {
      a.setAttribute("aria-current", a.dataset.to === current ? "page" : "false");
    });
    document.documentElement.dataset.view = current;
    window.scrollTo(0, 0);
  }

  function chrome() {
    if (new URLSearchParams(location.search).has("bare")) return;
    const nav = document.createElement("nav");
    nav.className = "proto-switch";
    nav.setAttribute("aria-label", "Pantallas del prototipo");
    nav.innerHTML =
      `<a href="index.html" title="Volver a las variantes">Variantes</a>` +
      SCREENS.map(([id, label]) => `<a href="#${id}" data-to="${id}">${label}</a>`).join("");
    document.body.appendChild(nav);
    const style = document.createElement("style");
    style.textContent = `
      .proto-switch{position:fixed;z-index:999;right:12px;bottom:12px;display:flex;gap:2px;padding:3px;
        background:#fff;border-radius:999px;box-shadow:0 2px 10px rgba(0,0,0,.18),0 0 0 1px rgba(0,0,0,.08);
        font:500 12px/1 system-ui,-apple-system,"Segoe UI",sans-serif;}
      .proto-switch a{color:#333;text-decoration:none;padding:7px 10px;border-radius:999px;letter-spacing:0}
      .proto-switch a:first-child{color:#777}
      .proto-switch a[aria-current="page"]{background:#222;color:#fff}
      .proto-switch a:focus-visible{outline:2px solid #2563eb;outline-offset:1px}
      @media (max-width: 767px){.proto-switch{bottom:76px;right:8px}}
    `;
    document.head.appendChild(style);
  }

  window.addEventListener("hashchange", show);
  document.addEventListener("DOMContentLoaded", () => {
    chrome();
    show();
  });
})();
