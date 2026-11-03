import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({
  config: vi.fn(),
  resolveViewer: vi.fn(),
  currentAnswer: vi.fn(),
  saveAnswer: vi.fn(),
  saveNotice: vi.fn(),
  revalidatePath: vi.fn(),
}));
vi.mock("@/lib/config", () => ({ webConfig: mocks.config }));
vi.mock("@/lib/sell-intent-server", () => ({
  resolveViewer: mocks.resolveViewer,
  currentAnswer: mocks.currentAnswer,
  saveAnswer: mocks.saveAnswer,
  saveNotice: mocks.saveNotice,
}));
vi.mock("next/cache", () => ({ revalidatePath: mocks.revalidatePath }));
vi.mock("next/navigation", () => ({
  redirect: (to: string) => {
    throw new Error(`REDIRECT ${to}`);
  },
}));

import { answerSellIntent, requestSellNotice } from "@/app/vender-mi-auto/actions";
import SellIntentPage from "@/app/vender-mi-auto/page";
import { SellIntentLine } from "@/components/app/sell-intent-line";
import { FORBIDDEN_TERMS } from "@/lib/copy";
import {
  answerRow,
  canAnswer,
  fichaReturnPath,
  maskEmail,
  noticeRow,
  SELL_INTENT,
  SELL_INTENT_PRIVACY_LINE,
  sellIntentAnswer,
  sellIntentConfig,
  sellIntentEmailId,
  sellIntentMetrics,
  showFichaQuestion,
} from "@/lib/sell-intent";

const ON = { ask: true, agenciesContact: false };
const EMAIL_VIEWER = { userId: "u-1", email: "juan@example.com", link: { id: 41, signature: "sig" } };
const SESSION_VIEWER = { userId: "u-1", email: "juan@example.com", link: null };
const YES = { user_id: "u-1", answer: "yes", source: "email", wants_notice: false, agencies_contact_ok: false };

function form(values: Record<string, string>): FormData {
  const data = new FormData();
  for (const [k, v] of Object.entries(values)) data.set(k, v);
  return data;
}

async function redirectOf(run: Promise<unknown>): Promise<string> {
  try {
    await run;
  } catch (error) {
    const message = error instanceof Error ? error.message : "";
    if (message.startsWith("REDIRECT ")) return message.slice(9);
    throw error;
  }
  throw new Error("no redirect");
}

async function page(query: Record<string, string>): Promise<string> {
  return renderToStaticMarkup(await SellIntentPage({ searchParams: Promise.resolve(query), params: Promise.resolve({}) } as never));
}

beforeEach(() => {
  vi.clearAllMocks();
  mocks.config.mockResolvedValue({ sellIntent: ON });
  mocks.saveNotice.mockResolvedValue(true);
});

