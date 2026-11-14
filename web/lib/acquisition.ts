/**
 * Where a user came from (admin «Usuarios»): the first visit is kept in a
 * first-party cookie by the proxy, and copied into the signup_completed event
 * when the account is created (lib/signup.ts). Only the first touch counts:
 * the cookie is never rewritten while it lives.
 *
 * Pure helpers, shared by the proxy (edge), the signup and the admin pages.
 */

export const ORIGIN_COOKIE = "first_touch";
export const ORIGIN_MAX_AGE = 60 * 60 * 24 * 90;

export type Origin = {
  /** utm_source, utm_medium, utm_campaign, utm_content */
  source?: string;
  medium?: string;
  campaign?: string;
  content?: string;
  /** Host of the page that linked to us (the browser sends only the origin). */
  referrer?: string;
  /** Path of the first page, without the query. */
  landing?: string;
  /** Ad click id present on the first URL. */
  click?: "meta" | "x" | "google";
  /** ISO time of the first visit. */
  at?: string;
};

export type Channel =
  | "meta_ads"
  | "x_ads"
  | "google_ads"
  | "founder"
  | "email"
  | "search"
  | "ai"
  | "social"
  | "campaign"
  | "referral"
  | "direct"
  | "unknown";

export const CHANNEL_LABEL: Record<Channel, string> = {
  meta_ads: "Anuncio Meta",
  x_ads: "Anuncio X",
  google_ads: "Anuncio Google",
  founder: "Link de fundador",
  email: "Email",
  search: "Buscador",
  ai: "Asistente de IA",
  social: "Redes (orgánico)",
  campaign: "Otra campaña",
  referral: "Otro sitio",
  direct: "Directo",
  unknown: "Sin dato",
};

const cut = (value: string | null | undefined, max = 80) => {
  const v = value?.trim();
  return v ? v.slice(0, max) : undefined;
};

/** Pages a first visit is not taken from: secrets in the URL, alert links, the backoffice, APIs. */
export function skipsOrigin(pathname: string): boolean {
  return (
    pathname.startsWith("/auth/") ||
    pathname === "/baja" ||
    pathname.startsWith("/r/") ||
    pathname.startsWith("/m/") ||
    pathname.startsWith("/api/") ||
    pathname === "/admin" ||
    pathname.startsWith("/admin/")
  );
}

/** The first touch of a visit: its URL and the Referer header (ignored when it is our own host). */
export function originFromRequest(url: URL, referer: string | null, now = new Date()): Origin {
  const q = url.searchParams;
  let referrer: string | undefined;
  if (referer) {
    try {
      const host = new URL(referer).hostname.replace(/^www\./, "");
      if (host && host !== url.hostname.replace(/^www\./, "")) referrer = cut(host);
    } catch {
      /* a malformed Referer is just no referrer */
    }
  }
  const click = q.get("fbclid") ? "meta" : q.get("twclid") ? "x" : q.get("gclid") || q.get("gbraid") || q.get("wbraid") ? "google" : undefined;
  const origin: Origin = {
    source: cut(q.get("utm_source"))?.toLowerCase(),
    medium: cut(q.get("utm_medium"))?.toLowerCase(),
    campaign: cut(q.get("utm_campaign")),
    content: cut(q.get("utm_content")),
    referrer,
    landing: cut(url.pathname, 120),
    click,
    at: now.toISOString(),
  };
  return Object.fromEntries(Object.entries(origin).filter(([, v]) => v !== undefined)) as Origin;
}

/** The cookie value: plain JSON (Next encodes cookie values itself). */
export function encodeOrigin(origin: Origin): string {
  return JSON.stringify(origin);
}

const FIELDS = ["source", "medium", "campaign", "content", "referrer", "landing", "click", "at"] as const;

/** Reads the cookie (or an event's props.origin) back, keeping only known string fields. */
export function parseOrigin(raw: unknown): Origin | null {
  let value = raw;
  if (typeof value === "string") {
    const raw = value;
    try {
      value = JSON.parse(raw);
    } catch {
      try {
        value = JSON.parse(decodeURIComponent(raw));
      } catch {
        return null;
      }
    }
  }
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  const out: Record<string, string> = {};
  for (const key of FIELDS) {
    const v = (value as Record<string, unknown>)[key];
    if (typeof v === "string" && v) out[key] = v.slice(0, 120);
  }
  if (out.click && !["meta", "x", "google"].includes(out.click)) delete out.click;
  return out as Origin;
}

const META = /^(facebook|fb|instagram|ig|meta|messenger)$|facebook|instagram/;
const X = /^(x|twitter)$|twitter/;
const PAID = /^(cpc|ppc|paid|paid_social|paidsocial|ads?|display|cpm)$/;
const SEARCH = /(^|\.)(google|bing|duckduckgo|yahoo|ecosia|search\.brave|yandex)\./;
const AI = /(^|\.)(chatgpt\.com|openai\.com|perplexity\.ai|gemini\.google\.com|claude\.ai|copilot\.microsoft\.com|you\.com)$/;
const SOCIAL = /(^|\.)(facebook\.com|instagram\.com|t\.co|x\.com|twitter\.com|whatsapp\.com|wa\.me|linkedin\.com|lnkd\.in|reddit\.com|youtube\.com|tiktok\.com|threads\.net|telegram\.org|t\.me)$|^(l|lm|m)\.facebook\.com$|^l\.instagram\.com$/;

/** The channel a first touch belongs to: paid clicks first, then the founder link, campaigns and the referrer. */
export function channelOf(origin: Origin | null): Channel {
  if (!origin) return "unknown";
  const source = origin.source ?? "";
  const medium = origin.medium ?? "";
  const paid = PAID.test(medium);
  if (origin.click === "meta" || (paid && META.test(source))) return "meta_ads";
  if (origin.click === "x" || (paid && X.test(source))) return "x_ads";
  if (origin.click === "google" || (paid && source === "google")) return "google_ads";
  if (origin.landing?.startsWith("/fundador")) return "founder";
  if (medium === "email" || source === "email" || source === "newsletter") return "email";
  const ref = origin.referrer ?? "";
  if (ref && AI.test(ref)) return "ai";
  if (source && (META.test(source) || X.test(source) || /whatsapp|linkedin|reddit|youtube|tiktok|telegram/.test(source))) return "social";
  if (source) return "campaign";
  if (ref && SEARCH.test(ref)) return "search";
  if (ref && SOCIAL.test(ref)) return "social";
  if (ref) return "referral";
  return "direct";
}

/** «Entró por»: the kind of first page. */
export function landingKind(landing: string | undefined): string {
  if (!landing) return "—";
  if (landing === "/") return "Inicio";
  if (landing.startsWith("/guias")) return "Guía";
  if (landing.startsWith("/fundador")) return "Fundador";
  if (landing.startsWith("/planes")) return "Planes";
  if (landing.startsWith("/vender-mi-auto")) return "Vender mi auto";
  if (landing.startsWith("/login")) return "Login";
  if (landing.startsWith("/app")) return "App";
  return landing;
}
