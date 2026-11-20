import { expect, it, vi } from "vitest";
import { NextRequest } from "next/server";

const mocks = vi.hoisted(() => ({ getClaims: vi.fn() }));
vi.mock("server-only", () => ({}));
vi.mock("@supabase/ssr", () => ({ createServerClient: () => ({ auth: { getClaims: mocks.getClaims } }) }));

import { proxy } from "@/proxy";

it("agencias: the proxy leaves /agencia alone, so with the program off an anonymous visit is still a 404", async () => {
  // app/agencia/layout.tsx answers 404 while dealer_program.enabled is off and only then asks for a session.
  mocks.getClaims.mockResolvedValue({ data: { claims: null } });
  for (const path of ["/agencia", "/agencia/stock/planilla"]) {
    const response = await proxy(new NextRequest(`https://www.eseauto.com.ar${path}`));
    expect(response.status).not.toBe(307);
  }
  // /app still asks for a session, as before.
  expect((await proxy(new NextRequest("https://www.eseauto.com.ar/app"))).status).toBe(307);
});