describe("config and parsing", () => {
  it("is on only when explicitly true; the agencies box starts off", () => {
    expect(sellIntentConfig(undefined)).toEqual({ ask: false, agenciesContact: false });
    expect(sellIntentConfig({ ask: "true", agencies_contact: 1 })).toEqual({ ask: false, agenciesContact: false });
    expect(sellIntentConfig({ ask: true, agencies_contact: false })).toEqual({ ask: true, agenciesContact: false });
    expect(sellIntentConfig({ ask: true, agencies_contact: true }).agenciesContact).toBe(true);
  });

  it("reads the answers of the email links and the forms", () => {
    expect(sellIntentAnswer("si")).toBe("yes");
    expect(sellIntentAnswer("yes")).toBe("yes");
    expect(sellIntentAnswer("no")).toBe("no");
    expect(sellIntentAnswer("sí")).toBeNull();
    expect(sellIntentAnswer(undefined)).toBeNull();
    expect(sellIntentEmailId("41")).toBe(41);
    expect(sellIntentEmailId("4x")).toBeNull();
  });

  it("masks an email for unsigned links", () => {
    expect(maskEmail("juan@gmail.com")).toBe("j***@gmail.com");
    expect(maskEmail("nada")).toBe("***");
  });

  it("asks in the ficha only an account with an email that hasn't answered, while the question is on", () => {
    const user = { email: "a@b.c" };
    expect(showFichaQuestion(ON, user, false)).toBe(true);
    expect(showFichaQuestion(ON, user, true)).toBe(false);
    expect(showFichaQuestion(ON, { email: null }, false)).toBe(false);
    expect(showFichaQuestion(ON, null, false)).toBe(false);
    expect(showFichaQuestion({ ask: false, agenciesContact: false }, user, false)).toBe(false);
    expect(canAnswer({ email: "" })).toBe(false);
  });

  it("«No» clears the notice; the agencies box counts only with its flag", () => {
    expect(answerRow("no", "ficha")).toEqual({ answer: "no", source: "ficha", wants_notice: false, agencies_contact_ok: false });
    expect(answerRow("yes", "email")).toEqual({ answer: "yes", source: "email" });
    expect(noticeRow(true, ON)).toEqual({ wants_notice: true });
    expect(noticeRow(true, { ask: true, agenciesContact: true })).toEqual({ wants_notice: true, agencies_contact_ok: true });
    expect(noticeRow(false, { ask: true, agenciesContact: true })).toEqual({ wants_notice: true, agencies_contact_ok: false });
  });

  it("goes back only to a listing page", () => {
    expect(fichaReturnPath("/app/listings/12")).toBe("/app/listings/12");
    expect(fichaReturnPath("https://evil.example/app/listings/12")).toBeNull();
    expect(fichaReturnPath("/app/listings/12?x=1")).toBeNull();
  });

  it("parses the admin metrics tolerantly", () => {
    expect(sellIntentMetrics(null)).toBeNull();
    const m = sellIntentMetrics({ answered: 2, yes: 1, pctYes: 50, since: "2026-11-03T00:00:00Z", bySource: { email: { yes: 1, answered: 1, pctYes: 100 } } });
    expect(m?.yes).toBe(1);
    expect(m?.pctYes).toBe(50);
    expect(m?.bySource.email.pctYes).toBe(100);
    expect(m?.bySource.ficha).toEqual({ answered: 0, yes: 0, no: 0, pctYes: null, wantsNotice: 0, agenciesContactOk: 0 });
  });
});

describe("copy", () => {
  it("never promises a price, an amount or that the reference exists", () => {
    const all = [...Object.values(SELL_INTENT), SELL_INTENT_PRIVACY_LINE].join(" ").toLowerCase();
    for (const term of [...FORBIDDEN_TERMS, "cuánto", "te pagamos", "ganá", "garantiz", "ya está lista", "usd"]) {
      expect(all).not.toMatch(new RegExp(`(^|[^\\p{L}])${term}($|[^\\p{L}])`, "u"));
    }
    expect(all).not.toContain("$");
    expect(SELL_INTENT.pitch).toBe(
      "Estamos armando una referencia de precios publicados para el auto que vas a vender. ¿Querés que te avisemos cuando esté?",
    );
    expect(SELL_INTENT.agencies).toBe("También me interesa que agencias me contacten para comprarlo");
  });
});

