# PAR-01 · Costo total estimado

Ítem PAR-01 del [backlog de producto](../../BACKLOG_PRODUCTO_2026-10.md) y Fase 2, fila 4, del [plan por fases](../../PLAN_FASES_BACKLOG_PRODUCTO_2026-10.md) (secciones 3, 4, 5 y 8). Parámetros y decisiones aprobados: [2026-10-30-par01-parametros-costo-total.md](2026-10-30-par01-parametros-costo-total.md) (secciones 1 a 6; la 6 son las respuestas de Juan). Plan de ejecución: [2026-10-30-par01-costo-total.md](../plans/2026-10-30-par01-costo-total.md). Estado: **borrador para que Juan lo apruebe**; nada implementado ni aplicado en producción.

## Alcance

1. **Config.** `app_config.cost_estimator` sembrada con los valores aprobados, cada bloque con `source` y `as_of`. Flag `plan_limits.pass.total_cost = true`. Es la única migración; no toca funciones, vistas ni scores.
2. **Calculadora pura, una por lado.** `worker/intelligence/cost_estimator.py` y `web/lib/cost-estimator.ts`. Las dos pasan los mismos vectores dorados (`worker/tests/fixtures/cost_estimator/golden.json`), así que no pueden divergir.
3. **Superficies, solo con el plan Particular.** Ficha: línea y detalle desplegable (reemplaza `DealerFeesNotice`). Tarjeta: una línea. Email de oportunidad: una línea.
4. **Admin.** Validador, ayuda y aviso de vencimiento en `/admin`.

Fuera de alcance en v1: **orden por costo total** (ver «Orden por costo total»), línea en el digest, costos de transferencia para Pro (los muestra PRO-02 con el mismo `cost_estimator`), anclar k a un índice oficial y tablas de valuación por modelo.

## Estado actual (verificado en el repo, rama `claude/par01-costo-total`, HEAD `6f3cb0d`)

