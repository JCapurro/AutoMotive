import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

// PRO-02 (20261130120000_pro02_margin.sql): anon/authenticated read matches by column,
// every column but margin_ref. A select("*"), a select() with no columns or an embedded
// matches(*) from the user's client asks PostgREST for margin_ref and gets a 403, so the
// web names the columns it reads. Only the service-role client (createAdminClient, which
// is not subject to column grants) may select * from matches.

const ROOT = path.resolve(__dirname, "..");

function sources(dir: string): string[] {
  return readdirSync(dir).flatMap((name) => {
    const full = path.join(dir, name);
    if (statSync(full).isDirectory()) return name === "node_modules" ? [] : sources(full);
    return /\.tsx?$/.test(name) && !/\.test\.tsx?$/.test(name) ? [full] : [];
  });
}

const STAR_FROM_MATCHES = /\.from\(\s*["'`]matches["'`]\s*\)\s*\.select\(\s*(?:\)|["'`]\s*\*)/g;
const EMBEDDED_STAR = /\bmatches(?:![a-z_]+)?\s*\(\s*\*/g;

function offenders(file: string): string[] {
  const text = readFileSync(file, "utf-8");
  const userClient = !/createAdminClient/.test(text) || /@\/lib\/supabase\/(server|client)["']/.test(text);
  const hits = [...text.matchAll(STAR_FROM_MATCHES), ...text.matchAll(EMBEDDED_STAR)];
  if (!hits.length) return [];
  // A file with only the admin client is fine; one with the user's client is not.
  return userClient ? hits.map((h) => `${path.relative(ROOT, file)}: ${h[0]}`) : [];
}

describe("matches is read by column (PRO-02)", () => {
  it("the user's client never selects * from matches", () => {
    const files = ["app", "components", "lib"].flatMap((d) => sources(path.join(ROOT, d)));
    expect(files.flatMap(offenders)).toEqual([]);
  });

  it("the patterns catch what PostgREST would refuse", () => {
    const sample = [
      `supabase.from("matches").select("*")`,
      `supabase.from('matches').select()`,
      `supabase.from("search_profiles").select("id, matches(*)")`,
      `supabase.from("listings").select("id, matches!inner(*)")`,
    ];
    for (const s of sample) expect([...s.matchAll(STAR_FROM_MATCHES), ...s.matchAll(EMBEDDED_STAR)]).not.toEqual([]);
    expect([...`supabase.from("matches").select("id, score")`.matchAll(STAR_FROM_MATCHES)]).toEqual([]);
  });
});
