import { readdirSync, readFileSync, statSync } from "node:fs";
import path from "node:path";

import { describe, expect, it } from "vitest";

import { FORBIDDEN_TERMS } from "./copy";

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
    for (const file of [...sources(path.join(ROOT, "app")), ...sources(path.join(ROOT, "components")), path.join(ROOT, "lib", "copy.ts")]) {
      const text = readFileSync(file, "utf-8")
        .replace(ALLOWED, "")
        .replace(/FORBIDDEN_TERMS = \[[^\]]*\]/, "")
        .toLowerCase();
      for (const term of FORBIDDEN_TERMS) {
        if (new RegExp(`(^|[^\p{L}])${term}([^\p{L}]|$)`, "u").test(text)) {
          offenders.push(`${path.relative(ROOT, file)}: ${term}`);
        }
      }
    }
    expect(offenders).toEqual([]);
  });
});