- **Aviso fijo.** `web/components/app/dealer-fees-notice.tsx:3-10` dice «Trámites y gestoría: 8–10% adicional estimado.» solo si `sellerType === "dealer"`. Lo usa únicamente la ficha (`web/app/app/listings/[id]/page.tsx:180`), como último hijo del bloque de precio (`:157-181`). Ningún test lo referencia.
- **Ficha.** Lee la fila completa (`select("*, sources(name)")`, `page.tsx:65`): `seller_type`, `body_type`, `year`, `price`, `currency`, `price_usd`, `fx_rate` y `description_facts`. Elige el match `best` (`:107`) y su búsqueda. `PriceVerdict` no se muestra con precio parcial ni sin `price_usd` (`:425`).
- **Tarjeta.** `web/components/app/listing-card.tsx:84-99`: precio, «de contado», «≈ USD X», «Financiable». Se usa en resultados, el inicio (`recent_opportunities`) y guardados. `match_cards` (`20261119120000_x01_tracking.sql:20-60`) no expone `seller_type`, `dealer_inferred`, `fx_rate` ni el origen de la búsqueda.
- **Dólar.** El worker calcula `price_usd = price / fx.rate` en la ingesta y guarda `listings.fx_rate`, pero solo en avisos en ARS (`worker/normalization/listing.py:78-85`). `fx_rates` tiene RLS sin acceso de clientes. Si falla la cotización, la ingesta usa un `_FALLBACK_RATE` de 1100 que no se guarda en `fx_rates` (`worker/normalization/fx.py:20,52-69`).
- **Zona del comprador.** `search_profiles.origin_lat/lon/radius_km` y `filters->>'location_label'`; `profiles.default_origin_*`. No hay provincia guardada. `worker/normalization/zone.py:nearest_locality` resuelve lat/lon a la localidad Georef más cercana (con `province_id`). La web trae el mismo dataset (`web/lib/data/argentina-locations.json`, copiado a `worker/normalization/data/ar_localities.json`) pero no tiene búsqueda por cercanía. Los presets AMBA y CABA guardan el centro de CABA (`web/lib/locations.ts:9,12`).
- **Email.** `templates.content()` arma `c.lines` para Telegram, email texto, HTML y bandeja web (`worker/notifications/templates.py:226-240`). El render es puro sobre `notifications.payload`; PAR-03 guarda `payload['price_track']` en `service.on_matches` solo para oportunidades (`service.py:171-203`). La audiencia (`db/repos/notifications.py:18-36`) no trae plan ni origen. `PRDCopyTests` fija las primeras líneas del email.
- **Plan.** `plan_feature(user, key)` y `my_plan_feature(key)` leen `app_config.plan_limits[plan]` (admins: todo). «Particular» es el plan `pass`. El validador de `plan_limits` tiene un schema con claves conocidas (`web/lib/admin-config.ts:19`).
- **Config/admin.** `webConfig` (`web/lib/config.ts:62-85`), `validateConfigChange` (`admin-config.ts:155-196`), `HINTS`/`NAMES` (`app/admin/config/page.tsx:10-36`), `DashboardAttention` (`components/admin/dashboard-ui.tsx:175-199`). `admin_update_setting` solo exige el mismo `jsonb_typeof`. El worker lee con `db.get_config` (caché de 60 s).
- **Copy.** `FORBIDDEN_TERMS` incluye «precio real» en la web (`web/lib/copy.ts:16`) y en el worker (`worker/intelligence/copy.py:14-15`). El lint web no escanea `web/lib` salvo `copy.ts`.
- **F-02.** En esta rama no existen `effective_seller`, `effectiveSeller` ni `dealer_inferred`. En `claude/f02-vendedor` (PR #58) está hecho el paso 1. Los helpers llegan en el paso 2, que se despliega junto con PRO-02.

## Decisiones de diseño

1. **Ningún número en el código.** Todo valor sale de `cost_estimator`, incluidos umbrales de edad, bandas, el tipo de carrocería de la pick-up y el vencimiento de 120 días. El parser es tolerante: un bloque inválido o sin `source`/`as_of` cuenta como ausente, y los términos que dependen de él pasan a «falta». No hay defaults numéricos.
2. **Una calculadora por lado, con vectores dorados compartidos.** Mismas fórmulas, el mismo orden de operaciones y solo `floor`/`ceil`, nunca `round` (Python y JS redondean distinto). El JSON dorado vive en `worker/tests/fixtures/cost_estimator/golden.json` (el mismo patrón que `web/lib/assisted.test.ts:20`) y lo leen `pytest` y `vitest`.
3. **Jurisdicción del comprador**, la misma para patente y transferencia: el origen de la búsqueda (`zones[0]`; las `extra_locations` se ignoran). `buyer_jurisdiction(lat, lon, label)`:
   - `lat`/`lon` null → `null` (falta).
   - `label` normalizado igual a `amba` → `amba`: el rango cubre CABA **y** Buenos Aires (unión: mínimo de los mínimos, máximo de los máximos). El preset guarda el centro de CABA; elegir CABA en silencio sería inventar.
   - Si no, `nearest_locality(lat, lon).province_id`: `02` → `caba`, `06` → `ba`, cualquier otra → `rest`.
   - No se usan `derive_zone` (parsea texto del aviso), `market_zones` (junta CABA con GBA) ni `listing_zones` (es del aviso, sin RLS de lectura y llenada solo por `market_stats`).
   - La web porta `nearest_locality` tal cual, con la misma preselección por distancia plana y los mismos `_CANDIDATES`, en un módulo `server-only`. Un test exige que los dos JSON de localidades sean iguales.
   - Ficha: la búsqueda del match `best`; sin match, `profiles.default_origin_*`; si no hay, `null`. Tarjeta: la búsqueda de la tarjeta (`search_profile_id`). Email: la búsqueda de la audiencia.
   - La UI siempre dice qué jurisdicción usó y por qué: «Patente y sellos de CABA, según tu búsqueda en «Palermo, CABA»». Así se ven los errores de borde (General Paz, coordenadas de IP redondeadas).
4. **Vendedor efectivo.** `effective_seller`/`effectiveSeller` de F-02: `dealer` si `seller_type = 'dealer'` o `dealer_inferred`; si no, `seller_type`. Con `null`, el rango cubre particular y agencia (unión). Si PAR-01 se implementa antes de que el paso 2 de F-02 esté en `main`, se usa la variante «solo `seller_type`» (como el paso 3 de F-02) y se cambia al helper cuando llegue, sin migración.
5. **Dólar.** Aviso en ARS: `P = price` y `R = listings.fx_rate`, el mismo de `price_usd`. Aviso en USD: `P = price × R`, con `R` la última fila **guardada** de `fx_rates` (blue primero, el patrón de `20261030120000_body_type.sql:319`), leída con el cliente admin en la web y con un repo nuevo en el worker. Nunca se usa el fallback de 1100. Sin `R`: un aviso en ARS muestra solo pesos y dice «sin dólar del día»; uno en USD no muestra estimación, porque las escalas están en pesos.
6. **Base.** Arancel y sellos sobre `P` (`transfer_base.value = "price"`; otro valor → esos términos faltan). Patente sobre `VF = P × k`.
7. **Sin estimación** si el precio es null o ≤ 0, o parcial (`publishedIsPartial` / `price_partial`, anticipo o cuota, como `PriceVerdict`), si falta `cost_estimator.as_of`, o si el plan no tiene `total_cost`. En esos casos no hay línea ni texto de reemplazo.
8. **Plan.** Flag `plan_limits.<plan>.total_cost`: `pass` true; `free` y `pro` sin la clave (false). Los admins lo ven (por `plan_feature`). Se apaga desde `/admin/config` sin deploy.
9. **El aviso 8–10 % se borra para todos.** Era un número sin fuente. Quien no tiene el flag ya no ve aviso de gastos (Pro recibe los costos de transferencia en PRO-02).
10. **El email guarda, no recalcula.** `payload['total_cost']` se calcula en `service.on_matches` (como `price_track`) solo para oportunidades cuya audiencia tiene el flag. Sin la clave en el payload no hay línea, y los snapshots viejos quedan idénticos byte a byte.

## `app_config.cost_estimator`

Mismos valores que la sección 4 de los parámetros. Cambios de forma (no de números), para que el código no tenga constantes:

- `status`: `"aprobado"`.
- `review`: vencimiento de 120 días y meses 12 y 1 (respuesta 12).
- `fixed_ars.domain_report_mrpa` sale del total y pasa a `domain_report` con `mrpa` = 4 (Res. 412/2026, 5A) e `in_total: false` (respuesta 3). El piso de 0 de la propuesta solo modelaba que es opcional.
- `patente.values_year` = 2026 para el rótulo «patente anual (valores 2026)» (respuesta 8).
- `patente.caba.old_model_min_zero.age_years` = 25 (respuesta 7) y `patente.caba.pickup_body_types` = `["pickup"]` (respuesta 11).
- `patente.rest.min_pct_model_year_le_2016` pasa a `patente.rest.old_model` = `{max_year: 2016, min_pct: 0}`.

```json
{
  "as_of": "2026-10-30",
  "status": "aprobado",
  "review": {
    "max_age_days": 120, "months": [12, 1],
    "source": "Decisión de Juan 30/10/2026: ciclo cuatrimestral del MRPA (Res. MJ 308/2026) y leyes impositivas de diciembre y enero",
    "as_of": "2026-10-30"
  },
  "fx": {"note": "Montos en ARS. Aviso en ARS: listings.fx_rate (el de price_usd). Aviso en USD: última fila guardada de fx_rates, blue primero."},
  "vf_from_price_k": {
    "min": 0.70, "max": 1.00,
    "source": "Supuesto propio, no oficial. Fundado en Res. AGIP 54/2026 (tabla con ACARA de oct-2025) y Ley 15.558 PBA art. 35 (ACARA x 0,95)",
    "as_of": "2026-10-30"
  },
  "transfer_base": {
    "value": "price",
    "note": "Arancel y sellos se calculan sobre el mayor entre precio y tabla; con k <= 1 es el precio",
    "source": "Res. MJ 412/2026 Anexo I; Res. 55/AGIP/26 art. 9",
    "as_of": "2026-09-01"
  },
  "mrpa_ars": {
    "min": 1010, "max": 1090,
    "source": "Res. MJ 308/2026 art. 1 (https://www.argentina.gob.ar/normativa/nacional/norma-427475/texto) + UVA BCRA var. 31; el max es una proyección desde el 04/11/2026",
    "as_of": "2026-10-30"
  },
  "dnrpa": {
    "pct": {"min": 1.0, "max": 1.0},
    "dealer_pct": {"min": 0.9, "max": 1.0},
    "min_mrpa": 32,
    "source": "Res. MJ 412/2026, Anexo I, arancel 2A (https://www.cira.org.ar/wp-content/uploads/anexo_7754131_1.pdf)",
    "as_of": "2026-09-01"
  },
  "fixed_ars": {
    "form_08": {"min": 8000, "max": 9600, "source": "IF-2026-06520679-APN-SSGA#MJ (https://www.dnrpa.gov.ar/portal_dnrpa/guia_tramites/IF-2026-06520679-APN-SSGA_MJ.pdf); max = +20 % no verificado en norma", "as_of": "2026-01-19"},
    "form_12": {"min": 0, "max": 9240, "source": "IF-2026-06520679-APN-SSGA#MJ (lista 7.700); min 0 por excepciones no confirmadas; max = +20 % no verificado", "as_of": "2026-01-19"}
  },
  "domain_report": {
    "mrpa": 4, "in_total": false,
    "note": "Opcional; recomendado antes de señar (checklist de PAR-02)",
    "source": "Res. MJ 412/2026, Anexo I, arancel 5A",
    "as_of": "2026-09-01"
  },
  "stamp_tax_pct": {
    "caba": {"private": {"min": 3.0, "max": 3.0}, "dealer": {"min": 3.0, "max": 3.0}, "source": "Ley 6927 Anexo art. 32 (https://boletinoficial.buenosaires.gob.ar/normativaba/norma/829857); Res. 55/AGIP/26 arts. 9 y 14", "as_of": "2026-01-01"},
    "ba": {"private": {"min": 3.0, "max": 3.0}, "dealer": {"min": 1.0, "max": 3.0}, "source": "Ley 15.558 art. 39 A) 12 a) y b) (https://www.arba.gov.ar/archivos/Publicaciones/leyimpositiva2026.pdf); el 1 % exige factura de agencia", "as_of": "2026-01-01"},
    "rest": {"private": {"min": 1.0, "max": 3.0}, "dealer": {"min": 0.5, "max": 3.0}, "source": "Córdoba Ley 11.090 art. 45; Santa Fe nomenclador API (Ley 14.426); Mendoza Ley 9680 art. 7; Tucumán tabla Rentas feb-2026. Techo 3 % prudente: 19 provincias sin revisar", "as_of": "2026-10-30"}
  },
  "patente": {
    "values_year": 2026,
    "caba": {
      "brackets": [
        {"from": 0, "fixed": 0, "pct": 1.60}, {"from": 7460000, "fixed": 119350, "pct": 4.00},
        {"from": 17155000, "fixed": 507150, "pct": 4.50}, {"from": 26850000, "fixed": 943500, "pct": 5.50},
        {"from": 36550000, "fixed": 1477000, "pct": 6.50}, {"from": 50350000, "fixed": 2374000, "pct": 7.00},
        {"from": 73100000, "fixed": 3965000, "pct": 8.00}
      ],
      "cap_pct_of_vf": 6.0, "min_ars": 13300,
      "pickup_flat_pct": 2.30, "pickup_body_types": ["pickup"],
      "subte_factor": {"min": 1.00, "max": 1.10},
      "old_model_min_zero": {"age_years": 25, "note": "Mínimo 0 hasta confirmar el art. 433 del Código Fiscal (decisión de Juan 30/10/2026)"},
      "note": "Factor Subte después del tope. La bonificación de la Ley 6942 (IPCBA 2025 = 31,8 %) puede bajar el monto y no se calcula",
      "source": "Ley 6927 Anexo art. 50 (https://documentosboletinoficial.buenosaires.gob.ar/publico/PL-LEY-LCABA-LCBA-6927-25-ANX.pdf); Ley 6942",
      "as_of": "2026-01-01"
    },
    "ba": {
      "brackets": [
        {"from": 0, "fixed": 0, "pct": 1.00}, {"from": 14100000, "fixed": 141000, "pct": 2.00},
        {"from": 18700000, "fixed": 233000, "pct": 3.00}, {"from": 26100000, "fixed": 455000, "pct": 4.00},
        {"from": 53900000, "fixed": 1567000, "pct": 4.50}
      ],
      "ipc_factor": {"min": 1.00, "max": 1.25}, "discount_pct": 0, "min_model_year": 1990,
      "note": "ipc_factor.max provisorio hasta que ARBA publique el coeficiente; modelos < 1990 sin cálculo",
      "source": "Ley 15.558 arts. 33, 34, 35, 37 y 167 (https://normas.gba.gob.ar/ar-b/ley/2025/15558/554025)",
      "as_of": "2026-01-01"
    },
    "rest": {
      "min_pct": 0.85,
      "old_model": {"max_year": 2016, "min_pct": 0},
      "max_pct_bands": [{"vf_upto": 59100000, "pct": 2.30}, {"vf_upto": 87500000, "pct": 2.50}, {"vf_upto": null, "pct": 3.00}],
      "note": "Solo Córdoba, Santa Fe y Mendoza revisadas",
      "source": "Córdoba Ley 11.090 arts. 55-57; Santa Fe LIA art. 55 y Ley 14.426; Mendoza Ley 9680 art. 9",
      "as_of": "2026-01-01"
    }
  },
  "gestoria": {
    "in_total": false, "official_value": null,
    "note": "Sin tabla oficial; honorarios libres. Se muestra como línea aparte",
    "source": "Sin norma que fije honorarios (Res. MJ 412/2026 y Digesto revisados)",
    "as_of": "2026-10-30"
  }
}
```

**Bloques y validación.** Un bloque es cada objeto con `source` y `as_of`: `review`, `vf_from_price_k`, `transfer_base`, `mrpa_ars`, `dnrpa`, `fixed_ars.form_08`, `fixed_ars.form_12`, `domain_report`, `stamp_tax_pct.{caba,ba,rest}`, `patente.{caba,ba,rest}` y `gestoria`. `patente.values_year` es un entero suelto, sin bloque. El `as_of` de la raíz es la fecha en que Juan revisó todo. El de cada bloque es la vigencia de la norma y **no** dispara avisos.

Reglas comunes al parser tolerante (los dos lados) y al validador estricto (zod en `CostEstimatorInput`, el mismo schema):
- `source`: string no vacío. `as_of`: `YYYY-MM-DD` válido.
- Rangos: números finitos, `0 <= min <= max`. Porcentajes ≤ 100.
- `k`: `0 < min <= max <= 1`. El techo de 1 sostiene «base = precio».
- Escalas: el primer `from` es 0, los `from` crecen estrictamente y `fixed`, `pct` ≥ 0.
- `max_pct_bands`: `vf_upto` crecientes y el último `null`.
- `min_model_year`, `old_model.max_year` y `age_years`: enteros. `review.months`: enteros de 1 a 12. `max_age_days`: entero > 0.

En el parser, un bloque que falla queda `null`. En `/admin/config`, el validador rechaza con el primer error en castellano: «cost_estimator.patente.ba.brackets: los "from" deben crecer».

## Calculadora

Firma, igual en los dos lados (`snake_case` en Python, `camelCase` en TS):

```
estimate(listing, jurisdiction, seller, fx_latest, cfg, today) -> Estimate | None
  listing: price, currency, price_usd, fx_rate, partial, year, body_type
  jurisdiction: 'caba' | 'ba' | 'rest' | 'amba' | None
  seller: 'dealer' | 'private' | None          (ya pasado por effective_seller)
  fx_latest: {rate, date} | None              (solo para avisos en USD)
  today: fecha en Argentina (UTC-3); ref_year = today.year
Estimate: p_ars, rate, terms[{code, min, max, block}], extras[{code, min, max}],
          missing[{code, reason}], total_ars{min,max}, total_usd{min,max} | None,
          jurisdiction, seller, as_of
```

Fórmulas (rangos `[min, max]`; `pct` en %, siempre `base * pct / 100`, multiplicación antes de la división):

- **Arancel DNRPA** (`dnrpa`, `mrpa_ars`, `transfer_base`). `pct` = `dealer_pct` para agencia, `pct` para particular y la unión de los dos sin dato. `min = max(P*pct.min/100, min_mrpa*mrpa.min)`; `max = max(P*pct.max/100, min_mrpa*mrpa.max)`.
- **Sellos** (`stamp_tax_pct[j]`, `transfer_base`). `P*pct/100` con el par de vendedor (unión sin dato). Con `amba`, unión de `caba` y `ba`. Sin `j` → falta.
- **Formularios 08 y 12** (`fixed_ars.form_08` y `form_12`). Suma de los rangos. Si falta uno, falta el término entero.
- **Patente anual** (`vf_from_price_k`, `patente[j]`, `values_year`). `VF = [P*k.min, P*k.max]`. Sin `year` → falta («falta el año del modelo»).
  - `scale(brackets, vf)` = `fixed + (vf - from)*pct/100` del último tramo con `from <= vf`.
  - CABA: si `body_type` está en `pickup_body_types`, `t = vf*pickup_flat_pct/100`. Si no, `t = min(scale(vf), vf*cap_pct_of_vf/100)`. Después `t = max(t, min_ars)` y `t = t*subte_factor` (`min` con `VF.min`, `max` con `VF.max`). Si `year <= ref_year - age_years`, el mínimo pasa a 0. El tope de 6 % es solo del inciso a). El mínimo de ARS 13.300 y el factor Subte se aplican a los dos incisos (la tabla de parámetros los lista para todo el art. 50; ver pregunta 3).
  - BA: si `year < min_model_year` → falta («modelo anterior a 1990 en Buenos Aires: sin dato»). Si no, `t = scale(vf)*ipc_factor*(100 - discount_pct)/100`.
  - Resto: `min = VF.min*(year <= old_model.max_year ? old_model.min_pct : min_pct)/100`. `max = VF.max*pct/100`, con `pct` de la primera banda en la que `vf_upto` es null o `VF.max <= vf_upto`.
  - `amba`: unión de CABA y BA. Si a una le falta el dato (BA < 1990), el término falta entero.
