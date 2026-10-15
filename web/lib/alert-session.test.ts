import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

type Row = Record<string, unknown>;
const m = vi.hoisted(() => ({
  tables: {} as Record<string, Row[]>,
  claims: null as Row | null,
  rpc: vi.fn(), getUserById: vi.fn(), generateLink: vi.fn(), verifyOtp: vi.fn(), signOut: vi.fn(),
  claimThrottle: vi.fn(), track: vi.fn(),
}));
vi.mock("server-only", () => ({}));
vi.mock("@/lib/supabase/admin", () => ({
  createAdminClient: () => ({
    rpc: m.rpc,
    auth: { admin: { getUserById: m.getUserById, generateLink: m.generateLink } },
    from: (table: string) => {
      const filters: [string, unknown][] = [];
      const query = {
        select: () => query,
        eq: (column: string, value: unknown) => (filters.push([column, value]), query),
        maybeSingle: async () => ({
          data: (m.tables[table] ?? []).find((row) => filters.every(([column, value]) => row[column] === value)) ?? null,
          error: null,
        }),
      };
      return query;
    },
  }),
}));
vi.mock("@/lib/supabase/server", () => ({
  createClient: async () => ({
    auth: { getClaims: async () => ({ data: m.claims ? { claims: m.claims } : null }), verifyOtp: m.verifyOtp, signOut: m.signOut },
  }),
}));
vi.mock("@/lib/config", () => ({ webConfig: async () => ({ emailOnlySignup: { alertSessionsPerUserHour: 10 } }) }));
vi.mock("@/lib/email-only", () => ({ HOUR: 3600, claimThrottle: m.claimThrottle }));
vi.mock("@/lib/events", () => ({ track: m.track }));
vi.mock("@/lib/origin", () => ({ requestOrigin: () => "https://www.eseauto.com.ar" }));

import * as alerts from "@/app/r/[notificationId]/route";
import * as plans from "@/app/m/[emailId]/route";
import {
  alertLinkSecrets, alertLinkSignature, continuePage, isAppPath, recentlySent, signedAction, validAlertLinkSignature,
} from "@/lib/alert-session";

const SITE = "https://www.eseauto.com.ar";
const SECRET = "alert-link-test-secret-0123456789abcdef";
const OWNER = "8d3a7c4e-1f2b-4c5d-9e6f-0a1b2c3d4e5f";
const SOURCE = "https://auto.mercadolibre.com.ar/MLA-1_JM";
const DAY = 86_400_000;
const ago = (days: number) => new Date(Date.now() - days * DAY).toISOString();
const sig = (scope: "r" | "m", id: number, user = OWNER, secret = SECRET) => alertLinkSignature(secret, scope, id, user);
const BROWSER = "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X)";

type Method = "GET" | "HEAD" | "POST";
function request(path: string, method: Method = "GET", headers: Record<string, string> = {}) {
  const extra: Record<string, string> = method === "POST" ? { origin: SITE } : {};
  return new NextRequest(`${SITE}${path}`, { method, headers: { "user-agent": BROWSER, ...extra, ...headers } });
}
function alert(query: string, method: Method = "GET", headers?: Record<string, string>) {
  return alerts[method](request(`/r/42?${query}`, method, headers), { params: Promise.resolve({ notificationId: "42" }) });
}
function plan(query: string, method: Method = "GET", headers?: Record<string, string>) {
  return plans[method](request(`/m/7${query ? `?${query}` : ""}`, method, headers), { params: Promise.resolve({ emailId: "7" }) });
}
const signedDetail = () => `to=detail&s=${sig("r", 42)}`;

