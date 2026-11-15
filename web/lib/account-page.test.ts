import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const m = vi.hoisted(() => ({ liveAccount: vi.fn(), hasFreshProof: vi.fn(), automaticPayments: true }));
vi.mock("server-only", () => ({}));
vi.mock("@/lib/auth", () => ({ liveAccount: m.liveAccount }));
vi.mock("@/lib/email-only", () => ({ hasFreshProof: m.hasFreshProof }));
vi.mock("@/lib/config", async () => {
  const { DEFAULT_PRO_OFFER } = await import("@/lib/pro");
  return { webConfig: async () => ({ automaticPayments: m.automaticPayments, proOffer: DEFAULT_PRO_OFFER }) };
});
vi.mock("@/app/app/cuenta/actions", () => ({
  completeAccount: vi.fn(), confirmAccountCode: vi.fn(), sendAccountLink: vi.fn(), continueToPayment: vi.fn(),
}));
vi.mock("@/lib/meta-pixel", () => ({ pixel: vi.fn() }));
vi.mock("@/lib/google-analytics", () => ({ analyticsEvent: vi.fn() }));
// Static rendering runs no effects: the page's autostart decision is shown next to the real component.
vi.mock("@/components/app/continue-to-payment", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/components/app/continue-to-payment")>();
  const { createElement: h, Fragment } = await import("react");
  return { ContinueToPayment: (props: Parameters<typeof actual.ContinueToPayment>[0]) =>
    h(Fragment, null, h("i", { "data-autostart": String(props.autostart) }), h(actual.ContinueToPayment, props)) };
});
vi.mock("next/navigation", () => ({
  redirect: (path: string) => { throw new Error(`redirect:${path}`); },
  useRouter: () => ({ push: vi.fn(), replace: vi.fn(), refresh: vi.fn() }),
}));

import AccountPage from "@/app/app/cuenta/page";
import { AccountSteps } from "@/components/app/account-steps";
import { ContinueToPayment } from "@/components/app/continue-to-payment";
import { planPrice } from "@/lib/pro";

const lite = { id: "user", email: "persona@example.com", sessionId: "session", emailOnly: true };
const page = async (params: Record<string, string>) =>
  renderToStaticMarkup(await AccountPage({ params: Promise.resolve({}), searchParams: Promise.resolve(params) } as never));

beforeEach(() => {
  vi.resetAllMocks();
  m.liveAccount.mockResolvedValue(lite);
  m.hasFreshProof.mockResolvedValue(false);
  m.automaticPayments = true;
});

describe("/app/cuenta on the way to paying", () => {
  it("asks only for the code, with the price on the button and no password", async () => {
    const html = await page({ next: "/app/pro?plan=pass_7" });
    expect(html).toContain("Escribí el código que te mandamos");
    expect(html).toContain("persona@example.com");
    expect(html).toContain(`Confirmar y pagar ${planPrice(5000)}`);
    expect(html).toContain("No hace falta una contraseña para pagar");
    expect(html).toContain("Términos y condiciones");
    expect(html).toContain('name="code"');
    expect(html).not.toContain('type="password"');
  });

  it("goes on to Mercado Pago once this session proved the inbox", async () => {
    m.hasFreshProof.mockResolvedValue(true);
    const html = await page({ next: "/app/pro?plan=pass_30", pagar: "1" });
    expect(html).toContain("Seguí en Mercado Pago");
    expect(html).toContain(`Continuar en Mercado Pago · ${planPrice(15000)}`);
    expect(html).not.toContain('type="password"');
  });

  it("keeps a full account that arrives with a plan, and sends one without a plan on", async () => {
    m.liveAccount.mockResolvedValue({ ...lite, emailOnly: false });
    expect(await page({ next: "/app/pro?plan=pass_7" })).toContain(`Continuar en Mercado Pago · ${planPrice(5000)}`);
    await expect(page({ next: "/app/settings" })).rejects.toThrow("redirect:/app/settings");
    await expect(page({ next: "/app/pro" })).rejects.toThrow("redirect:/app/pro");
    m.automaticPayments = false;
    await expect(page({ next: "/app/pro?plan=pass_7" })).rejects.toThrow("redirect:/app/pro?plan=pass_7");
  });

  it("starts the checkout by itself only for a session with a fresh proof", async () => {
    m.liveAccount.mockResolvedValue({ ...lite, emailOnly: false });
    const stale = await page({ next: "/app/pro?plan=pass_7", pagar: "1" });
    expect(stale).toContain('data-autostart="false"');
    expect(stale).toContain(`Continuar en Mercado Pago · ${planPrice(5000)}`);
    m.hasFreshProof.mockResolvedValue(true);
    expect(await page({ next: "/app/pro?plan=pass_7", pagar: "1" })).toContain('data-autostart="true"');
    m.liveAccount.mockResolvedValue(lite);
    expect(await page({ next: "/app/pro?plan=pass_7", pagar: "1" })).toContain('data-autostart="true"');
    expect(await page({ next: "/app/pro?plan=pass_7" })).toContain('data-autostart="false"');
  });

  it("asks for the password as before when payments are off", async () => {
    m.automaticPayments = false;
    expect(await page({ next: "/app/pro?plan=pass_7" })).toContain("Confirmá tu email para contratar");
    m.hasFreshProof.mockResolvedValue(true);
    expect(await page({ next: "/app/pro?plan=pass_7" })).toContain('type="password"');
  });

  it("never sends anyone off-site", async () => {
    m.liveAccount.mockResolvedValue({ ...lite, emailOnly: false });
    await expect(page({ next: "https://evil.example/app/pro?plan=pass_7" })).rejects.toThrow("redirect:/app");
  });
});

describe("/app/cuenta without paying", () => {
  it("chooses a password after the code, as today", async () => {
    expect(await page({ next: "/app/settings" })).toContain("Confirmá tu email");
    m.hasFreshProof.mockResolvedValue(true);
    const html = await page({ next: "/app/settings" });
    expect(html).toContain("Elegí una contraseña");
    expect(html).toContain('type="password"');
    expect(html).toContain("Ahora no, seguir");
  });
});

describe("the steps", () => {
  it("without checkout waits for «Mandarme el código»", () => {
    const html = renderToStaticMarkup(createElement(AccountSteps, { email: "a@b.test", next: "/app/settings", proven: false, paying: false }));
    expect(html).toContain("Mandarme el código");
    expect(html).not.toContain('name="code"');
  });

  it("with checkout but no amount (the founder link) confirms and goes on", () => {
    const html = renderToStaticMarkup(createElement(AccountSteps, { email: "a@b.test", next: "/app/pro?fundador=abcdef12", proven: false, paying: true, checkout: { amount: null } }));
    expect(html).toContain("Confirmar y seguir");
    expect(html).toContain("Mandarme otro código");
    expect(html).not.toContain("Términos y condiciones");
  });

  it("the payment button without an offer only continues", () => {
    const html = renderToStaticMarkup(createElement(ContinueToPayment, { next: "/app/pro", offer: null, autostart: false }));
    expect(html).toContain("Continuar");
    expect(html).not.toContain("Mercado Pago ·");
  });
});
