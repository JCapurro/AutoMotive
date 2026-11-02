import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";

import PrivacyPage from "@/app/privacidad/page";

it("no longer lists «Tus notas»: the note was removed (Juan 02/11), the date says so", () => {
  const html = renderToStaticMarkup(PrivacyPage());
  expect(html).not.toContain("Tus notas");
  expect(html).not.toContain("Tu nota");
  expect(html).toContain("2 de noviembre de 2026");
  // The follow-up statuses stay, and so does their mention.
  expect(html).toContain("«compré»");
});
