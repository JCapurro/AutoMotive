import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { COST_ESTIMATE, FOLLOW_EMPTY, FOLLOW_LABEL, FORBIDDEN_TERMS, TRACKING } from "./copy";

const ROOT = path.resolve(__dirname, "..");

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) return name === "ui" ? [] : sources(full);
    return /\.tsx?$/.test(name) && !name.endsWith(".test.ts") ? [full] : [];
  });
}

// The idiom of the §50 landing ("uno que vale la pena mirar") is not about price.
const ALLOWED = /vale la pena/gi;

describe("copy lint (§19)", () => {
  it("never says a car is worth a price, nor a real price or an appraisal", () => {
    const offenders: string[] = [];
    for (const file of [...sources(path.join(ROOT, "app")), ...sources(path.join(ROOT, "components")), path.join(ROOT, "lib", "copy.ts"), path.join(ROOT, "lib", "cost-estimator.ts")]) {
      const text = readFileSync(file, "utf-8")
        .replace(ALLOWED, "")
        .replace(/FORBIDDEN_TERMS = \[[^\]]*\]/, "")
        .toLowerCase();
      for (const term of FORBIDDEN_TERMS) {
        if (new RegExp(`(^|[^\\p{L}\\p{N}_])${term}([^\\p{L}\\p{N}_]|$)`, "u").test(text)) {
          offenders.push(`${path.relative(ROOT, file)}: ${term}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  it("keeps the follow-up texts (X-01) prudent and the note's privacy honest", () => {
    const texts = [...Object.values(TRACKING), ...Object.values(FOLLOW_LABEL), ...Object.values(FOLLOW_EMPTY)];
    expect(texts).toContain("La nota es privada: no se la mostramos al vendedor ni a otros usuarios.");
    for (const text of texts) {
      for (const term of FORBIDDEN_TERMS) {
        expect(new RegExp(`(^|[^\\p{L}\\p{N}_])${term}([^\\p{L}\\p{N}_]|$)`, "iu").test(text), `${text}: ${term}`).toBe(false);
      }
      // An admin with the service role can read the database: never promise "only you".
      expect(text).not.toMatch(/solo la ves vos/i);
    }
  });

  it("keeps the total cost estimate (PAR-01) estimated, never absolute", () => {
    const flat = (v: unknown): string[] => (typeof v === "string" ? [v] : v && typeof v === "object" ? Object.values(v).flatMap(flat) : []);
    const texts = flat(COST_ESTIMATE);
    expect(COST_ESTIMATE.line).toBe("Costo total estimado{suffix}: {usd} ({ars})");
    expect(COST_ESTIMATE.lineNoUsd).toBe("Costo total estimado{suffix}: {ars} (sin dólar del día)");
    expect(COST_ESTIMATE.lineNoFx).toBe("Costo total estimado: sin dólar del día, no se puede estimar");
    expect(COST_ESTIMATE.suffix).toBe(" (sin {items})");
    expect(COST_ESTIMATE.vf).toContain("supuesto propio, no oficial");
    for (const text of texts) {
      for (const term of [...FORBIDDEN_TERMS, "precio final", "costo real", "costo exacto", "total real"]) {
        expect(new RegExp(`(^|[^\\p{L}\\p{N}_])${term}([^\\p{L}\\p{N}_]|$)`, "iu").test(text), `${text}: ${term}`).toBe(false);
      }
      expect(text).not.toMatch(/8\s*[–-]\s*10\s*%/);
    }
  });
});
