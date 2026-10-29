import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";

import { ContactedMetric } from "@/components/admin/criteria";

// X-01, decision 2: Contactado left criterion 5 and is measured on its own.
it("shows the Contactado metric next to the criteria, outside criterion 5", () => {
  const html = renderToStaticMarkup(createElement(ContactedMetric, { row: { users: 4, events: 7 } }));
  expect(html).toContain('data-testid="contacted-metric"');
  expect(html).toContain("Contactado");
  expect(html).toMatch(/>4<\/span> usuarios/);
  expect(html).toMatch(/>7<\/span> cambios/);
  expect(html).toContain("no cuenta para el criterio 5");
});

it("says so when the view is not there yet", () => {
  const html = renderToStaticMarkup(createElement(ContactedMetric, { row: null }));
  expect(html).toContain("Sin datos");
  expect(html).not.toContain("NaN");
});
