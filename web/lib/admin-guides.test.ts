import { beforeEach, describe, expect, it, vi } from "vitest";

const mocks = vi.hoisted(() => ({ requireAdmin: vi.fn(), client: vi.fn(), rpc: vi.fn(), single: vi.fn(), refresh: vi.fn(), revalidatePath: vi.fn() }));
vi.mock("server-only", () => ({}));
vi.mock("next/cache", () => ({ refresh: mocks.refresh, revalidatePath: mocks.revalidatePath }));
vi.mock("@/lib/admin", () => ({ requireAdmin: mocks.requireAdmin }));
vi.mock("@/lib/supabase/admin", () => ({ createAdminClient: mocks.client }));

import { createGuide, requestGuide, saveGuide, setGuideStatus } from "@/app/admin/guides/actions";
import { configFieldLabel, MODEL_GUIDE_LIMITS_MESSAGE, MODEL_GUIDES_MESSAGE, validateConfigChange } from "@/lib/admin-config";
import { argentinaStarts, guideGeneration } from "@/lib/admin-guides";

const BODY = {
  known_issues: [{ text: "Caja: tirones en primera.", applies_to: null }],
  visit_checklist: [{ text: "Probar la caja en frío.", applies_to: null }],
  versions_equipment: [{ text: "S, SE y Titanium.", applies_to: null }],
  maintenance_costs: [{ text: "Distribución por correa.", applies_to: null }],
  generations: [{ label: "Mk7", year_from: 2011, year_to: 2019, text: "Kinetic Design." }],
};
const QUESTIONS = [
  { text: "¿Tiene los services hechos?", why: "" },
  { text: "¿Cuándo se cambió la correa?", why: "" },
  { text: "¿La caja hace tirones en frío?", why: "" },
];
const SOURCES = [{ title: "Manual", url: "https://example.test/manual", kind: "manual", verified: true }];
// The updated_at of the page the admin has open (PostgREST and the page may format it differently).
const SEEN = "2026-11-05T12:00:00.123456+00:00";
const VALUES = { make: "Ford", model: "Fiesta", generation_label: null, year_from: 2011, year_to: 2019, body: BODY, questions: QUESTIONS, sources: [] };

beforeEach(() => {
  vi.clearAllMocks();
  mocks.requireAdmin.mockResolvedValue({ id: "session-admin", email: "juan@example.test" });
  mocks.rpc.mockResolvedValue({ data: { id: 3, updated_at: "t2", status: "published", slug_make: "ford", slug_model: "fiesta" }, error: null });
  mocks.single.mockResolvedValue({ data: { body: BODY, questions: QUESTIONS, sources: SOURCES, updated_at: SEEN }, error: null });
  mocks.client.mockReturnValue({ rpc: mocks.rpc, from: vi.fn(() => ({ select: vi.fn(() => ({ eq: vi.fn(() => ({ maybeSingle: mocks.single })) })) })) });
});

