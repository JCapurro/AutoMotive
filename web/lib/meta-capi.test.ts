import { afterEach, beforeEach, expect, it, vi } from "vitest";

vi.mock("server-only", () => ({}));
vi.mock("next/headers", () => ({ cookies: vi.fn(), headers: vi.fn() }));
const state = vi.hoisted(() => ({ claimed: true as boolean, earlier: 0, updates: [] as unknown[] }));
vi.mock("@/lib/supabase/admin", () => ({
  createAdminClient: () => ({
    from: () => {
      let head = false;
      const query = {
        update: (value: unknown) => { state.updates.push(value); return query; },
        select: (_: string, opts?: { head?: boolean }) => { head = Boolean(opts?.head); return query; },
        eq: () => query, is: () => query, lt: () => query,
        maybeSingle: async () => ({ data: state.claimed ? { id: 7 } : null }),
        then: (resolve: (value: unknown) => void) => resolve(head ? { count: state.earlier } : { error: null }),
      };
      return query;
    },
  }),
}));

const checkout = {
  id: "00000000-0000-4000-8000-000000000001", user_id: "owner", offer: "pass_30", amount: 15000, currency: "ARS",
  ad_attribution: { consent: true, fbp: "fb.1.1.2", fbc: "fb.1.1.abc", ip: "190.0.0.1", ua: "UA" },
};
const fetchMock = vi.fn();

beforeEach(async () => {
  vi.resetModules();
  vi.stubEnv("NEXT_PUBLIC_META_PIXEL_ID", "123");
  vi.stubEnv("META_CAPI_TOKEN", "secret-token");
  vi.stubEnv("SITE_URL", "https://eseauto.com.ar");
  vi.stubGlobal("fetch", fetchMock);
  fetchMock.mockResolvedValue({ ok: true });
  Object.assign(state, { claimed: true, earlier: 0, updates: [] });
});
afterEach(() => { vi.unstubAllGlobals(); vi.unstubAllEnvs(); vi.clearAllMocks(); });

const send = async (over: Partial<typeof checkout> = {}) => {
  const { sendPurchase } = await import("./meta-capi");
  await sendPurchase({ paymentId: 7, checkout: { ...checkout, ...over }, paidAt: new Date().toISOString() });
};
const body = () => JSON.parse(fetchMock.mock.calls[0][1].body).data[0];

it("sends the first payment with the browser's event id, hashed user id and no email", async () => {
  await send();
  expect(fetchMock.mock.calls[0][0]).toBe("https://graph.facebook.com/v23.0/123/events");
  expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe("Bearer secret-token");
  expect(body()).toMatchObject({ event_name: "Purchase", event_id: `purchase:${checkout.id}`, action_source: "website",
    user_data: { fbp: "fb.1.1.2", fbc: "fb.1.1.abc", client_ip_address: "190.0.0.1", client_user_agent: "UA" },
    custom_data: { value: 15000, currency: "ARS", content_ids: ["pass_30"] } });
  expect(body().user_data.external_id[0]).toMatch(/^[0-9a-f]{64}$/);
  expect(JSON.stringify(body())).not.toContain("owner");
});

it("gives renewals their own event id", async () => {
  state.earlier = 1;
  await send({ offer: "pro_monthly" });
  expect(body().event_id).toBe(`purchase:${checkout.id}:7`);
});

it("sends nothing without consent, without a token or when already sent", async () => {
  await send({ ad_attribution: { consent: false } as never });
  await send({ ad_attribution: null as never });
  state.claimed = false;
  await send();
  vi.stubEnv("META_CAPI_TOKEN", "");
  state.claimed = true;
  await send();
  expect(fetchMock).not.toHaveBeenCalled();
});

it("releases the claim when Meta fails, so reconciliation retries", async () => {
  fetchMock.mockResolvedValue({ ok: false, status: 500 });
  const error = vi.spyOn(console, "error").mockImplementation(() => {});
  await send();
  expect(state.updates.at(-1)).toEqual({ meta_sent_at: null });
  expect(error.mock.calls[0].join(" ")).not.toContain("secret-token");
});
