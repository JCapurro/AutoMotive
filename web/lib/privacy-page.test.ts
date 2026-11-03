import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ config: vi.fn() }));
vi.mock("@/lib/config", () => ({ webConfig: mocks.config }));

import PrivacyPage from "@/app/privacidad/page";
import { SELL_INTENT_PRIVACY_LINE } from "@/lib/sell-intent";

beforeEach(() => {
  mocks.config.mockResolvedValue({ sellIntent: { ask: true, agenciesContact: false } });
});

it("no longer lists «Tus notas»: the note was removed (Juan 02/11), the date says so", async () => {
  const html = renderToStaticMarkup(await PrivacyPage());
  expect(html).not.toContain("Tus notas");
  expect(html).not.toContain("Tu nota");
  expect(html).toContain("2 de noviembre de 2026");
  // The follow-up statuses stay, and so does their mention.
  expect(html).toContain("«compré»");
});

it("PAR-05: the agencies line stays hidden until its flag is on", async () => {
  const off = renderToStaticMarkup(await PrivacyPage());
  expect(off).not.toContain("agencias te contacten");
  mocks.config.mockResolvedValue({ sellIntent: { ask: true, agenciesContact: true } });
  const on = renderToStaticMarkup(await PrivacyPage());
  expect(on).toContain(SELL_INTENT_PRIVACY_LINE);
  expect(on).toContain("No compartimos tus datos con ninguna agencia sin que lo marques");
  // The date moves with the line (approved by Juan, 03/11).
  expect(off).toContain("2 de noviembre de 2026");
  expect(on).toContain("3 de noviembre de 2026");
});