beforeEach(() => {
  vi.resetAllMocks();
  vi.stubEnv("ALERT_LINK_SECRET", SECRET);
  vi.stubEnv("ALERT_LINK_SECRET_PREVIOUS", "");
  m.claims = null;
  m.tables = {
    notifications: [{ id: 42, user_id: OWNER, channel: "email", status: "sent", sent_at: ago(1), listing_id: 501, payload: { items: [{ listing_id: 502 }] } }],
    lifecycle_emails: [{ id: 7, user_id: OWNER, status: "sent", sent_at: ago(1), target: "/app/pro?plan=pass_30" }],
    listings: [{ id: 501, url: SOURCE }, { id: 502, url: "https://www.kavak.com/ar/usados/502" }],
    profiles: [{ id: OWNER, email_only: true }],
  };
  m.rpc.mockImplementation(async (name: string, args: Row) => {
    if (name === "track_notification_click") return { data: [{ listing_id: args.p_listing_id ?? 501, url: SOURCE }], error: null };
    if (name === "track_lifecycle_click") return { data: "/app/pro?plan=pass_30", error: null };
    return { data: null, error: null };
  });
  m.claimThrottle.mockResolvedValue(true);
  m.getUserById.mockResolvedValue({ data: { user: { id: OWNER, email: "persona@example.com" } }, error: null });
  m.generateLink.mockResolvedValue({ data: { properties: { hashed_token: "hash" }, user: { id: OWNER } }, error: null });
  m.verifyOtp.mockImplementation(async () => {
    m.claims = { sub: OWNER, session_id: "minted" };
    return { data: { user: { id: OWNER } }, error: null };
  });
  m.signOut.mockImplementation(async () => {
    m.claims = null;
    return { error: null };
  });
});
afterEach(() => vi.unstubAllEnvs());

describe("the signature", () => {
  it("is the worker's (worker/tests/test_notifications_links.py)", () => {
    expect(sig("r", 42)).toBe("QmbEMrNzw4hGRVgh7FPfPw");
    expect(sig("m", 7)).toBe("txvVh27uBxAp7KCEPptC0w");
  });

  it("binds the kind of email, its id and its owner", () => {
    const link = { scope: "r" as const, id: 42, signature: sig("r", 42) };
    expect(validAlertLinkSignature(link, OWNER, [SECRET])).toBe(true);
    expect(validAlertLinkSignature({ ...link, id: 43 }, OWNER, [SECRET])).toBe(false);
    expect(validAlertLinkSignature({ ...link, scope: "m" }, OWNER, [SECRET])).toBe(false);
    expect(validAlertLinkSignature(link, "another-user", [SECRET])).toBe(false);
    expect(validAlertLinkSignature(link, OWNER, [`${SECRET}-new`])).toBe(false);
    for (const signature of [null, "", `${sig("r", 42)}=`, sig("r", 42).slice(0, 21), "../../../../etc/passwd!!"]) {
      expect(validAlertLinkSignature({ ...link, signature }, OWNER, [SECRET])).toBe(false);
    }
  });

  it("still accepts the previous secret while rotating, and ignores short ones", () => {
    const fresh = `${SECRET}-rotated`;
    expect(alertLinkSecrets({ ALERT_LINK_SECRET: fresh, ALERT_LINK_SECRET_PREVIOUS: SECRET })).toEqual([fresh, SECRET]);
    expect(validAlertLinkSignature({ scope: "r", id: 42, signature: sig("r", 42) }, OWNER, [fresh, SECRET])).toBe(true);
    expect(alertLinkSecrets({ ALERT_LINK_SECRET: "x".repeat(31) })).toEqual([]);
    expect(alertLinkSecrets({})).toEqual([]);
  });

  it("lasts 7 days from the database's sent_at and only leads into the app", () => {
    expect(recentlySent(ago(6.9))).toBe(true);
    expect(recentlySent(ago(7))).toBe(false);
    expect(recentlySent(null)).toBe(false);
    expect(recentlySent("nope")).toBe(false);
    for (const path of ["/app", "/app/pro?plan=pass_30", "/app/searches/3/edit"]) expect(isAppPath(path)).toBe(true);
    for (const path of ["/apple", "/planes", "//app", "/r/42"]) expect(isAppPath(path)).toBe(false);
  });
});