- **Extras fuera del total.** Informe de dominio: `[domain_report.mrpa*mrpa.min, domain_report.mrpa*mrpa.max]`. Gestoría: solo texto.
- **Total.** `total_ars = [P + Σ min, P + Σ max]` sobre los términos calculados. `total_usd = total_ars / R` si hay `R`.

Ejemplo de la sección 1 de los parámetros, sin el informe de dominio dentro del total (respuesta 3): ARS 20.000.000, particular, modelo 2017+, `R` = 1.300.

| | CABA | Buenos Aires | Resto | AMBA |
|---|---|---|---|---|
| Total ARS crudo | 21.188.950 – 21.517.532,5 | 20.948.000 – 21.158.840 | 20.527.000 – 21.278.840 | 20.948.000 – 21.517.532,5 |
| Línea | USD 16.290 – 16.560 (ARS 21.188.000 – 21.518.000) | USD 16.110 – 16.280 (ARS 20.948.000 – 21.159.000) | USD 15.790 – 16.370 (ARS 20.527.000 – 21.279.000) | USD 16.110 – 16.560 (ARS 20.948.000 – 21.518.000) |

**Redondeo (solo al mostrar, siempre hacia afuera para no achicar el rango).** Totales ARS: `floor` del mínimo y `ceil` del máximo a $1.000. USD: a 10. Detalle por término: a $100. Los porcentajes y k van con coma y dos decimales («0,70–1,00»). Si tras redondear `min == max`, se muestra un solo número. Miles con punto, armados a mano en los dos lados (sin `Intl` ni `locale`) para que el string sea idéntico. La fecha: `as_of` → `dd/mm`, sin zona horaria. Los vectores comparan los valores crudos con tolerancia de 0,01 y los strings exactos.

