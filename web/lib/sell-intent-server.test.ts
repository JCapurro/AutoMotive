import { beforeEach, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ email: null as Record<string, unknown> | null, profile: { email: "juan@gmail.com" } as Record<string, unknown> | null }));
vi.mock("server-only", () => ({}));
vi.mock("@/lib/auth", () => ({ currentUser: vi.fn() }));
vi.mock("@/lib/supabase/server", () => ({ createClient: vi.fn() }));
vi.mock("@/lib/supabase/admin", () => ({
  createAdminClient: () => ({
    from: (table: string) => ({
      select: () => ({
        eq: () => ({ maybeSingle: async () => ({ data: table === "lifecycle_emails" ? mocks.email : mocks.profile }) }),
      }),
    }),
  }),
}));

import { alertLinkSignature } from "@/lib/alert-session";
import { emailLinkViewer } from "@/lib/sell-intent-server";

const SECRET = "x".repeat(32);
const USER = "11111111-1111-4111-8111-111111111111";

beforeEach(() => {
  vi.unstubAllEnvs();
  mocks.email = { user_id: USER, kind: "search_activated", status: "sent" };
});

it("a signed link of a sent welcome email is its owner, with the whole email", async () => {
  vi.stubEnv("ALERT_LINK_SECRET", SECRET);
  const signature = alertLinkSignature(SECRET, "m", 41, USER);
  expect(await emailLinkViewer(41, signature)).toEqual({ userId: USER, email: "juan@gmail.com", link: { id: 41, signature } });
});

it("with a secret, a bad or missing signature is nobody", async () => {
  vi.stubEnv("ALERT_LINK_SECRET", SECRET);
  expect(await emailLinkViewer(41, null)).toBeNull();
  expect(await emailLinkViewer(41, alertLinkSignature(SECRET, "m", 42, USER))).toBeNull();
});

it("only a sent welcome email", async () => {
  mocks.email = { user_id: USER, kind: "search_feedback", status: "sent" };
  expect(await emailLinkViewer(41, null)).toBeNull();
  mocks.email = { user_id: USER, kind: "search_activated", status: "pending" };
  expect(await emailLinkViewer(41, null)).toBeNull();
});

it("without a secret (unsigned links) the email shows masked", async () => {
  vi.stubEnv("ALERT_LINK_SECRET", "");
  vi.stubEnv("ALERT_LINK_SECRET_PREVIOUS", "");
  expect((await emailLinkViewer(41, null))?.email).toBe("j***@gmail.com");
});