describe("/admin/guides actions", () => {
  it("every action checks the admin first", async () => {
    mocks.requireAdmin.mockRejectedValue(new Error("admin_required"));
    await expect(saveGuide({ id: 3, expectedUpdatedAt: "t1", values: VALUES })).rejects.toThrow("admin_required");
    await expect(setGuideStatus({ id: 3, status: "published", expectedUpdatedAt: SEEN })).rejects.toThrow("admin_required");
    await expect(requestGuide({ id: 3 })).rejects.toThrow("admin_required");
    expect(mocks.client).not.toHaveBeenCalled();
  });

  it("creating a draft stores the catalog model with its slugs, as the session's admin", async () => {
    mocks.rpc.mockResolvedValue({ data: { id: 9 }, error: null });
    expect(await createGuide({ make: "Volkswagen", model: "Gol Trend" })).toEqual({ ok: true, id: 9 });
    const [name, args] = mocks.rpc.mock.calls[0];
    expect(name).toBe("admin_save_model_guide");
    expect(args).toMatchObject({ p_id: null, p_actor_id: "session-admin", p_values: { slug_make: "volkswagen", slug_model: "gol-trend" } });
  });

  it("saving runs the copy lint before the RPC and says which row fails", async () => {
    const bad = { ...VALUES, body: { ...BODY, maintenance_costs: [{ text: "El kit sale USD 400.", applies_to: null }] } };
    expect(await saveGuide({ id: 3, expectedUpdatedAt: "t1", values: bad })).toEqual({ error: "Mantenimiento y costos típicos, renglón 1: tiene una cifra de dinero." });
    expect(mocks.rpc).not.toHaveBeenCalled();
  });

  it("saving a published guide invalidates its page, /guias and the sitemap", async () => {
    expect(await saveGuide({ id: 3, expectedUpdatedAt: "t1", values: VALUES })).toEqual({ ok: true, id: 3, updatedAt: "t2" });
    expect(mocks.rpc).toHaveBeenCalledWith("admin_save_model_guide", expect.objectContaining({ p_id: 3, p_expected_updated_at: "t1", p_actor_id: "session-admin" }));
    expect(mocks.revalidatePath.mock.calls.map((c) => c[0])).toEqual(["/guias/ford/fiesta", "/guias", "/sitemap.xml", "/llms.txt", "/llms-full.txt"]);
  });

  it("a conflict says so", async () => {
    mocks.rpc.mockResolvedValue({ data: null, error: { message: "guide_conflict" } });
    expect((await saveGuide({ id: 3, expectedUpdatedAt: "t1", values: VALUES })).error).toContain("Otra persona cambió esta guía");
  });

  it("publishing refuses an unchecked source before calling the RPC", async () => {
    mocks.single.mockResolvedValue({ data: { body: BODY, questions: QUESTIONS, sources: [{ title: "x", url: "https://x.test", kind: "otra", verified: false }], updated_at: SEEN }, error: null });
    expect((await setGuideStatus({ id: 3, status: "published", expectedUpdatedAt: SEEN })).error).toContain("La revisé");
    expect(mocks.rpc).not.toHaveBeenCalled();
  });

  it("publishing refuses a guide without sources: none is not «all checked»", async () => {
    mocks.single.mockResolvedValue({ data: { body: BODY, questions: QUESTIONS, sources: [], updated_at: SEEN }, error: null });
    expect((await setGuideStatus({ id: 3, status: "published", expectedUpdatedAt: SEEN })).error).toContain("al menos una fuente");
    expect(mocks.rpc).not.toHaveBeenCalled();
    mocks.single.mockResolvedValue({ data: null, error: null });
    mocks.rpc.mockResolvedValue({ data: null, error: { message: "guide_sources_missing" } });
    expect((await setGuideStatus({ id: 3, status: "published", expectedUpdatedAt: SEEN })).error).toContain("al menos una fuente");
  });

  it("publishing needs the version on screen: a guide the worker rewrote since is not published", async () => {
    expect((await setGuideStatus({ id: 3, status: "published" })).error).toBe("Datos inválidos.");
    // «Regenerar» on this page, the worker wrote a new draft, «Publicar» on the stale page.
    mocks.single.mockResolvedValue({ data: { body: BODY, questions: QUESTIONS, sources: SOURCES, updated_at: "2026-11-05T12:09:00+00:00" }, error: null });
    expect((await setGuideStatus({ id: 3, status: "published", expectedUpdatedAt: SEEN })).error).toContain("cambió desde que abriste esta página");
    expect(mocks.rpc).not.toHaveBeenCalled();
    // Same instant, other format: the same version.
    mocks.single.mockResolvedValue({ data: { body: BODY, questions: QUESTIONS, sources: SOURCES, updated_at: "2026-11-05T12:00:00.123456Z" }, error: null });
    expect((await setGuideStatus({ id: 3, status: "published", expectedUpdatedAt: SEEN })).ok).toBe(true);
    // A change between the read and the RPC: the RPC refuses it.
    mocks.rpc.mockResolvedValue({ data: null, error: { message: "guide_changed" } });
    expect((await setGuideStatus({ id: 3, status: "published", expectedUpdatedAt: SEEN })).error).toContain("Recargá y revisala");
    expect(mocks.revalidatePath).toHaveBeenCalledTimes(5);
  });

  it("publishing and unpublishing invalidate the public pages", async () => {
    expect((await setGuideStatus({ id: 3, status: "published", expectedUpdatedAt: SEEN })).ok).toBe(true);
    expect(mocks.rpc).toHaveBeenCalledWith("admin_set_model_guide_status", { p_id: 3, p_status: "published", p_actor_id: "session-admin", p_expected_updated_at: SEEN });
    expect(mocks.revalidatePath).toHaveBeenCalledWith("/guias/ford/fiesta");
    await setGuideStatus({ id: 3, status: "draft" });
    expect(mocks.rpc).toHaveBeenLastCalledWith("admin_set_model_guide_status", { p_id: 3, p_status: "draft", p_actor_id: "session-admin", p_expected_updated_at: null });
  });

  it("asking for a draft with the generation off says it is off", async () => {
    mocks.rpc.mockResolvedValue({ data: null, error: { message: "guide_generation_off" } });
    expect((await requestGuide({ id: 3 })).error).toContain("apagada");
  });
});