## Dónde se ve

Solo con `my_plan_feature('total_cost')` en la web y `plan_feature(sp.user_id, 'total_cost')` en el worker.

**Ficha** (`listings/[id]/page.tsx:157-181`): `<CostEstimate>` en lugar de `<DealerFeesNotice>`, `data-testid="cost-estimate"`.

```
Costo total estimado: USD 16.290 – 16.560 (ARS 21.188.000 – 21.518.000)
▸ Ver detalle                                   (<details>, emite total_cost_expanded una vez)
  Precio publicado                 ARS 20.000.000
  Arancel de transferencia DNRPA   ARS 200.000
  Sellos de CABA                   ARS 600.000
  Formularios 08 y 12              ARS 8.000 – 18.900
  Patente anual (valores 2026)     ARS 380.900 – 698.700
  Fuera del total: informe de dominio ARS 4.000 – 4.400, recomendado antes de señar.
  Gestor opcional: sin tarifa oficial, se pacta con el gestor.
  Patente y sellos de CABA, según tu búsqueda en «Palermo, CABA». Vendedor: particular.
  La valuación fiscal se estima como precio × 0,70–1,00 (supuesto propio, no oficial). Si la
  tabla oficial de tu modelo supera el precio, el arancel y los sellos son mayores.
  Parámetros al 30/10. Fuentes: Res. MJ 412/2026, Ley 6927, …   (fuente y as_of por término)
```

