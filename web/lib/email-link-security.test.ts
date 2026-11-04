import { NextRequest } from "next/server";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

type Row = Record<string, unknown>;
const m = vi.hoisted(() => ({
  tables: {} as Record<string, Row[]>, claims: null as Row | null,
  rpc: vi.fn(), generateLink: vi.fn(), verifyOtp: vi.fn(), signOut: vi.fn(), track: vi.fn(), claimThrottle: vi.fn(),
}));
vi.mock("server-only", () => ({}));
vi.mock("@/lib/supabase/admin", () => ({
  createAdminClient: () => ({
    rpc: m.rpc,
    auth: { admin: { generateLink: m.generateLink, getUserById: async () => ({ data: { user: { id: OWNER, email: "owner@example.com" } }, error: null }) } },
    from: (table: string) => {
      const filters: [string, unknown][] = [];
      const query = {
        select: () => query,
        eq: (column: string, value: unknown) => (filters.push([column, value]), query),
        maybeSingle: async () => ({ data: (m.tables[table] ?? []).find((row) => filters.every(([key, value]) => row[key] === value)) ?? null, error: null }),
      };
      return query;
    },
  }),
}));
vi.mock("@/lib/supabase/server", () => ({ createClient: async () => ({
  auth: { getClaims: async () => ({ data: m.claims ? { claims: m.claims } : null }), verifyOtp: m.verifyOtp, signOut: m.signOut },
}) }));
vi.mock("@/lib/config", () => ({ webConfig: async () => ({ emailOnlySignup: { alertSessionsPerUserHour: 10 } }) }));
vi.mock("@/lib/email-only", () => ({ HOUR: 3600, claimThrottle: m.claimThrottle }));
vi.mock("@/lib/events", () => ({ track: m.track }));
vi.mock("@/lib/origin", () => ({ requestOrigin: () => SITE }));

import * as alerts from "@/app/r/[notificationId]/route";
import * as plans from "@/app/m/[emailId]/route";
import { alertLinkSignature } from "@/lib/alert-session";

const SITE = "https://www.eseauto.com.ar";
const SECRET = "alert-link-test-secret-0123456789abcdef";
const OWNER = "8d3a7c4e-1f2b-4c5d-9e6f-0a1b2c3d4e5f";
const SOURCE = "https://auto.mercadolibre.com.ar/MLA-1_JM";
type Method = "GET" | "HEAD" | "POST";
const signature = (scope: "r" | "m", id: number) => alertLinkSignature(SECRET, scope, id, OWNER);
function open(kind: "r" | "m", method: Method, options: { origin?: string; preview?: boolean; item?: number } = {}) {
  const id = kind === "r" ? 42 : 7;
  const params = new URLSearchParams({ s: signature(kind, id) });
  if (kind === "r") params.set("to", "detail");
  if (options.item) params.set("l", String(options.item));
  const headers: Record<string, string> = { "user-agent": options.preview ? "WhatsApp/2.23" : "Mozilla/5.0 (iPhone)" };
  if (method === "POST") headers.origin = options.origin ?? SITE;
  const request = new NextRequest(`${SITE}/${kind}/${id}?${params}`, { method, headers });
  return kind === "r"
    ? alerts[method](request, { params: Promise.resolve({ notificationId: String(id) }) })
    : plans[method](request, { params: Promise.resolve({ emailId: String(id) }) });
}
function expectNoAuthentication() {
  expect(m.generateLink).not.toHaveBeenCalled();
  expect(m.verifyOtp).not.toHaveBeenCalled();
  expect(m.signOut).not.toHaveBeenCalled();
  expect(m.claimThrottle).not.toHaveBeenCalled();
  expect(m.track).not.toHaveBeenCalled();
}

