import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it, vi } from "vitest";

import { LimitsForm } from "@/components/admin/config-forms";

it("shows the web's effective defaults for absent plans without adding untouched values", () => {
  const value = { enforced: false }, onChange = vi.fn();
  const html = renderToStaticMarkup(createElement(LimitsForm, { value, onChange }));
  const free = html.slice(html.indexOf(">Prueba gratis</legend>"), html.indexOf(">Particular</legend>"));
  const pro = html.slice(html.indexOf(">Pro</legend>"));
  expect(free).toMatch(/aria-label="Prueba gratis: Resultados por búsqueda"[^>]*value="100"/);
  expect(pro).toMatch(/<input type="checkbox"[^>]*checked=""[^>]*\/><span>Umbral de oportunidad/);
  expect(pro).toMatch(/<input type="checkbox"[^>]*checked=""[^>]*\/><span>Buscar por carrocería sin modelo/);
  expect(html).toContain("hereda los valores predeterminados");
  expect(onChange).not.toHaveBeenCalled();
  expect(value).toEqual({ enforced: false });
});