- Faltantes: «Costo total estimado (sin patente): …» y en el detalle «Patente: falta el año del modelo».
- Variantes de texto: AMBA («Tu búsqueda es AMBA: el rango cubre CABA y provincia de Buenos Aires.»), resto («Resto del país: rango armado con Córdoba, Santa Fe y Mendoza.»), vendedor («posible agencia», «concesionaria», «sin informar: el rango cubre particular y agencia»).
- Sin `R` en un aviso en pesos: «ARS A – B (sin dólar del día)».

**Tarjeta** (`listing-card.tsx`, debajo de la línea de precio): una línea, `data-testid="cost-estimate-line"`, el mismo texto que el encabezado de la ficha, sin detalle. A 375 px puede partirse en dos renglones, pero sin scroll horizontal. Los datos llegan con una consulta por página (decisión: no tocar `match_cards`): `listings.select("id, seller_type, dealer_inferred, fx_rate, description_facts").in("id", ids)`, más los orígenes de las búsquedas de la página (resultados: una; inicio y guardados: las distintas `search_profile_id`), `webConfig().costEstimator` y la última cotización (cliente admin, `cache()` por request). Sin el flag no se hace ninguna consulta extra.

**Email de oportunidad.** `total_cost_line(p.get("total_cost"))` va después de `price_track_line` (`templates.py:239-240`), así que no rompe `PRDCopyTests`. Texto: «Costo total estimado: USD X – Y (ARS A – B). Parámetros al dd/mm.», o «Costo total estimado (sin patente): …». Va en `c.lines`, como PAR-03, así que también aparece en Telegram y en la bandeja web: el mismo dato, con el mismo flag. Estilo HTML por defecto (`<p>` apagado). `payload['total_cost'] = {ars_min, ars_max, usd_min, usd_max, missing: [codes], jurisdiction, as_of}`, con valores ya redondeados. El costo queda congelado al crear la fila, como `price_track`. El digest no lleva la línea en v1.