describe("/vender-mi-auto", () => {
  it("an invalid or missing link says so", async () => {
    mocks.resolveViewer.mockResolvedValue(null);
    expect(await page({ e: "41", r: "si" })).toContain(SELL_INTENT.invalid);
    expect(mocks.saveAnswer).not.toHaveBeenCalled();
  });

  it("the email's link asks to confirm, with its answer marked, and records nothing on opening", async () => {
    mocks.resolveViewer.mockResolvedValue(EMAIL_VIEWER);
    mocks.currentAnswer.mockResolvedValue(null);
    const html = await page({ e: "41", r: "si", s: "sig" });
    expect(html).toContain(SELL_INTENT.question);
    expect(html).toMatch(/<input type="radio"[^>]*checked="" value="yes"\/>/);
    expect(html).toMatch(/<input type="radio" required="" name="r" value="no"\/>/);
    expect(html).toContain('name="e" value="41"');
    expect(html).toContain('name="s" value="sig"');
    expect(mocks.saveAnswer).not.toHaveBeenCalled();
    expect(mocks.resolveViewer).toHaveBeenCalledWith(41, "sig");
  });

  it("after «Sí»: the honest offer with the email, and no agencies box while its flag is off", async () => {
    mocks.resolveViewer.mockResolvedValue(EMAIL_VIEWER);
    mocks.currentAnswer.mockResolvedValue(YES);
    const html = await page({ e: "41", s: "sig" });
    expect(html).toContain(SELL_INTENT.pitch);
    expect(html).toContain("juan@example.com");
    expect(html).toContain(SELL_INTENT.notify);
    expect(html).not.toContain("agencias");
  });

  it("with the flag on, the agencies box is there and unchecked", async () => {
    mocks.config.mockResolvedValue({ sellIntent: { ask: true, agenciesContact: true } });
    mocks.resolveViewer.mockResolvedValue(SESSION_VIEWER);
    mocks.currentAnswer.mockResolvedValue({ ...YES, source: "ficha" });
    const html = await page({});
    expect(html).toContain(SELL_INTENT.agencies);
    expect(html).toMatch(/<input type="checkbox"[^>]*name="agencias"\/>/);
    expect(html).not.toMatch(/name="agencias"[^>]*checked/);
  });

  it("after asking for the notice it says so, without promising anything else", async () => {
    mocks.resolveViewer.mockResolvedValue(SESSION_VIEWER);
    mocks.currentAnswer.mockResolvedValue({ ...YES, wants_notice: true });
    const html = await page({});
    expect(html).toContain(SELL_INTENT.notified);
    expect(html).not.toContain(SELL_INTENT.notify);
  });

  it("after «No»: a short thanks", async () => {
    mocks.resolveViewer.mockResolvedValue(SESSION_VIEWER);
    mocks.currentAnswer.mockResolvedValue({ ...YES, answer: "no" });
    expect(await page({})).toContain(SELL_INTENT.noThanks);
  });
});

describe("actions", () => {
  it("the email's confirm records the answer as «email» and comes back without it", async () => {
    mocks.resolveViewer.mockResolvedValue(EMAIL_VIEWER);
    const to = await redirectOf(answerSellIntent(form({ e: "41", s: "sig", r: "yes" })));
    expect(mocks.saveAnswer).toHaveBeenCalledWith(EMAIL_VIEWER, "yes", "email");
    expect(to).toBe("/vender-mi-auto?e=41&s=sig");
  });

  it("the ficha's «No» goes back to the listing; «Sí» opens the page", async () => {
    mocks.resolveViewer.mockResolvedValue(SESSION_VIEWER);
    expect(await redirectOf(answerSellIntent(form({ r: "no", volver: "/app/listings/7" })))).toBe("/app/listings/7");
    expect(mocks.saveAnswer).toHaveBeenLastCalledWith(SESSION_VIEWER, "no", "ficha");
    expect(mocks.revalidatePath).toHaveBeenCalledWith("/app/listings/7");
    expect(await redirectOf(answerSellIntent(form({ r: "yes", volver: "/app/listings/7" })))).toBe("/vender-mi-auto");
  });

  it("without a valid viewer or answer nothing is saved", async () => {
    mocks.resolveViewer.mockResolvedValue(null);
    await redirectOf(answerSellIntent(form({ e: "41", r: "yes" })));
    mocks.resolveViewer.mockResolvedValue(SESSION_VIEWER);
    await redirectOf(answerSellIntent(form({ r: "maybe" })));
    expect(mocks.saveAnswer).not.toHaveBeenCalled();
  });

  it("the notice passes the agencies box to the config-aware writer", async () => {
    mocks.resolveViewer.mockResolvedValue(EMAIL_VIEWER);
    await redirectOf(requestSellNotice(form({ e: "41", s: "sig", agencias: "on" })));
    expect(mocks.saveNotice).toHaveBeenCalledWith(EMAIL_VIEWER, true, ON);
  });
});

describe("the ficha line", () => {
  it("is one line with both answers and the way back", () => {
    const html = renderToStaticMarkup(createElement(SellIntentLine, { listingId: 7 }));
    expect(html).toContain(SELL_INTENT.question);
    expect(html).toMatch(/<button type="submit" value="yes"[^>]*name="r">Sí<\/button>/);
    expect(html).toMatch(/<button type="submit" value="no"[^>]*name="r">No<\/button>/);
    expect(html).toContain('name="volver" value="/app/listings/7"');
  });
});