describe("llm_limits.model_guide and model_guides in /admin/config", () => {
  const limits = { per_user_hour: 30, email_only_per_user_hour: 5, model_guide: { enabled: false, per_day: 30, per_month: 60, queued_ttl_minutes: 60, timeout_seconds: 180, max_questions_in_listing: 3 } };

  it("accepts the migration's defaults and the pilot's", () => {
    expect(validateConfigChange("llm_limits", limits, limits)).toBeNull();
    expect(validateConfigChange("llm_limits", { ...limits, model_guide: { ...limits.model_guide, enabled: true, per_day: 5 } }, limits)).toBeNull();
    // A base without the sub-key keeps working.
    expect(validateConfigChange("llm_limits", { per_user_hour: 30 }, { per_user_hour: 30 })).toBeNull();
  });

  it.each([
    { max_questions_in_listing: 4 },
    { max_questions_in_listing: -1 },
    { enabled: "true" },
    { per_day: 61 },
    { per_month: 1.5 },
    { timeout_seconds: 5 },
  ])("refuses %o", (patch) => {
    expect(validateConfigChange("llm_limits", { ...limits, model_guide: { ...limits.model_guide, ...patch } }, limits)).toBe(MODEL_GUIDE_LIMITS_MESSAGE);
  });

  it("validates the pilot and the events' caps", () => {
    expect(validateConfigChange("model_guides", { pilot: [1, 2, 3, 4, 5] }, { pilot: [] })).toBeNull();
    expect(validateConfigChange("model_guides", { pilot: ["a"] }, { pilot: [] })).toBe(MODEL_GUIDES_MESSAGE);
    expect(validateConfigChange("model_guides", { pilot: [], events: { per_guide_minute: 0, per_guide_hour: 10 } }, { pilot: [] })).toBe(MODEL_GUIDES_MESSAGE);
  });

  it("labels the fields", () => {
    expect(configFieldLabel("llm_limits", "model_guide.max_questions_in_listing")).toBe("Guías: preguntas por aviso (hasta 3)");
  });

  it("reads the switch off without the key, and Argentina's day and month", () => {
    expect(guideGeneration({})).toEqual({ enabled: false, perDay: 0, perMonth: 0 });
    expect(guideGeneration(limits)).toEqual({ enabled: false, perDay: 30, perMonth: 60 });
    expect(argentinaStarts(new Date("2026-11-03T02:00:00Z"))).toEqual({ today: "2026-11-02T03:00:00.000Z", month: "2026-11-01T03:00:00.000Z" });
  });
});
