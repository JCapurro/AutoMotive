import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it, vi } from "vitest";

import { LimitsForm } from "@/components/admin/config-forms";

it("shows the web's effective defaults for absent plans without adding untouched values", () => {
  const value = { enforced: false }, onChange = vi.fn();
  const html = renderToStaticMarkup(createElement(LimitsForm, { value, onChange }));
  const free = html.slice(html.indexOf(">Prueba gratis</legend>"), html.indexOf(">Particular</legend>"));
  const pro = html.slice(html.indexOf(">Pro</legend>"));
  expect(free).toMatch(/aria-label="Prueba gratis: Resultados por búsqueda"[^>]*value="50"/);
  expect(free).toContain('aria-label="Prueba gratis: Resultados acumulados durante la prueba"');
  expect(pro).toMatch(/<input type="checkbox"[^>]*checked=""[^>]*\/><span>Umbral de oportunidad/);
  expect(pro).toMatch(/<input type="checkbox"[^>]*checked=""[^>]*\/><span>Buscar por carrocería sin modelo/);
  expect(html).toContain("hereda los valores predeterminados");
  expect(onChange).not.toHaveBeenCalled();
  expect(value).toEqual({ enforced: false });
});

// PAR-01: plan_limits.<plan>.total_cost, a toggle per plan.
it("toggles the total cost estimate per plan, off when the key is absent", () => {
  const value = { enforced: false, free: { total_cost: true }, pass: { total_cost: true }, pro: { max_profiles: 20 } };
  const html = renderToStaticMarkup(createElement(LimitsForm, { value, onChange: vi.fn() }));
  const part = (from: string, to?: string) => html.slice(html.indexOf(from), to ? html.indexOf(to) : undefined);
  expect(part(">Particular</legend>", ">Pro</legend>")).toMatch(/<input type="checkbox"[^>]*checked=""[^>]*\/><span>Costo total estimado \(PAR-01\)/);
  expect(part(">Prueba gratis</legend>", ">Particular</legend>")).toMatch(/<input type="checkbox"[^>]*checked=""[^>]*\/><span>Costo total estimado \(PAR-01\)/);
  const pro = part(">Pro</legend>");
  expect(pro).toMatch(/<input type="checkbox"(?![^>]*checked)[^>]*\/><span>Costo total estimado \(PAR-01\)/);
});
