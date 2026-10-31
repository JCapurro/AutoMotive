import { readFileSync } from "node:fs";
import path from "node:path";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { DashboardAttention } from "@/components/admin/dashboard-ui";
import { AdminPlanLimitsInput, configFieldLabel, validateConfigChange } from "@/lib/admin-config";
import { costReviewItem, costReviewState, type DashboardData, getDashboardPeriod } from "@/lib/admin-dashboard";

// PAR-01: the cost estimator in /admin (validator, plan flag, review notice).
const GOLDEN = JSON.parse(
  readFileSync(path.resolve(__dirname, "../../worker/tests/fixtures/cost_estimator/golden.json"), "utf-8"),
) as { config: Record<string, unknown> };
const config = GOLDEN.config;
const withAsOf = (asOf: string) => ({ ...config, as_of: asOf });

describe("validateConfigChange('cost_estimator')", () => {
  it("accepts the design's JSON", () => {
    expect(validateConfigChange("cost_estimator", config, config)).toBeNull();
  });

  it("rejects each rule with its path, in Spanish", () => {
    const ba = config.patente as { ba: { brackets: { from: number }[] } };
    const badScale = { ...config, patente: { ...(config.patente as object), ba: { ...ba.ba, brackets: [ba.ba.brackets[1], ba.ba.brackets[0]] } } };
    expect(validateConfigChange("cost_estimator", badScale, config)).toBe('cost_estimator.patente.ba.brackets: el primer "from" tiene que ser 0.');
    const k = { ...config, vf_from_price_k: { ...(config.vf_from_price_k as object), min: 1.2, max: 1.3 } };
    expect(validateConfigChange("cost_estimator", k, config)).toBe("cost_estimator.vf_from_price_k.max: no puede superar 1 (base = precio).");
    const noSource = { ...config, mrpa_ars: { min: 1010, max: 1090, as_of: "2026-10-30" } };
    expect(validateConfigChange("cost_estimator", noSource, config)).toBe("cost_estimator.mrpa_ars.source: falta source.");
    expect(validateConfigChange("cost_estimator", withAsOf("ayer"), config)).toBe(
      "cost_estimator.as_of: tiene que ser una fecha AAAA-MM-DD (la de tu última revisión).",
    );
    expect(validateConfigChange("cost_estimator", [], config)).toBe("El valor tiene que ser object, como el actual.");
  });
});

describe("plan_limits.total_cost", () => {
  it("is a boolean per plan", () => {
    expect(AdminPlanLimitsInput.safeParse({ enforced: false, pass: { total_cost: true }, free: { total_cost: false } }).success).toBe(true);
    expect(AdminPlanLimitsInput.safeParse({ pass: { total_cost: "true" } }).success).toBe(false);
    const current = { enforced: false, pass: { max_profiles: 3 } };
    expect(validateConfigChange("plan_limits", { ...current, pass: { max_profiles: 3, total_cost: "yes" } }, current)).toMatch(/^Revisá los límites/);
    expect(validateConfigChange("plan_limits", { ...current, pass: { max_profiles: 3, total_cost: false } }, current)).toBeNull();
  });

  it("has a label in the change summary", () => {
    expect(configFieldLabel("plan_limits", "pass.total_cost")).toBe("Particular: costo total estimado");
    expect(configFieldLabel("plan_limits", "free.total_cost")).toBe("Prueba gratis: costo total estimado");
  });
});

describe("the review notice", () => {
  // Noon in Buenos Aires.
  const at = (day: string) => new Date(`${day}T15:00:00Z`);
  const period = getDashboardPeriod("7", new Date("2026-10-27T18:00:00Z"));
  const dashboard = (costReview: DashboardData["costReview"]): DashboardData => ({
    period, metrics: { data: null, error: null }, sources: { data: [], error: null }, llm: { data: [], error: null }, costReview,
  });
  const html = (asOf: string, today: string) =>
    renderToStaticMarkup(createElement(DashboardAttention, { data: dashboard(costReviewState(withAsOf(asOf), at(today))) }));

  it("shows the parameters older than review.max_age_days", () => {
    expect(html("2026-06-01", "2026-09-30")).toContain("Costo total: parámetros al 01/06, más de 120 días");
    expect(html("2026-06-23", "2026-10-21")).not.toContain("Costo total:");
  });

  it("shows December and January until the parameters are reviewed", () => {
    expect(html("2026-10-30", "2026-12-20")).toContain("Costo total: diciembre/enero, revisar leyes impositivas y MRPA");
    expect(html("2026-12-05", "2026-12-20")).not.toContain("Costo total:");
    expect(html("2026-12-05", "2027-01-15")).not.toContain("Costo total:");
    expect(html("2026-11-30", "2027-01-02")).toContain("Costo total: diciembre/enero");
    expect(html("2026-10-30", "2026-12-20")).toContain('href="/admin/config#cost_estimator"');
  });

  it("says when there are no valid parameters, and nothing when not read", () => {
    expect(costReviewItem(costReviewState(null))?.title).toBe("Costo total: sin parámetros válidos");
    expect(costReviewItem(null)).toBeNull();
    const plain = renderToStaticMarkup(createElement(DashboardAttention, { data: dashboard(null) }));
    expect(plain).not.toContain("Costo total:");
  });
});
