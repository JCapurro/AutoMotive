-- PAR-01 · Costo total estimado (docs/BACKLOG_PRODUCTO_2026-10.md, ítem PAR-01;
-- diseño docs/superpowers/specs/2026-10-30-par01-costo-total-design.md; plan
-- docs/superpowers/plans/2026-10-30-par01-costo-total.md; parámetros aprobados
-- docs/superpowers/specs/2026-10-30-par01-parametros-costo-total.md).
--
-- Data only, idempotent:
-- * app_config.cost_estimator: every figure of the estimate (DNRPA fee, stamp
--   tax, forms, annual patente, domain report), each block with its source and
--   as_of. The calculators (worker/intelligence/cost_estimator.py,
--   web/lib/cost-estimator.ts) have no default: a missing or invalid block is
--   told as missing. An existing row is left alone.
-- * plan_limits.pass.total_cost and, during the pilot, plan_limits.free.total_cost
--   (Juan, 30/10/2026): only added when missing, so a toggle already turned off
--   in /admin/config stays off. Pro has no key (PRO-02 shows its costs).
-- No table, column, RLS, function, view or SCORING_VERSION change.

insert into public.app_config(key, value) values ('cost_estimator', '{
  "as_of": "2026-10-30",
  "status": "aprobado",
  "review": {"max_age_days": 120, "months": [12, 1], "source": "Decisión de Juan 30/10/2026: ciclo cuatrimestral del MRPA (Res. MJ 308/2026) y leyes impositivas de diciembre y enero", "as_of": "2026-10-30"},
  "fx": {"max_age_days": 3, "note": "Montos en ARS. Aviso en ARS: el dólar con el que se calculó price_usd (price / price_usd, como listing_snapshots.fx_rate). Aviso en USD: fila blue más reciente de fx_rates (si no hay, la oficial más reciente), descartada si tiene más de max_age_days días", "source": "Decisión de Juan 30/10/2026 (respuesta 6 a la revisión 2 de PAR-01)", "as_of": "2026-10-30"},
  "buyer_zone": {"max_locality_km": 80, "note": "Una zona de la búsqueda a más de max_locality_km de la localidad argentina más cercana no tiene jurisdicción (falta)", "source": "Decisión de Juan 30/10/2026 (respuesta 5 a la revisión 2 de PAR-01). Medido: Montevideo 106,8 km, Santiago de Chile 91,3 km, hueco máximo entre localidades del continente 127,7 km", "as_of": "2026-10-30"},
  "vf_from_price_k": {"min": 0.7, "max": 1.0, "source": "Supuesto propio, no oficial. Fundado en Res. AGIP 54/2026 (tabla con ACARA de oct-2025) y Ley 15.558 PBA art. 35 (ACARA x 0,95)", "as_of": "2026-10-30"},
  "transfer_base": {"value": "price", "note": "Arancel y sellos se calculan sobre el mayor entre precio y tabla; con k <= 1 es el precio", "source": "Res. MJ 412/2026 Anexo I; Res. 55/AGIP/26 art. 9", "as_of": "2026-09-01"},
  "mrpa_ars": {"min": 1010, "max": 1090, "source": "Res. MJ 308/2026 art. 1 (https://www.argentina.gob.ar/normativa/nacional/norma-427475/texto) + UVA BCRA var. 31; el max es una proyección desde el 04/11/2026", "as_of": "2026-10-30"},
  "dnrpa": {"pct": {"min": 1.0, "max": 1.0}, "dealer_pct": {"min": 0.9, "max": 1.0}, "min_mrpa": 32, "source": "Res. MJ 412/2026, Anexo I, arancel 2A (https://www.cira.org.ar/wp-content/uploads/anexo_7754131_1.pdf)", "as_of": "2026-09-01"},
  "fixed_ars": {
    "form_08": {"min": 8000, "max": 9600, "source": "IF-2026-06520679-APN-SSGA#MJ (https://www.dnrpa.gov.ar/portal_dnrpa/guia_tramites/IF-2026-06520679-APN-SSGA_MJ.pdf); max = +20 % no verificado en norma", "as_of": "2026-01-19"},
    "form_12": {"min": 0, "max": 9240, "source": "IF-2026-06520679-APN-SSGA#MJ (lista 7.700); min 0 por excepciones no confirmadas; max = +20 % no verificado", "as_of": "2026-01-19"}
  },
  "domain_report": {"mrpa": 4, "in_total": false, "note": "Opcional; recomendado antes de señar (checklist de PAR-02)", "source": "Res. MJ 412/2026, Anexo I, arancel 5A", "as_of": "2026-09-01"},
  "stamp_tax_pct": {
    "caba": {"private": {"min": 3.0, "max": 3.0}, "dealer": {"min": 3.0, "max": 3.0}, "source": "Ley 6927 Anexo art. 32 (https://boletinoficial.buenosaires.gob.ar/normativaba/norma/829857); Res. 55/AGIP/26 arts. 9 y 14", "as_of": "2026-01-01"},
    "ba": {"private": {"min": 3.0, "max": 3.0}, "dealer": {"min": 1.0, "max": 3.0}, "source": "Ley 15.558 art. 39 A) 12 a) y b) (https://www.arba.gov.ar/archivos/Publicaciones/leyimpositiva2026.pdf); el 1 % exige factura de agencia", "as_of": "2026-01-01"},
    "rest": {"private": {"min": 1.0, "max": 3.0}, "dealer": {"min": 0.5, "max": 3.0}, "source": "Córdoba Ley 11.090 art. 45; Santa Fe nomenclador API (Ley 14.426); Mendoza Ley 9680 art. 7; Tucumán tabla Rentas feb-2026. Techo 3 % prudente: 19 provincias sin revisar", "as_of": "2026-10-30"}
  },
  "patente": {
    "values_year": 2026,
    "caba": {"brackets": [{"from": 0, "fixed": 0, "pct": 1.6}, {"from": 7460000, "fixed": 119350, "pct": 4.0}, {"from": 17155000, "fixed": 507150, "pct": 4.5}, {"from": 26850000, "fixed": 943500, "pct": 5.5}, {"from": 36550000, "fixed": 1477000, "pct": 6.5}, {"from": 50350000, "fixed": 2374000, "pct": 7.0}, {"from": 73100000, "fixed": 3965000, "pct": 8.0}], "cap_pct_of_vf": 6.0, "min_ars": 13300, "pickup_flat_pct": 2.3, "pickup_body_types": ["pickup"], "subte_factor": {"min": 1.0, "max": 1.1}, "old_model_min_zero": {"age_years": 25, "note": "Mínimo 0 hasta confirmar el art. 433 del Código Fiscal (decisión de Juan 30/10/2026)"}, "note": "Factor Subte después del tope. La bonificación de la Ley 6942 (IPCBA 2025 = 31,8 %) puede bajar el monto y no se calcula", "source": "Ley 6927 Anexo art. 50 (https://documentosboletinoficial.buenosaires.gob.ar/publico/PL-LEY-LCABA-LCBA-6927-25-ANX.pdf); Ley 6942", "as_of": "2026-01-01"},
    "ba": {"brackets": [{"from": 0, "fixed": 0, "pct": 1.0}, {"from": 14100000, "fixed": 141000, "pct": 2.0}, {"from": 18700000, "fixed": 233000, "pct": 3.0}, {"from": 26100000, "fixed": 455000, "pct": 4.0}, {"from": 53900000, "fixed": 1567000, "pct": 4.5}], "ipc_factor": {"min": 1.0, "max": 1.25}, "discount_pct": 0, "min_model_year": 1990, "note": "ipc_factor.max provisorio hasta que ARBA publique el coeficiente; modelos < 1990 sin cálculo", "source": "Ley 15.558 arts. 33, 34, 35, 37 y 167 (https://normas.gba.gob.ar/ar-b/ley/2025/15558/554025)", "as_of": "2026-01-01"},
    "rest": {"min_pct": 0.85, "old_model": {"max_year": 2016, "min_pct": 0}, "max_pct_bands": [{"vf_upto": 59100000, "pct": 2.3}, {"vf_upto": 87500000, "pct": 2.5}, {"vf_upto": null, "pct": 3.0}], "note": "Solo Córdoba, Santa Fe y Mendoza revisadas", "source": "Córdoba Ley 11.090 arts. 55-57; Santa Fe LIA art. 55 y Ley 14.426; Mendoza Ley 9680 art. 9", "as_of": "2026-01-01"}
  },
  "gestoria": {"in_total": false, "official_value": null, "note": "Sin tabla oficial; honorarios libres. Se muestra como línea aparte", "source": "Sin norma que fije honorarios (Res. MJ 412/2026 y Digesto revisados)", "as_of": "2026-10-30"}
}')
on conflict (key) do nothing;

update public.app_config
   set value = jsonb_set(value, '{pass,total_cost}', 'true')
 where key = 'plan_limits'
   and jsonb_typeof(value->'pass') = 'object'
   and not (value->'pass' ? 'total_cost');

update public.app_config
   set value = jsonb_set(value, '{free,total_cost}', 'true')
 where key = 'plan_limits'
   and jsonb_typeof(value->'free') = 'object'
   and not (value->'free' ? 'total_cost');
