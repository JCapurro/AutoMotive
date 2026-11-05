import { readFileSync } from "node:fs";
import { join } from "node:path";

import { expect, it } from "vitest";

const root = join(__dirname, "..", "..", "supabase");
const template = readFileSync(join(root, "templates", "recovery.html"), "utf8");
const config = readFileSync(join(root, "config.toml"), "utf8");

it("the email to enter shows the code /login and the pop-ups ask for, next to the link", () => {
  // The code's box (e2e and people look for it there) and the preheader.
  expect(template).toMatch(/letter-spacing:8px[^>]*>\{\{ \.Token \}\}</);
  expect(template).toContain("Tu código es {{ .Token }}");
  // The link stays, through /auth/confirm (works from another browser).
  expect(template).toContain("{{ .RedirectTo }}&amp;token_hash={{ .TokenHash }}&amp;type=recovery");
  expect(config).toContain('subject = "Tu código para entrar a Ese Auto"');
  // The code fields take 6 to 8 digits (lib/entry-code.ts normalizeCode).
  expect(config).toMatch(/\[auth\.email\][\s\S]*?otp_length = 6/);
});
