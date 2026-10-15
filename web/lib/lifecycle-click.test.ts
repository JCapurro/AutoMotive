import { NextRequest } from "next/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const db = vi.hoisted(() => ({ rpc: vi.fn(), target: null as string | null }));
vi.mock("@/lib/supabase/admin", () => ({
  createAdminClient: () => ({
    rpc: db.rpc,
    from: () => {
      const query = { select: () => query, eq: () => query, maybeSingle: async () => ({ data: db.target ? { target: db.target } : null }) };
      return query;
    },
  }),
}));
vi.mock("@/lib/origin", () => ({ requestOrigin: () => "https://www.eseauto.com.ar" }));
vi.mock("server-only", () => ({}));

import { GET, HEAD } from "@/app/m/[emailId]/route";
import { lifecycleEmailId, lifecycleTarget } from "./lifecycle-click";

const open = (id: string, method: "GET" | "HEAD" = "GET", agent = "Mozilla/5.0 (iPhone)") => {
  const request = new NextRequest(`https://www.eseauto.com.ar/m/${id}`, { method, headers: { "user-agent": agent } });
  return (method === "GET" ? GET : HEAD)(request, { params: Promise.resolve({ emailId: id }) });
};

beforeEach(() => {
  db.rpc.mockReset();
  db.target = null;
});

describe("/m/<id>: the button of a plan email", () => {
  it("records the click and leads to the email's page", async () => {
    db.rpc.mockResolvedValue({ data: "/app/pro?plan=pass_30", error: null });
    const response = await open("41");
    expect(db.rpc).toHaveBeenCalledWith("track_lifecycle_click", { p_id: 41 });
    expect(response.status).toBe(302);
    expect(response.headers.get("location")).toBe("https://www.eseauto.com.ar/app/pro?plan=pass_30");
    expect(response.headers.get("cache-control")).toBe("no-store");
  });

  it("does not count link previews or HEAD requests", async () => {
    db.target = "/app/searches/7/edit";
    for (const response of [await open("41", "GET", "WhatsApp/2.23"), await open("41", "HEAD")]) {
      expect(response.headers.get("location")).toBe("https://www.eseauto.com.ar/app/searches/7/edit");
    }
    expect(db.rpc).not.toHaveBeenCalled();
  });

  it("answers 404 for unknown emails and never leaves the site", async () => {
    db.rpc.mockResolvedValue({ data: null, error: null });
    expect((await open("41")).status).toBe(404);
    expect((await open("41abc")).status).toBe(404);
    db.rpc.mockResolvedValue({ data: "//evil.example/pro", error: null });
    expect((await open("42")).status).toBe(404);
  });

  it("accepts only ids and in-site paths", () => {
    expect(lifecycleEmailId("41")).toBe(41);
    expect(lifecycleEmailId("41; drop")).toBeNull();
    expect(lifecycleTarget("/app/pro?plan=pass_30")).toBe("/app/pro?plan=pass_30");
    for (const bad of ["https://evil.example", "//evil.example", "/\\evil.example", "app/pro", null, 7]) {
      expect(lifecycleTarget(bad)).toBeNull();
    }
  });
});