## Orden por costo total: no en v1

El plan por fases ya lo dejó fuera («Sin orden por costo total en v1»). Costo de consulta medido sobre el código:

- Ordenar en SQL obliga a redefinir `search_results` por sexta vez, copiando el cuerpo de X-01 con el tope del plan.
- `match_cards` no tiene `seller_type`, `dealer_inferred`, `fx_rate` ni jurisdicción. Habría que agregar columnas a la vista (solo al final) y portar a SQL la calculadora, la jurisdicción por cercanía (4.022 localidades) y la lectura de `app_config` (sin acceso para `authenticated`: helper `security definer`, como PAR-03). Sería una tercera implementación de la calculadora, fuera de los vectores dorados.
- Además, con rangos hay que elegir por qué extremo se ordena.
- Ordenar en la web solo la página cargada (`p_limit = PAGE_SIZE*page+1`) engaña con la paginación.

Queda para v2 si los eventos muestran uso. `results_sorted_total_cost` queda reservado y documentado, pero **no se emite** en v1.

## Eventos

- `total_cost_expanded`: server action `trackTotalCostExpanded(listingId, jurisdiction, missing)` con zod, siguiendo el patrón de `trackPriceHistoryExpanded` (`listings/actions.ts:183-191`). Props `{listing_id, jurisdiction, missing}` (cantidad de términos faltantes). Una vez por apertura del `<details>`, nunca a Pixel/GA.
- `results_sorted_total_cost`: reservado para v2.