describe("/r/<id>?to=detail with a signed link, signed out, of an email-only account", () => {
  it("counts the click and answers a page that posts itself back, without a session yet", async () => {
    const response = await alert(signedDetail());
    expect(response.status).toBe(200);
    expect(m.rpc).toHaveBeenCalledWith("track_notification_click", { p_notification_id: 42, p_to: "detail", p_listing_id: undefined });
    const html = await response.text();
    expect(html).toContain(`<form method="post" action="/r/42?to=detail&amp;s=${sig("r", 42)}">`);
    expect(html).toContain("document.forms[0].submit()");
    expect(response.headers.get("cache-control")).toBe("private, no-store");
    expect(response.headers.get("referrer-policy")).toBe("same-origin");
    expect(m.generateLink).not.toHaveBeenCalled();
    expect(m.verifyOtp).not.toHaveBeenCalled();
  });

  it("keeps the digest item in the page's form", async () => {
    const html = await (await alert(`to=detail&l=502&s=${sig("r", 42)}`)).text();
    expect(html).toContain(`action="/r/42?to=detail&amp;l=502&amp;s=${sig("r", 42)}"`);
  });

  it("signs the owner in on the POST, without an inbox proof, and opens the detail", async () => {
    const response = await alert(signedDetail(), "POST");
    expect(response.status).toBe(303);
    expect(response.headers.get("location")).toBe(`${SITE}/app/listings/501?n=42`);
    expect(m.claimThrottle).toHaveBeenCalledWith("alert_link_session", OWNER, 10, 3600);
    expect(m.generateLink).toHaveBeenCalledWith({ type: "magiclink", email: "persona@example.com" });
    expect(m.verifyOtp).toHaveBeenCalledWith({ type: "magiclink", token_hash: "hash" });
    expect(m.track).toHaveBeenCalledWith(expect.anything(), OWNER, "alert_link_signin", { link: "r", id: 42 });
    // No proof, no other session closed, no footholds cleared, and the click was counted on the GET.
    expect(m.rpc).not.toHaveBeenCalled();
    expect(m.signOut).not.toHaveBeenCalled();
    expect(m.tables.account_proofs).toBeUndefined();
  });

  it("refuses a POST from another site", async () => {
    const response = await alert(signedDetail(), "POST", { origin: "https://evil.example" });
    expect(response.status).toBe(403);
    expect(m.generateLink).not.toHaveBeenCalled();
    expect((await alert(signedDetail(), "POST", { origin: "null" })).status).toBe(403);
  });

  it("falls back to the source listing past the per-account brake", async () => {
    m.claimThrottle.mockResolvedValue(false);
    const response = await alert(signedDetail(), "POST");
    expect(response.headers.get("location")).toBe(SOURCE);
    expect(m.generateLink).not.toHaveBeenCalled();
  });

  it("falls back to the source listing when Auth refuses the link (429 right after another one)", async () => {
    m.generateLink.mockResolvedValue({ data: { properties: null, user: null }, error: { status: 429, message: "over_email_send_rate_limit" } });
    expect((await alert(signedDetail(), "POST")).headers.get("location")).toBe(SOURCE);
    expect(m.verifyOtp).not.toHaveBeenCalled();
  });

  it("never verifies a link of another user", async () => {
    m.generateLink.mockResolvedValue({ data: { properties: { hashed_token: "hash" }, user: { id: "someone-else" } }, error: null });
    expect((await alert(signedDetail(), "POST")).headers.get("location")).toBe(SOURCE);
    expect(m.verifyOtp).not.toHaveBeenCalled();
  });

  it("never keeps a session for another user", async () => {
    m.verifyOtp.mockImplementation(async () => {
      m.claims = { sub: "someone-else" };
      return { data: { user: { id: "someone-else" } }, error: null };
    });
    expect((await alert(signedDetail(), "POST")).headers.get("location")).toBe(SOURCE);
    expect(m.signOut).toHaveBeenCalledWith({ scope: "local" });
    expect(m.track).not.toHaveBeenCalled();
  });

  it("drops the session if the account was completed in between: a full account keeps the login", async () => {
    m.verifyOtp.mockImplementation(async () => {
      m.claims = { sub: OWNER };
      m.tables.profiles = [{ id: OWNER, email_only: false }];
      return { data: { user: { id: OWNER } }, error: null };
    });
    expect((await alert(signedDetail(), "POST")).headers.get("location")).toBe(`${SITE}/app/listings/501?n=42`);
    expect(m.signOut).toHaveBeenCalledWith({ scope: "local" });
    expect(m.claims).toBeNull();
  });
});

