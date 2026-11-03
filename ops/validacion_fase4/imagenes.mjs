// Imágenes para WhatsApp de la Prueba A (Validación comercial de la Fase 4).
// En lugar del PDF y de la planilla compartida: lo que se manda a cada agencia
// es una imagen PNG de 1080 px de ancho.
//
//   node imagenes.mjs radar   <radar.json> <zona> <semana YYYY-MM-DD> <salida.png> ["Agencia"]
//   node imagenes.mjs monitor <monitor.json> <fecha YYYY-MM-DD> <salida.png> "Agencia" [zona]
//
// radar.json   = salida de radar.sql: lista de {zone, rows}.
// monitor.json = filas de monitor.sql (una por auto del stock de la agencia).
// Reglas de texto: «dejó de publicarse», nunca «vendido»; precios publicados,
// no de venta; sin promesas de ganancias.
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";

// require() also finds a globally installed playwright (NODE_PATH); import does not.
const { chromium } = createRequire(import.meta.url)("playwright");

const ZONES = { amba: "AMBA", cordoba: "Córdoba", litoral: "Rosario y Litoral", todas: "todo el país" };
const FIX = [["Ecosport", "EcoSport"], ["Vw ", "VW "]];

const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" })[c]);
const usd = (v) => (v == null || v === "" ? "—" : "US$ " + Math.round(Number(v)).toLocaleString("es-AR"));
const title = (s) => String(s).replace(/\b\p{L}/gu, (c) => c.toUpperCase());
const nice = (make, model) => FIX.reduce((n, [a, b]) => n.replace(a, b), `${title(make)} ${title(model)}`);
const ddmm = (iso) => { const [y, m, d] = iso.split("-"); return `${d}/${m}/${y}`; };
const addDays = (iso, n) => { const d = new Date(iso + "T12:00:00Z"); d.setUTCDate(d.getUTCDate() + n); return d.toISOString().slice(0, 10); };

const CSS = `
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { width: 1080px; background: #f1f3f7; font-family: Inter, Arial, Helvetica, sans-serif; color: #14213d; }
  .card { margin: 36px; background: #fff; border: 1px solid #d8dde6; }
  .bar { height: 10px; background: #ffe14d; }
  header { padding: 40px 48px 28px; border-bottom: 1px solid #d8dde6; }
  .brand { font-size: 22px; font-weight: 700; letter-spacing: 1px; color: #4e5a73; }
  h1 { font-size: 52px; line-height: 1.1; letter-spacing: -1px; margin-top: 14px; }
  .sub { font-size: 26px; line-height: 1.4; color: #4e5a73; margin-top: 12px; }
  .row { display: flex; gap: 24px; padding: 26px 48px; border-bottom: 1px solid #e6e9ef; align-items: flex-start; }
  .n { width: 52px; height: 52px; border-radius: 26px; background: #14213d; color: #fff; font-size: 24px; font-weight: 700;
       display: flex; align-items: center; justify-content: center; flex: none; }
  .main { flex: 1; min-width: 0; }
  .model { font-size: 32px; font-weight: 700; }
  .years { font-weight: 400; color: #4e5a73; }
  .facts { font-size: 24px; line-height: 1.45; color: #4e5a73; margin-top: 6px; }
  .price { text-align: right; flex: none; }
  .price b { display: block; font-size: 32px; }
  .price span { font-size: 21px; color: #4e5a73; }
  .cheap { display: inline-block; margin-top: 10px; font-size: 22px; background: #fff7c2; padding: 4px 12px; border-radius: 6px; color: #14213d; }
  .chip { display: inline-block; margin-top: 10px; font-size: 23px; font-weight: 700; padding: 6px 14px; border-radius: 6px; }
  .up { background: #fbe3e3; color: #8a1c1c; } .ok { background: #e5f4e4; color: #1d5e2a; }
  .low { background: #e7f1fb; color: #1f4f80; } .few { background: #eef0f4; color: #4e5a73; }
  .alert { margin-top: 10px; font-size: 22px; color: #14213d; }
  footer { padding: 28px 48px 36px; font-size: 20px; line-height: 1.5; color: #4e5a73; background: #f7f8fa; }
`;

function page(body) {
  return `<!doctype html><html lang="es"><head><meta charset="utf-8"><style>${CSS}</style></head>
<body><div class="card"><div class="bar"></div>${body}</div></body></html>`;
}

