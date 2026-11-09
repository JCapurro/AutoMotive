import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";

import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { Inspector } from "@/components/admin/inspector";
import type { Inspection } from "@/lib/admin-inspect";

// f3 «precio × encaje» in shadow (docs/superpowers/specs/2026-11-08-recalibracion-score-design.md §4.4):
// the worker adds score_breakdown.shadow_f3 next to f2's components (worker/intelligence/engine.py
// Evaluation.row) while f2 keeps deciding. Nothing in the web may show it or change because of it.

const ROOT = path.resolve(__dirname, "..");

/** f2's breakdown as worker/intelligence/scoring.py Score.breakdown writes it. */
const F2_BREAKDOWN = {
  price: { c: 0.8, w: 40, contribution: 32, explanation: "8 % debajo de 23 publicaciones comparables" },
  match: { c: 1, w: 25, contribution: 25, explanation: "Cumple todos los filtros" },
  km: { c: 0.7, w: 15, contribution: 10.5, explanation: "Km dentro de lo esperado" },
  trim: { c: 1, w: 10, contribution: 10, explanation: "Versión pedida" },
  recency: { c: 0.5, w: 5, contribution: 2.5, explanation: "Publicado hace 3 días" },
  completeness: { c: 1, w: 5, contribution: 5, explanation: "Datos completos" },
  scoring_version: "f2-v5-seller-margin",
  guard: "suspicious",
};
/** The shadow_f3 contract (worker/intelligence/f3.py F3.to_json), with a different level and score than f2's. */
const SHADOW_F3 = {
  v: "f3-precio-encaje", mode: "shadow", params: "3f2a9c1d07be",
  level: "match", level_uncapped: "good", score: 61, raw: 58.2,
  deal: { value: 0.6, raw: 0.6, r: 1, diff_pct: 52.1, d: 52.1, d_eff: 52.1, d_full: 13.3929, s_lo: 5.3571, n: 23,
    level_used: "trim_transmission", kavak: false, placeholder: false, has_price: true, credible: false, tier: "verify" },
  fit: { level: 0.875, score: 0.845, unknown_hard: ["transmission"], prefs: { km_target: 1, seller_type: 0.75 } },
  flags: ["suspicious", "seller_unknown"], a_verificar: ["transmission", "seller_type"],
  seller: { wanted: ["private"], strict: false, effective: null, for_preference: null, agency_voice: "financiamos",
    mismatch: false, capped: false },
  would_defer: true,
  alternatives: { agency_voice_off: { level: "good", score: 74 } },
};

function inspection(breakdown: Record<string, unknown>): Inspection {
  const match = {
    id: 7, search_profile_id: 3, listing_id: 11, score: 88, level: "high", is_backfill: false, scoring_version: "f2-v5-seller-margin",
    score_breakdown: breakdown, match_reasons: { price: { result: "ok", detail: "USD 9.500 ≤ 10.000", kind: "hard" } },
    price_ref: { n: 23, level_used: "trim_transmission", median: 11200, p25: 10600, p75: 12100, median_km: 80000, diff_pct: 8.04 },
    red_flags: [], seller_questions: null, contact_questions: null, question_origins: null, margin_ref: null,
    generated_at: "2026-11-09T12:00:00Z", updated_at: "2026-11-09T12:00:00Z",
  };
  return { notification: null, siblings: [], match, listing: null, sourceName: null, profile: null, email: null, related: [] } as unknown as Inspection;
}

describe("score_breakdown.shadow_f3 in the web", () => {
  it("leaves the admin inspector exactly as without it", () => {
    const f2Only = renderToStaticMarkup(createElement(Inspector, { data: inspection(F2_BREAKDOWN) }));
    const withShadow = renderToStaticMarkup(createElement(Inspector, { data: inspection({ ...F2_BREAKDOWN, shadow_f3: SHADOW_F3 }) }));
    expect(withShadow).toBe(f2Only);
    // f2's six components and its guard are what it shows; nothing of the shadow.
    expect(f2Only).toContain("Kilometraje");
    expect(f2Only).toContain("guarda: suspicious");
    for (const text of ["shadow_f3", "f3-precio-encaje", "3f2a9c1d07be", "financiamos", "seller_unknown"]) expect(withShadow).not.toContain(text);
  });

  it("is read by no web source, and no reader of score_breakdown walks all its keys", () => {
    const sources = (dir: string): string[] => readdirSync(dir).flatMap((name) => {
      const full = path.join(dir, name);
      if (statSync(full).isDirectory()) return sources(full);
      return /\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name) ? [full] : [];
    });
    // The code of a file, without comments and quoted strings (the /admin/config hint may name the key).
    // Template literals stay: what goes in their ${} is code.
    const code = (text: string) => text
      .replace(/\/\*[\s\S]*?\*\//g, " ")
      .replace(/"(?:[^"\\\n]|\\.)*"|'(?:[^'\\\n]|\\.)*'/g, '""')
      .replace(/\/\/[^\n]*/g, " ");
    const files = ["app", "components", "lib"].flatMap((dir) => sources(path.join(ROOT, dir)));
    // While f2 decides, the shadow is for the decision log and the report (worker/tools/shadow_report.py) only.
    expect(files.filter((file) => code(readFileSync(file, "utf-8")).includes("shadow_f3")).map((file) => path.relative(ROOT, file))).toEqual([]);
    const readers = files.filter((file) => readFileSync(file, "utf-8").includes("score_breakdown"));
    // The listing page (ScoreInWords) and the inspector read it, by COMPONENTS and named keys (guard) only; the
    // /admin/config hint and lib/types.ts only name it. A new file here needs the same check by hand.
    expect(readers.map((file) => path.relative(ROOT, file)).sort()).toEqual([
      "app/admin/config/page.tsx", "app/app/listings/[id]/page.tsx", "components/admin/inspector.tsx", "lib/types.ts",
    ]);
    for (const file of readers) {
      const text = code(readFileSync(file, "utf-8"));
      expect(text, path.relative(ROOT, file)).not.toMatch(/Object\.(keys|values|entries)\(\s*(breakdown|[\w.?]*score_breakdown)/);
      expect(text, path.relative(ROOT, file)).not.toMatch(/\bin\s+(breakdown|[\w.?]*score_breakdown)\b|\.\.\.\s*(breakdown|[\w.?]*score_breakdown)\b/);
      expect(text, path.relative(ROOT, file)).not.toMatch(/(JSON\.stringify|<Json value=\{)\s*\(?\s*(breakdown|[\w.?]*score_breakdown)/);
    }
  });
});