## Admin

- `validateConfigChange("cost_estimator", …)` con `CostEstimatorInput`. `NAMES.cost_estimator = "Costo total (PAR-01)"`. `HINTS.cost_estimator`: «Parámetros del costo total estimado (PAR-01). Cada bloque necesita source y as_of. as_of de la raíz: fecha en que revisaste todo; se muestra como «parámetros al dd/mm». Porcentajes en %, montos en ARS, rangos {min, max}. Sin un bloque válido, ese concepto se muestra como faltante.»
- `plan_limits`: `total_cost: z.boolean().optional()` en el schema (`admin-config.ts:19`), su rótulo («costo total estimado», `:130`) y un toggle en `config-forms.tsx`.
- **Aviso de vencimiento.** `costEstimatorReview(cfg, today)` es pura y vive en `cost-estimator.ts`. Devuelve `stale` si `today - as_of > review.max_age_days` y `due` si el mes de `today` está en `review.months`. Sin `review` o sin `as_of` devuelve `missing`. `loadAdminDashboard` lee la clave y `DashboardAttention` agrega «Costo total: parámetros al dd/mm, más de 120 días» o «Costo total: diciembre/enero, revisar leyes impositivas y MRPA», con link a `/admin/config#cost_estimator`. El mismo aviso aparece en la tarjeta de la clave.
- Edición con el textarea JSON actual. Sin formulario guiado en v1.