function radarHtml(rows, zone, week, agency) {
  const items = rows.map((r) => {
    const days = r.median_days == null ? "" : ` · unos ${Math.round(r.median_days)} días publicados`;
    const gone = r.has_days ? `${r.gone} dejaron de publicarse${days}` : `${r.active} publicados ahora (pocas bajas para medir)`;
    const cheaper = r.cheapest_dept && r.cheapest_dept_med != null && r.median_usd != null && r.cheapest_dept_med <= r.median_usd * 0.97
      ? `<div class="cheap">Más barato en ${esc(r.cheapest_dept === "Comuna 1" ? "CABA" : r.cheapest_dept.replace(/^Comuna/, "CABA, comuna"))}: ${usd(r.cheapest_dept_med)}</div>` : "";
    return `<div class="row"><div class="n">${r.rk}</div><div class="main">
      <div class="model">${esc(nice(r.make, r.model))} <span class="years">${r.year_from}–${r.year_from + 1}</span></div>
      <div class="facts">${gone}</div>${cheaper}</div>
      <div class="price"><b>${usd(r.median_usd)}</b><span>precio mediano</span></div></div>`;
  }).join("");
  return page(`<header><div class="brand">ESE AUTO · RADAR SEMANAL</div>
    <h1>Qué se movió en ${esc(ZONES[zone] ?? zone)}</h1>
    <div class="sub">Semana del ${ddmm(week).slice(0, 5)} al ${ddmm(addDays(week, 6))}${agency ? ` · para ${esc(agency)}` : ""}.<br>
    Los 10 modelos usados que más dejaron de publicarse.</div></header>${items}
    <footer>«Dejaron de publicarse» = avisos que ya no aparecen en los portales que revisamos; no sabemos si se vendieron.
    Precios publicados en dólares, sin anticipos ni cuotas. «Más barato en» = la zona con la mediana más baja (3 avisos o más).
    Fuente: Ese Auto, con avisos públicos de portales de clasificados.</footer>`);
}

const READING = {
  "por encima de la mediana": ["up", "Más caro que la mayoría"],
  "en línea con la mediana": ["ok", "En línea con el mercado"],
  "entre el 25 % más barato": ["low", "Entre los más baratos"],
  "pocos comparables": ["few", "Pocos avisos parecidos"],
};

function monitorHtml(rows, date, agency, zone) {
  const items = rows.map((r) => {
    const [cls, label] = READING[r.lectura] ?? ["few", r.lectura];
    const diff = r.dif_vs_mediana_pct == null ? "" : ` (${Number(r.dif_vs_mediana_pct) > 0 ? "+" : ""}${String(r.dif_vs_mediana_pct).replace(".", ",")} %)`;
    const facts = r.comparables ? `${r.comparables} avisos parecidos · mediana ${usd(r.mediana)}${diff}` : "Sin avisos parecidos en tu zona";
    const alert = r.nuevo_mas_barato
      ? `<div class="alert">⚠ Apareció uno parecido a <b>${usd(r.nuevo_mas_barato)}</b> (${r.nuevo_anio}${r.nuevo_km ? `, ${Number(r.nuevo_km).toLocaleString("es-AR")} km` : ""}). Te pasamos el link.</div>` : "";
    return `<div class="row"><div class="n">${r.fila}</div><div class="main">
      <div class="model">${esc(nice(r.make, r.model))} <span class="years">${r.year}${r.km ? ` · ${Number(r.km).toLocaleString("es-AR")} km` : ""}</span></div>
      <div class="facts">${facts}</div><div class="chip ${cls}">${label}</div>${alert}</div>
      <div class="price"><b>${usd(r.precio_agencia)}</b><span>tu precio</span></div></div>`;
  }).join("");
  return page(`<header><div class="brand">ESE AUTO · TU STOCK</div>
    <h1>Cómo está tu stock hoy</h1>
    <div class="sub">${esc(agency)} · ${ddmm(date)}${zone ? ` · comparado en ${esc(ZONES[zone] ?? zone)}` : ""}.</div></header>${items}
    <footer>Comparamos cada auto con avisos activos de tu zona: misma marca y modelo, año ±1 y km ±25 %, vistos en los últimos 30 días.
    «Más caro que la mayoría» = más de 5 % arriba de la mediana. Con menos de 5 avisos parecidos no damos lectura.
    Son precios publicados, no de venta.</footer>`);
}

async function shot(html, out) {
  const browser = await chromium.launch();
  const p = await browser.newPage({ viewport: { width: 1080, height: 800 }, deviceScaleFactor: 1 });
  await p.setContent(html, { waitUntil: "load" });
  await p.screenshot({ path: out, fullPage: true });
  await browser.close();
  console.log(out);
}

const [kind, src, ...rest] = process.argv.slice(2);
const data = JSON.parse(readFileSync(src, "utf8"));
if (kind === "radar") {
  const [zone, week, out, agency] = rest;
  const rows = data.find((z) => z.zone === zone)?.rows ?? [];
  await shot(radarHtml(rows, zone, week, agency), out);
} else if (kind === "monitor") {
  const [date, out, agency, zone] = rest;
  await shot(monitorHtml(data, date, agency, zone), out);
} else {
  console.error("uso: node imagenes.mjs radar|monitor …");
  process.exit(1);
}