describe("/r/<id> keeps its behavior", () => {
  const listingFallback = async (query: string) => {
    const response = await alert(query);
    expect(response.status).toBe(302);
    expect(response.headers.get("location")).toBe(SOURCE);
    expect(m.generateLink).not.toHaveBeenCalled();
  };

  it("without a valid signature: the signed-out email-only owner goes to the source", async () => {
    await listingFallback("to=detail");
    await listingFallback(`to=detail&s=${sig("r", 43)}`);
    await listingFallback(`to=detail&s=${sig("m", 42)}`);
    await listingFallback(`to=detail&s=${sig("r", 42, "another-user")}`);
  });

  it("without the secret on the web", async () => {
    vi.stubEnv("ALERT_LINK_SECRET", "");
    await listingFallback(signedDetail());
    vi.stubEnv("ALERT_LINK_SECRET", "too-short");
    await listingFallback(signedDetail());
  });

  it("for an email sent 7 days ago or more, or one that didn't go out by email", async () => {
    m.tables.notifications[0].sent_at = ago(8);
    await listingFallback(signedDetail());
    m.tables.notifications[0] = { ...m.tables.notifications[0], sent_at: ago(1), channel: "telegram" };
    await listingFallback(signedDetail());
    m.tables.notifications[0] = { ...m.tables.notifications[0], channel: "email", status: "failed" };
    await listingFallback(signedDetail());
  });

  it("for link previews, HEAD requests and links to the source", async () => {
    for (const response of [await alert(signedDetail(), "GET", { "user-agent": "WhatsApp/2.23" }), await alert(signedDetail(), "HEAD")]) {
      expect(response.headers.get("location")).toBe(SOURCE);
    }
    expect((await alert(`to=listing&s=${sig("r", 42)}`)).headers.get("location")).toBe(SOURCE);
    expect(m.generateLink).not.toHaveBeenCalled();
  });

  it("with a session already open on this browser, whoever's it is", async () => {
    for (const sub of [OWNER, "someone-else"]) {
      m.claims = { sub };
      expect((await alert(signedDetail())).headers.get("location")).toBe(`${SITE}/app/listings/501?n=42`);
      expect((await alert(signedDetail(), "POST")).headers.get("location")).toBe(`${SITE}/app/listings/501?n=42`);
    }
    expect(m.generateLink).not.toHaveBeenCalled();
  });

  it("for a full account: the detail, through the login", async () => {
    m.tables.profiles = [{ id: OWNER, email_only: false }];
    expect((await alert(signedDetail())).headers.get("location")).toBe(`${SITE}/app/listings/501?n=42`);
    expect((await alert(signedDetail(), "POST")).headers.get("location")).toBe(`${SITE}/app/listings/501?n=42`);
    expect(m.generateLink).not.toHaveBeenCalled();
  });
});

describe("/m/<id> (plan emails)", () => {
  const signed = () => `s=${sig("m", 7)}`;

  it("answers the page for a signed-out email-only owner, then signs in and goes on", async () => {
    const page = await plan(signed());
    expect(page.status).toBe(200);
    expect(await page.text()).toContain(`action="/m/7?s=${sig("m", 7)}"`);
    expect(m.rpc).toHaveBeenCalledWith("track_lifecycle_click", { p_id: 7 });
    const response = await plan(signed(), "POST");
    expect(response.status).toBe(303);
    expect(response.headers.get("location")).toBe(`${SITE}/app/pro?plan=pass_30`);
    expect(m.verifyOtp).toHaveBeenCalledWith({ type: "magiclink", token_hash: "hash" });
    expect(m.track).toHaveBeenCalledWith(expect.anything(), OWNER, "alert_link_signin", { link: "m", id: 7 });
  });

  it("goes on without a session when it can't sign in (the login takes over)", async () => {
    m.claimThrottle.mockResolvedValue(false);
    expect((await plan(signed(), "POST")).headers.get("location")).toBe(`${SITE}/app/pro?plan=pass_30`);
    expect(m.generateLink).not.toHaveBeenCalled();
    expect((await plan(signed(), "POST", { origin: "https://evil.example" })).status).toBe(403);
  });

  it("redirects as before when unsigned, old, unsent, or for a full account", async () => {
    const redirects = async (query: string) => {
      const response = await plan(query);
      expect(response.status).toBe(302);
      expect(response.headers.get("location")).toBe(`${SITE}/app/pro?plan=pass_30`);
    };
    await redirects("");
    await redirects(`s=${sig("r", 7)}`);
    m.tables.lifecycle_emails[0].sent_at = ago(8);
    await redirects(signed());
    m.tables.lifecycle_emails[0] = { ...m.tables.lifecycle_emails[0], sent_at: ago(1), status: "pending" };
    await redirects(signed());
    m.tables.lifecycle_emails[0].status = "sent";
    m.tables.profiles = [{ id: OWNER, email_only: false }];
    await redirects(signed());
    expect(m.generateLink).not.toHaveBeenCalled();
  });
});

describe("the page of a signed link", () => {
  it("escapes its action and builds it from parsed values", async () => {
    expect(signedAction("/r/42", { to: "detail", l: null, s: "abc" })).toBe("/r/42?to=detail&s=abc");
    const html = await continuePage(`/r/42?to=detail&s="><script>alert(1)</script>`).text();
    expect(html).not.toContain("<script>alert(1)");
    expect(html).toContain("&quot;&gt;&lt;script&gt;");
  });
});