beforeEach(() => {
  vi.resetAllMocks();
  vi.stubEnv("ALERT_LINK_SECRET", SECRET);
  vi.stubEnv("ALERT_LINK_SECRET_PREVIOUS", "");
  m.claims = null;
  const sentAt = new Date(Date.now() - 86_400_000).toISOString();
  m.tables = {
    notifications: [{ id: 42, user_id: OWNER, channel: "email", status: "sent", sent_at: sentAt, listing_id: 501, payload: { items: [{ listing_id: 502 }] } }],
    lifecycle_emails: [{ id: 7, user_id: OWNER, status: "sent", sent_at: sentAt, target: "/app/pro?plan=pass_30" }],
    listings: [{ id: 501, url: SOURCE }, { id: 502, url: "https://www.kavak.com/ar/usados/502" }],
    profiles: [{ id: OWNER, email_only: true }],
  };
  m.rpc.mockImplementation(async (name: string, args: Row) => name === "track_notification_click"
    ? { data: [{ listing_id: args.p_listing_id ?? 501, url: SOURCE }], error: null }
    : { data: "/app/pro?plan=pass_30", error: null });
  // Auth remains functional: a regression really changes identity and is caught.
  m.claimThrottle.mockResolvedValue(true);
  m.generateLink.mockResolvedValue({ data: { properties: { hashed_token: "hash" }, user: { id: OWNER } }, error: null });
  m.verifyOtp.mockImplementation(async () => {
    m.claims = { sub: OWNER, session_id: "minted" };
    return { data: { user: { id: OWNER } }, error: null };
  });
});
afterEach(() => vi.unstubAllEnvs());

describe("alerts and marketing links never authenticate", () => {
  for (const kind of ["r", "m"] as const) {
    it.each(["GET", "HEAD", "POST"] as const)(`/${kind} rejects old signed links as credentials via %s`, async (method) => {
      const response = await open(kind, method);
      expectNoAuthentication();
      expect(m.claims).toBeNull();
      expect(response.status).toBe(method === "POST" ? 303 : 302);
      expect(response.headers.get("location")).toBe(kind === "r" ? SOURCE : `${SITE}/app/pro?plan=pass_30`);
      expect(response.headers.get("set-cookie")).toBeNull();
      expect(response.headers.get("referrer-policy")).toBe("no-referrer");
      expect(response.headers.get("cache-control")).toBe("no-store");
    });
  }

  it("preserves B's identity when opening A's alert, plan or feedback signature", async () => {
    m.claims = { sub: "another-user", session_id: "session-b" };
    const before = { ...m.claims };
    for (const method of ["GET", "HEAD", "POST"] as const) {
      expect((await open("r", method)).headers.get("location")).toBe(`${SITE}/app/listings/501?n=42`);
      expect((await open("m", method)).headers.get("location")).toBe(`${SITE}/app/pro?plan=pass_30`);
      expect(m.claims).toEqual(before);
    }
    expectNoAuthentication();
  });

  it("does not count previews, HEAD or legacy POST redirects", async () => {
    for (const kind of ["r", "m"] as const) {
      await open(kind, "GET", { preview: true });
      await open(kind, "HEAD");
      await open(kind, "POST");
    }
    expect(m.rpc).not.toHaveBeenCalled();
    expectNoAuthentication();
  });

  it("counts real navigation once per GET without an automatic POST page", async () => {
    for (const kind of ["r", "m"] as const) {
      const response = await open(kind, "GET");
      expect(response.status).toBe(302);
      expect(await response.text()).not.toContain("document.forms");
    }
    expect(m.rpc).toHaveBeenCalledTimes(2);
    expectNoAuthentication();
  });

  it("preserves digest destinations and rejects a non-member item", async () => {
    expect((await open("r", "POST", { item: 502 })).headers.get("location")).toBe("https://www.kavak.com/ar/usados/502");
    expect((await open("r", "POST", { item: 503 })).status).toBe(404);
    expectNoAuthentication();
  });

  it("rejects cross-site legacy POSTs without calling Auth", async () => {
    for (const origin of ["https://evil.example", "null", ""]) {
      for (const kind of ["r", "m"] as const) expect((await open(kind, "POST", { origin })).status).toBe(403);
    }
    expectNoAuthentication();
  });
});
