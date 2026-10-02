// Snapshot of the local Supabase (search "Ford Focus", 2026-09-28), shared by
// the four variants. Ages are illustrative; the comparables' individual
// prices are spread to match the stored price_ref (n=10, p25/mediana/p75).
window.AM = {
  searches: [
    {
      id: 67,
      name: "Ford Focus",
      vehicle: "Ford Focus",
      filters: ["2014 a 2017", "hasta 120.000 km", "AMBA"],
      fresh: 58,
      opps: 7,
      state: "on",
    },
    {
      id: 80,
      name: "Fiesta Titanium manual",
      vehicle: "Ford Fiesta Titanium",
      filters: ["2016 a 2018", "hasta USD 11.500", "manual", "hasta 150.000 km"],
      fresh: 8,
      opps: 0,
      state: "on",
    },
    {
      id: 83,
      name: "Polo Highline",
      vehicle: "Volkswagen Polo Highline",
      filters: ["desde 2017", "hasta USD 12.000"],
      state: "pending",
    },
    {
      id: 84,
      name: "Gol Trend",
      vehicle: "Volkswagen Gol Trend",
      filters: ["2016 a 2018", "hasta USD 11.500", "manual"],
      fresh: 0,
      opps: 0,
      state: "paused",
    },
  ],

  // Recent opportunities, by score.
  listings: [
    { id: 2309, name: "Ford Focus SE Plus 2016", ars: "16.500.000", usd: "10.645", km: "71.009 km", place: "Flores, CABA", source: "Autocosmos", seller: "Concesionaria", box: "Automática", score: 89, level: "high", age: "hace 4 min", img: "img/2309.jpg", status: "new" },
    { id: 2302, name: "Ford Focus 2.0 Trend 2014", ars: "10.771.000", usd: "6.949", km: "105.420 km", place: "Buenos Aires", source: "Kavak", seller: "Concesionaria", box: "Manual", score: 88, level: "high", age: "hace 16 h", img: "img/2302.jpg", status: "new" },
    { id: 2311, name: "Ford Focus SE Plus 2014", ars: "12.600.000", usd: "8.129", km: "100.000 km", place: "José C. Paz", source: "Autocosmos", seller: "Particular", box: "Automática", score: 88, level: "high", age: "hace 38 min", img: "img/2311.jpg", status: "interested", saved: true },
    { id: 2317, name: "Ford Focus S 2016", ars: "15.900.000", usd: "10.258", km: "84.007 km", place: "Flores, CABA", source: "Autocosmos", seller: "Concesionaria", box: "Manual", score: 87, level: "high", age: "hace 2 h", img: "img/2317.jpg", status: "seen" },
    { id: 2305, name: "Ford Focus SE Plus 2016", ars: "15.490.000", usd: "9.994", km: "113.759 km", place: "Buenos Aires", source: "Kavak", seller: "Concesionaria", box: "Manual", score: 85, level: "high", age: "hace 5 h", img: "img/2305.jpg", status: "contacted" },
    { id: 2301, name: "Ford Focus S 2015", ars: "15.071.000", usd: "9.723", km: "81.049 km", place: "Buenos Aires", source: "Kavak", seller: "Concesionaria", box: "Manual", score: 85, level: "high", age: "ayer", img: "img/2301.jpg", status: "seen" },
    { id: 2307, name: "Ford Focus Titanium 2017", ars: "18.241.000", usd: "11.768", km: "84.310 km", place: "Buenos Aires", source: "Kavak", seller: "Concesionaria", box: "Manual", score: 83, level: "good", age: "ayer", img: "img/2307.jpg", status: "seen" },
    { id: 2304, name: "Ford Focus S 2017", ars: "14.971.000", usd: "9.659", km: "119.405 km", place: "Buenos Aires", source: "Kavak", seller: "Concesionaria", box: "Manual", score: 83, level: "good", age: "hace 2 días", img: "img/2304.jpg", status: "discarded" },
  ],

  // Ford Focus with manual gearbox in AMBA seen the same week, cheapest first
  // (all real; 2302 is the opportunity).
  week: [
    { id: 2302, name: "Ford Focus 2.0 Trend 2014", km: "105.420 km", source: "Kavak", usd: "6.949", img: "img/2302.jpg", score: 88 },
    { id: 2209, name: "Ford Focus S 2014", km: "86.000 km", source: "Kavak", usd: "9.523", img: "img/2209.jpg", score: 82 },
    { id: 2301, name: "Ford Focus S 2015", km: "81.049 km", source: "Kavak", usd: "9.723", img: "img/2301.jpg", score: 85 },
    { id: 2305, name: "Ford Focus SE Plus 2016", km: "113.759 km", source: "Kavak", usd: "9.994", img: "img/2305.jpg", score: 85 },
    { id: 2317, name: "Ford Focus S 2016", km: "84.007 km", source: "Autocosmos", usd: "10.258", img: "img/2317.jpg", score: 87 },
  ],

  // The listing detail: id 2302, its best match on "Ford Focus".
  detail: {
    id: 2302,
    name: "Ford Focus 2.0 Trend 2014",
    title: "Ford Focus 2.0 TREND Sedan 2014",
    search: "Ford Focus",
    source: "Kavak",
    place: "Buenos Aires",
    age: "hace 16 h",
    ars: "10.771.000",
    usd: "6.949",
    usdN: 6949,
    km: "105.420 km",
    year: 2014,
    box: "Manual",
    fuel: "Nafta",
    seller: "Concesionaria",
    sellerName: "Kavak",
    score: 88,
    level: "high",
    photos: ["img/2302.jpg", "img/2302-1.jpg", "img/2302-2.jpg", "img/2302-3.jpg", "img/2302-4.jpg", "img/2302-5.jpg"],
    reasons: [
      { name: "Modelo", ok: "Modelo buscado", detail: "Ford Focus" },
      { name: "Año", ok: "Año dentro del rango", detail: "2014, buscás 2014 a 2017" },
      { name: "Kilometraje", ok: "Kilometraje compatible", detail: "105.420, tope 120.000" },
      { name: "Ubicación", ok: "Zona compatible", detail: "Buenos Aires, 0 km de tu zona" },
    ],
    breakdown: [
      { key: "price", name: "Precio", got: 35, of: 35, why: "34% debajo del mercado observado" },
      { key: "match", name: "Coincidencia con la búsqueda", got: 25, of: 25, why: "Sin preferencias adicionales" },
      { key: "trim", name: "Versión", got: 10, of: 10, why: "Sin versión preferida" },
      { key: "km", name: "Kilometraje", got: 7.95, of: 15, why: "2% menos km que publicaciones comparables" },
      { key: "recency", name: "Antigüedad de la publicación", got: 6.14, of: 10, why: "Detectado hace 16 h" },
      { key: "completeness", name: "Datos informados", got: 3.5, of: 5, why: "7 de 10 datos informados" },
    ],
    priceRef: { n: 10, p25: 9842, median: 10540, p75: 10645, diffPct: 34, level: "misma caja", medianKm: "108.000 km" },
    // Three of those ten (same make, model and gearbox, year ±1, km ±25%,
    // seen in the last 30 days — public.comparables with the seed config).
    similar: [
      { name: "Ford Focus S 2014", km: "86.000 km", source: "Kavak", usd: "9.523" },
      { name: "Ford Focus S 2015", km: "81.049 km", source: "Kavak", usd: "9.723" },
      { name: "Ford Focus SE Plus 2015", km: "117.000 km", source: "Facebook Marketplace", usd: "10.645" },
    ],
    // The score in words: what each part adds, from its share of the maximum
    // (≥ 90% "mucho", ≥ 50% "algo", below "poco"). Versión folds into "lo que pediste".
    plain: [
      { adds: "mucho", what: "El precio", why: "Unos USD 3.600 menos de lo que suelen pedir por autos parecidos." },
      { adds: "mucho", what: "Tiene lo que pediste", why: "Modelo, años, kilometraje y zona." },
      { adds: "algo", what: "El kilometraje", why: "Parecido al de otros Focus de esos años." },
      { adds: "algo", what: "Qué tan nuevo es el aviso", why: "Lo detectamos hace 16 horas." },
      { adds: "algo", what: "Los datos del aviso", why: "Informa 7 de los 10 datos que miramos." },
    ],
    comparables: [8990, 9523, 9842, 10120, 10450, 10630, 10645, 10645, 11401, 11768],
    flags: [
      { warn: true, text: "Publicación 34% más barata que publicaciones comparables: conviene verificar por qué." },
      { text: "No especifica cantidad de dueños." },
      { text: "No informa services: conviene ver el historial." },
      { text: "No informa la distribución: conviene preguntar cuándo se cambió." },
      { text: "Descripción muy corta: conviene pedir más información." },
    ],
    questions:
      "Hola, ¿cómo estás? ¿Lo seguís teniendo? ¿Sos titular? ¿Cuántos dueños tuvo? ¿Cuándo se hizo la distribución por última vez? ¿Tiene VTV vigente? ¿Tuvo choques o reparaciones importantes? ¿Tenés historial de services? ¿Qué versión es?",
  },

  LEVEL: {
    high: { label: "Alta oportunidad", short: "Alta" },
    good: { label: "Buena coincidencia", short: "Buena" },
    match: { label: "Coincidencia", short: "Coincidencia" },
    low: { label: "Baja prioridad", short: "Baja" },
  },
  STATUS: {
    new: "Nuevo",
    seen: "Visto",
    interested: "Me interesa",
    contacted: "Contactado",
    visit_scheduled: "Visita agendada",
    discarded: "Descartado",
    purchased: "Comprado",
  },
  SOURCES: ["MercadoLibre", "Facebook Marketplace", "Kavak", "V6", "Autocosmos"],
};