## Copy

- Web: bloque `COST_ESTIMATE` en `web/lib/copy.ts`, junto a `PRICE_TRACK`.
- Worker: `TOTAL_COST` en `worker/intelligence/copy.py`, que cubre el lint AST.
- `cost-estimator.ts` y `cost_estimator.py` devuelven códigos (`patente`, `no_year`, …), no textos.
- `cost-estimator.ts` se suma al escaneo de `copy.test.ts` de todos modos.
- Lint por funcionalidad, como PAR-03, con los términos extra «precio final», «costo real», «costo exacto» y «total real».
- La palabra «estimado» aparece siempre en la línea.

## Qué NO cambia

Scores, `SCORING_VERSION`, `price_ref`, `match_cards`, `search_results`, umbrales de alerta, `PriceVerdict`, «≈ USD X» de ficha y tarjeta, `listing_payload`, snapshots de payloads sin `total_cost`, digest y lifecycle emails.

## Riesgos

- **Borde CABA/GBA** por centroide más cercano y coordenadas redondeadas: se mitiga mostrando la jurisdicción usada.
- **`fx_rate` con el fallback de 1100.** Un aviso ingerido con la cotización caída puede tener ese `fx_rate`. Task 0 cuenta los casos (filas sin una fila de `fx_rates` de su día); si existen, se decide si se excluyen.
- **Valores que vencen.** MRPA en noviembre, ARBA y leyes 2027: el aviso de `/admin` es la única defensa.
- **Edición por SQL directo** saltea el validador. El parser tolerante convierte lo inválido en «falta».
- **Dependencia de F-02 paso 2** para `dealer_inferred`: variante «solo `seller_type`».
- **Choques de archivos:** `templates.py`/snapshots van después de PRO-02 (plan §4); `admin-config.ts` y `config-forms.tsx` con PRO-01/02.
- **Rendimiento de tarjetas:** una consulta más por página y la búsqueda por cercanía en el servidor (4.022 puntos, cacheada por origen).

## Operación y rollback

- **Migración** `supabase/migrations/20261124120000_par01_cost_estimator.sql` (por encima de los `2026112312xxxx` de F-02; releer `max(version)` de producción justo antes y renombrar si PRO-01, PRO-02 o F-02 sumaron otras). Contenido: `insert … on conflict (key) do nothing` de `cost_estimator`, y `plan_limits.pass.total_cost = true` solo si la clave no existe. Va con OK de Juan, en una transacción con el insert de su versión. `supabase/seed.sql` recibe lo mismo.
- **Sin cambio de score, sin bump, sin rescore.** El worker toma la config en menos de 60 s; la web, en el request siguiente.
- **Orden de deploy:** migración → worker (`wait_idle`) → web. Una web nueva con la base vieja no muestra nada: sin `cost_estimator` no hay `as_of`.
- **Rollback rápido:** `plan_limits.pass.total_cost = false` en `/admin/config` apaga ficha, tarjeta y email sin deploy.
- **Rollback de código:** revert de web y worker. `DealerFeesNotice` vuelve con el revert. La fila de config queda sin uso y se puede borrar.

## Preguntas para Juan

1. **Plan Free.** Mientras `plan_limits.enforced = false` (piloto), casi todos los usuarios resuelven a `free`, así que con solo `pass` casi nadie lo ve. ¿Se prende también `free.total_cost`? Recomiendo sí durante el piloto. Es un toggle, sin deploy.
2. **Free y Pro pierden el aviso de agencia.** Al borrar el 8–10 % para todos, quien no tiene el flag deja de ver un aviso de gastos en avisos de agencia. ¿OK? (Pro lo recupera con PRO-02.)
3. **CABA, mínimo y Subte en pick-ups.** ¿El mínimo de ARS 13.300 y el factor Subte se aplican también al inciso b) (2,30 % plano)? Propongo sí, porque la tabla los lista para todo el art. 50. Si no, son dos claves más en la config.
4. **Informe de dominio** con `mrpa: 4` (ARS 4.040 – 4.360) como línea aparte, en lugar del rango 0–4 de la propuesta. ¿OK?
