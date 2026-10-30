# PAR-01 · Parámetros del costo total estimado

Ítem PAR-01 del [backlog de producto](../../BACKLOG_PRODUCTO_2026-10.md). Estado: **propuesta para que Juan la apruebe**. No hay nada cargado en `app_config` ni implementado.

Regla de Juan (30/10/2026): solo números reales sacados de documentación oficial, cada uno con fecha y fuente. Si un valor no se conoce con certeza, se propone un **rango**, se dice por qué y ese rango se lleva al total. El cálculo **reemplaza** el texto fijo «Trámites y gestoría: 8–10% adicional estimado» (`web/components/app/dealer-fees-notice.tsx`).

Cada valor salió de una investigación y pasó por una verificación aparte contra la fuente. Abajo figuran solo los valores verificados, o el valor corregido por el verificador cuando trae una fuente oficial. Los que no pasaron la verificación están en la sección 3.

---

## 1. Qué se calcula y fórmula

```
costo_total = precio
            + transferencia = arancel DNRPA + sellos + gastos fijos
            + patente anual
            (gestoría: línea aparte, fuera del total)
```

| Término | Base | Quién lo paga |
|---|---|---|
| Arancel DNRPA | 1 % del **mayor** entre la tabla de valuación DNRPA y el precio declarado en el 08, con un mínimo de 32 MRPA | Comprador, por costumbre. La norma no dice quién paga |
| Sellos | % sobre el **mayor** entre el precio declarado y la valuación fiscal de la jurisdicción (CABA y Santa Fe lo dicen; PBA y Córdoba no está confirmado) | Comprador, por costumbre. En CABA las partes responden solidariamente |
| Gastos fijos | Montos fijos (formularios 08 y 12, informe de dominio) | Comprador el 08 y el informe. El 12 lo paga el vendedor o se negocia |
| Patente anual | Escala o alícuota sobre la **valuación fiscal (VF)** de la jurisdicción (AGIP, ACARA × 0,95 en PBA, Rentas), **no** sobre el precio | Titular, o sea el comprador desde que se inscribe la transferencia |
| Gestoría | Honorario libre, sin tabla oficial | Comprador, solo si contrata un gestor |

**Jurisdicción.** La patente y los sellos se calculan con la del **comprador**, es decir la zona de la búsqueda, que es donde se radica el auto. La provincia del aviso no sirve para esto. Si falta la jurisdicción, se muestra solo lo calculable y se dice qué falta.

**Bases que no tenemos.** La app no tiene las tablas de valuación DNRPA, AGIP, ARBA ni de las provincias: se consultan por dominio en cada organismo. Propuesta:

- **VF ≈ precio publicado × k, con k entre 0,70 y 1,00.** Es un **supuesto propio, no oficial**. Se apoya en que las tablas están atrasadas respecto del aviso (CABA usa valores ACARA de octubre de 2025, según la Res. AGIP 54/2026) y en que PBA aplica ACARA × 0,95 (Ley 15.558, art. 35). El rango de k se arrastra al total.
- **Base de arancel y sellos = precio publicado.** Si k ≤ 1, el «mayor entre precio y valuación» es el precio. Si la tabla de un modelo supera el precio publicado, el arancel y los sellos reales son mayores. Esto se aclara en el detalle.
- Precio en ARS para comparar con los tramos: si el aviso está en pesos, se usa `price`; si está en USD, `price_usd × fx_rate`, con el mismo dólar blue del día que ya usa `price_usd`. El total se vuelve a pasar a USD con ese mismo tipo de cambio.

**Cómo se arrastran los rangos.** Cada término tiene un mínimo y un máximo. El total mínimo es la suma de los mínimos y el total máximo, la suma de los máximos, sin promediar. Se muestra «Costo total estimado: USD X – Y (ARS A – B)» y en el detalle va cada término con su rango, su fuente y la frase «parámetros al dd/mm».

**Ejemplo.** Precio ARS 20.000.000, venta entre particulares, modelo 2017 o posterior, sin gestor. VF entre 14.000.000 (k = 0,70) y 20.000.000 (k = 1,00). Gastos fijos entre ARS 8.000 y 23.200.

| Concepto | CABA | Buenos Aires | Resto (3 provincias) |
|---|---|---|---|
| Arancel DNRPA 1 % | 200.000 | 200.000 | 200.000 |
| Sellos | 600.000 (3 %) | 600.000 (3 %) | 200.000 – 600.000 (1–3 %) |
| Fijos | 8.000 – 23.200 | 8.000 – 23.200 | 8.000 – 23.200 |
| Patente anual | 380.950 – 698.693 | 140.000 – 340.000 | 119.000 – 460.000 |
| **Total** | **21.188.950 – 21.521.893** | **20.948.000 – 21.163.200** | **20.527.000 – 21.283.200** |
| Extra sobre el precio | 5,9 % – 7,6 % | 4,7 % – 5,8 % | 2,6 % – 6,4 % |

Cuentas de la patente:
- **CABA.** Con VF 14M: tramo 2, 119.350 + 4 % × 6.540.000 = 380.950, por factor Subte 1,00. Con VF 20M: tramo 3, 507.150 + 4,5 % × 2.845.000 = 635.175, por factor 1,10 = 698.693.
- **PBA.** Con VF 14M: 1 % = 140.000, por factor IPC 1,00. Con VF 20M: 233.000 + 3 % × 1.300.000 = 272.000, por factor 1,25 = 340.000.
- **Resto.** 0,85 % × 14M = 119.000 y 2,30 % × 20M = 460.000.

En los tres casos el extra queda **por debajo** del 8–10 % fijo actual.

---

## 2. Valores verificados por jurisdicción

Aplican a toda la tabla: vigencia al 30/10/2026; MRPA = Módulo de Registro de la Propiedad del Automotor (0,5 UVA); VF = valuación fiscal.

### 2.1 Nacional (igual en CABA, Buenos Aires y resto del país)

| Concepto | Valor | Base | Paga | Vigencia / norma | Fuente |
|---|---|---|---|---|---|
| Arancel de transferencia (2A) | **1 %** | Mayor entre la tabla DNRPA y el precio del 08. Si el modelo no figura: el valor del 08; si tampoco hay, el mínimo | Comprador (costumbre) | Desde 01/09/2026, Res. MJ 412/2026, Anexo I (BO 31/08/2026) | [Anexo IF-2026-75063842](https://www.cira.org.ar/wp-content/uploads/anexo_7754131_1.pdf) · [texto en argentina.gob.ar](https://www.argentina.gob.ar/normativa/nacional/norma-429419/texto) |
| Mínimo del arancel | 32 MRPA = **ARS 32.320 – 34.880** · RANGO | Monto fijo. Solo aplica si el 1 % del valor es menor (valor de menos de unos ARS 3,2 a 3,5 M) | Comprador | Res. MJ 412/2026 | ídem |
| Valor del MRPA | **ARS 1.010 – 1.090** · RANGO | 0,5 UVA del BCRA, redondeado hacia abajo a $10, actualización cada 4 meses | — | Res. MJ 308/2026, art. 1 (BO 07/07/2026). UVA de la API del BCRA, variable 31 | [Res. 308/2026](https://www.argentina.gob.ar/normativa/nacional/norma-427475/texto) · [BCRA](https://api.bcra.gob.ar/estadisticas/v4.0/monetarias/31) |
| Lo que incluye el arancel | ARS 0 adicional: 2 firmas, legajo, cédula, título, alta y baja impositiva | — | — | Res. MJ 412/2026, Anexo I, fila 2 | Anexo IF-2026-75063842 |
| Reducción por comerciante habitualista | **0,9 %** en lugar de 1 % | Solo si el vendedor inscribió el auto a su nombre (ST 08 o 17) y la transferencia se pide dentro de los 90 días | Comprador | Res. MJ 412/2026, Anexo I, nota de la fila 2 | ídem |
| Descuento por trámite digital | **0 %**: no existe para transferencias de usados | — | — | Res. 412/2026, Anexo V (solo 0,80 % para 0 km por RUV). El 40 % de la Res. 312/2018 quedó sin efecto | ídem |
| Recargo por mora en las firmas (7B) | 0 % si se presenta a tiempo; +20 % del arancel por año de demora, hasta +100 % | % del arancel | Comprador (en la práctica) | Res. MJ 412/2026, Anexo I, 7B | ídem |
| Firma adicional, desde la 3ª (8A) | 3 MRPA = ARS 3.030 – 3.270 por firma · RANGO | Fijo. Lo normal en una venta entre dos personas es 0 | Quien firma | Res. MJ 412/2026, 8A | ídem |
| Formulario 08 (contrato de transferencia) | **ARS 8.000** de lista. **Rango 8.000 – 9.600** · RANGO | Fijo | Comprador | Lista oficial del 19/01/2026 (IF-2026-06520679-APN-SSGA#MJ) | [Lista DNRPA](https://www.dnrpa.gov.ar/portal_dnrpa/guia_tramites/IF-2026-06520679-APN-SSGA_MJ.pdf) |
| Formulario 12 (verificación policial) | **ARS 7.700** de lista. **Rango 0 – 9.240** · RANGO | Fijo | Vendedor o se negocia | ídem | ídem |
| Informe de dominio (5A) | 4 MRPA = **ARS 4.040 – 4.360**. Rango por operación **0 – 4.360** · RANGO | Fijo. No es obligatorio, pero es lo usual antes de comprar | Comprador | Res. MJ 412/2026, 5A | Anexo IF-2026-75063842 |
| Tabla de valuación DNRPA | Valor por marca, modelo y año. Si existe el modelo pero falta el año: año anterior + 8 % | Base del 1 % | — | Disp. DNRPA 160/2026, vigente desde 01/08/2026 (BO 05/08/2026). Se renueva varias veces por año | [Disp. 160/2026](https://www.cira.org.ar/es/servicios/normativas-servicios/disposicion/disposicion-160-2026/) |

Por qué cada rango:
- **MRPA.** No hay publicación oficial del valor en pesos. El piso de $1.010 sale de la UVA del 03/07/2026. El techo de $1.090 es una proyección: si el período cuatrimestral empieza el 04/07, se actualiza el 04/11/2026 con una UVA estimada de unos 2.181.
- **Formularios 08 y 12.** El posible recargo de hasta 20 % de los Registros solo aparece en fuentes secundarias; no lo encontré en una norma vigente.
- **Formulario 12, piso 0.** La obligación de verificar y sus excepciones (familiares, autos muy viejos) no están confirmadas en una fuente oficial.
- **Informe de dominio.** Es opcional.

### 2.2 Sellos (sobre el precio publicado, por el supuesto k ≤ 1)

| Jurisdicción | Particular | Agencia | Base | Vigencia / norma | Fuente |
|---|---|---|---|---|---|
| **CABA** | **3 %** | **3 %**: la venta de agencia a consumidor final paga lo mismo (Res. 55/AGIP/26, art. 14). El 1,5 % es solo para la compra que hace la agencia | Mayor entre el precio del 08 y la tabla AGIP (Res. 55/AGIP/26, art. 9) | 2026. Ley 6927, Anexo, art. 32 (BOCBA 7269, 19/12/2025) | [Ley 6927](https://boletinoficial.buenosaires.gob.ar/normativaba/norma/829857) · [Res. 55/AGIP/26](https://boletinoficial.buenosaires.gob.ar/normativaba/norma/838971) |
| **Buenos Aires** | **3 %** (30 ‰) | **1 %** (10 ‰) solo con factura de agencia inscripta en IIBB y como habitualista. Como no sabemos si hay factura: **1 – 3 %** · RANGO | Precio o VF de ARBA. No se confirmó la regla del mayor (ver 3) | 2026. Ley 15.558, art. 39 A) 12 a) y b) (BO PBA 30.139, 15/12/2025) | [Ley Impositiva 2026](https://www.arba.gov.ar/archivos/Publicaciones/leyimpositiva2026.pdf) |
| **Resto** | **1 – 3 %** · RANGO | **0,5 – 3 %** · RANGO | Según provincia | 2026 | ver abajo |

Provincias revisadas para «resto», todas con fuente de 2026:
- **Córdoba:** 1,5 %, o 0,6 % si vende una agencia con inscripción preventiva F.17 ([Ley 11.090, art. 45](https://www.rentascordoba.gob.ar/cms/wp-content/uploads/2026/02/ley_n_11090_%E2%80%93_ley_impositiva_anual_2026.pdf)).
- **Santa Fe:** 1,2 %, con base no inferior a la tabla de API ([nomenclador API, ya con Ley 14.426](https://www.santafe.gob.ar/index.php/web/content/download/258548/1361139/file/NOMENCLADOR%20SELLOS%20Y%20TRS%202025.pdf)).
- **Mendoza:** 1 % entre particulares (alícuota general) y 0,5 % con factura de agencia registrada ([Ley 9680, art. 7](https://atm.mendoza.gov.ar/wp-content/uploads/2025/12/Ley-Impositiva-2026.pdf)). Base con piso en la tabla DNRPA (RG ATM 60/2021).
- **Tucumán:** 1 % ([tabla de Rentas, PDF del 05/02/2026](https://www.rentastucuman.gob.ar/nomina/rentastuc2/nwx1ut2pa3lo/agenda_impositiva/Alicuotas_Sellos.pdf)).

Por qué el rango del resto llega a 3 %: las cuatro provincias revisadas dan entre 1 % y 1,5 %, pero hay indicios no oficiales de provincias más caras (Salta 2,5 %, Chubut 2 %) y las otras 19 no se revisaron. El 3 % es el tope prudente, igual a CABA y PBA. En agencia, el piso es 0,5 % (Mendoza con factura) y el techo sigue siendo 3 %, porque sin factura rige la alícuota de particular.

### 2.3 Patente anual (sobre VF = precio × k, k entre 0,70 y 1,00)

**CABA.** Ley 6927, Anexo, art. 50 (2026) · [Anexo oficial](https://documentosboletinoficial.buenosaires.gob.ar/publico/PL-LEY-LCABA-LCBA-6927-25-ANX.pdf)

Inciso a): autos, rurales, 4x4 y motos. Escala progresiva:

| VF desde | VF hasta | Cuota fija | % sobre el excedente |
|---|---|---|---|
| 0 | 7.460.000 | 0 | 1,60 % |
| 7.460.000 | 17.155.000 | 119.350 | 4,00 % |
| 17.155.000 | 26.850.000 | 507.150 | 4,50 % |
| 26.850.000 | 36.550.000 | 943.500 | 5,50 % |
| 36.550.000 | 50.350.000 | 1.477.000 | 6,50 % |
| 50.350.000 | 73.100.000 | 2.374.000 | 7,00 % |
| 73.100.000 | — | 3.965.000 | 8,00 % |

- Tope: el impuesto no puede superar el 6 % de la VF (solo inciso a). Mínimo anual: ARS 13.300.
- Inciso b), camionetas y pick-ups: **2,30 %** plano. Las rurales y 4x4 van al inciso a).
- Inciso f), +10 % para el Fondo Subte: **factor 1,00 – 1,10** · RANGO. No hay fuente oficial que diga si la boleta lo suma aparte. Se aplica después del tope.
- Base: Tabla AGIP 2026, con valores ACARA de octubre de 2025 (Res. AGIP 54/2026, [BO](https://boletinoficial.buenosaires.gob.ar/normativaba/norma/838803)).
- Ley 6942 (BOCBA 7352, 23/04/2026): en 2026 la suba frente a 2025 no puede superar el IPCBA 2025, que fue **31,8 %** según [IDECBA](https://www.estadisticaciudad.gob.ar/eyc/wp-content/uploads/2026/02/ir_2026_2012.pdf). Depende de la patente 2025 de ese dominio, que no conocemos. Por eso la escala se usa como **cota superior**: el monto real puede ser menor y el mínimo del rango no lo contempla.

**Buenos Aires.** Ley 15.558, arts. 33, 34, 35, 37 y 167 (BO PBA 30.139, 15/12/2025) · [normas.gba.gob.ar](https://normas.gba.gob.ar/ar-b/ley/2025/15558/554025)

Inciso A): autos y rurales modelo 2016 a 2026. Los modelos 1990 a 2015 que tienen VF usan la misma escala y los cobra el municipio (art. 34). Las pick-ups y camionetas no afectadas a una actividad usan la misma escala.

| VF desde | VF hasta | Cuota fija | % sobre el excedente |
|---|---|---|---|
| 0 | 14.100.000 | 0 | 1,00 % |
| 14.100.000 | 18.700.000 | 141.000 | 2,00 % |
| 18.700.000 | 26.100.000 | 233.000 | 3,00 % |
| 26.100.000 | 53.900.000 | 455.000 | 4,00 % |
| 53.900.000 | — | 1.567.000 | 4,50 % |

- Base: ACARA × 0,95 (art. 35).
- Ajuste por IPC de cada cuota (art. 167): **factor 1,00 – 1,25** · RANGO PROVISORIO. ARBA puede bonificar hasta el 100 % del ajuste, y no encontré el coeficiente oficial de noviembre y diciembre de 2026. El 1,25 es una estimación del verificador con IPC de prensa; hay que reemplazarlo por el valor que publique ARBA.
- Bonificaciones del 10 al 35 % (art. 37): **no se aplican** (0 %), por criterio conservador. Se pueden mostrar como ahorro posible.
- Modelos anteriores a 1990: sin dato. **No se calcula** la patente.

**Resto del país.** Rango armado con Córdoba, Santa Fe y Mendoza; no se revisaron otras provincias, y la interfaz tiene que decirlo.

- **Mínimo:** 0,85 % de la VF para modelos 2017 en adelante (primer tramo de Córdoba; Santa Fe y Mendoza cobran más). Para **modelos 2016 y anteriores, 0**, porque Córdoba los exime: los 2008 y anteriores siempre, y los 2009 a 2016 si su VF es menor a $19,4 M ([Ley 11.090, arts. 55–57](https://www.rentascordoba.gob.ar/cms/wp-content/uploads/2026/02/ley_n_11090_%E2%80%93_ley_impositiva_anual_2026.pdf)).
- **Máximo:** 2,30 % de la VF hasta $59,1 M (Santa Fe, autos de hasta 5 años; [LIA art. 55](https://www.santafe.gov.ar/index.php/web/content/download/135407/669723/file/LIA%2007%20Patente%20%C3%9Anica%20sobre%20Veh%C3%ADculos%20(Art.%2055%20a%2058).pdf)), 2,50 % de $59,1 M a $87,5 M y 3,00 % de más de $87,5 M (Mendoza G y H, [Ley 9680, art. 9](https://atm.mendoza.gov.ar/wp-content/uploads/2025/12/Ley-Impositiva-2026.pdf)).
- Los mínimos fijos (Córdoba $11.500, Santa Fe 1.000 MT = $13.000) solo suben el piso; para el rango no hacen falta.

---

## 3. Lo que no se pudo confirmar

Sin números inventados. Cada punto dice cómo entra al cálculo.

1. **Valor oficial del MRPA en pesos.** No se publica. Entra como rango de $1.010 a $1.090, calculado con la UVA del BCRA.
2. **Valuaciones por modelo** (DNRPA, AGIP, ARBA, provincias). Solo se consultan por dominio. Entran con el supuesto propio k = 0,70 – 1,00. El verificador sugiere anclar el piso a un índice oficial (IPSA de SIOMAA o IPC del INDEC para compra de vehículos).
3. **Base de sellos en PBA y Córdoba**: si es el precio o el mayor entre precio y valuación. No encontré el artículo oficial. Con k ≤ 1 no cambia el cálculo.
4. **Recargo de hasta 20 % sobre los formularios.** No aparece en una norma vigente. Entra como techo de rango. Puede haber una lista de precios posterior al 19/01/2026.
5. **Obligación y excepciones de la verificación policial (F.12) y tasa de la planta verificadora.** No hay arancel oficial en CABA, PBA ni en otras provincias. El F.12 entra con piso 0. La tasa de la planta **no entra**: no hay número.
6. **Formulario 13 (informe impositivo).** No figura en la lista oficial vigente. No entra.
7. **Gestoría.** No hay tabla oficial: los honorarios se pactan libremente. El único número publicado (ARS 54.184, «mínimo sugerido» de una asociación privada, nota de iProfesional del 28/09/2024) **no es oficial y es de 2024**. No entra al total.
8. **Sellos del resto del país.** Solo se revisaron 4 de 23 provincias. Por eso el techo prudente de 3 %. Salta (2,5 %) y Chubut (2 %) son indicios no oficiales.
9. **Sellos de Tucumán.** La tabla de Rentas no cita la ley impositiva ni la base.
10. **Santa Fe.** El módulo tributario puede ser mayor a $13 si lo subió el Ejecutivo, y la prensa menciona topes de aumento interanual en la Ley 14.426 que no se leyeron. La escala queda como cota superior.
11. **CABA.** No se verificó la exención por antigüedad (la prensa habla de 25 años; art. 433 del Código Fiscal sin leer). Tampoco se confirmó si el +10 % Subte se suma en la boleta: entra como factor 1,00 – 1,10.
12. **Córdoba.** Rentas puede reescalar los tramos mes a mes (art. 55 inc. 4). Los tramos nominales pueden haber cambiado al 30/10/2026.
13. **PBA.** Falta el coeficiente IPC de las cuotas de noviembre y diciembre de 2026, el porcentaje de la RN ARBA 8/2026 y el tratamiento de los modelos anteriores a 1990.
14. **Escalas 2027.** No están publicadas ni revisadas. Un auto comprado en noviembre de 2026 paga casi todo su primer año con valores 2027.
15. **Quién paga.** Ninguna norma reparte los costos entre comprador y vendedor. Lo indicado en las tablas es costumbre de mercado.
16. **Ítems descartados por la verificación.**
    - Ficha DNRPA de sellos de PBA: de 2022, decía 1,2 % para agencias, desactualizado.
    - Rango de sellos del resto de 1 a 1,5 %: era corto.
    - Rango del MRPA de 1.010 a 1.040: no contemplaba la actualización de noviembre.
    - Fijo de $9.100 de Santa Fe: prevalece el mínimo de $13.000.
    - Piso de 0,75 para k.
    - Exención de Córdoba mal descripta.
    - Fecha de publicación de la Ley 15.558: es el 15/12/2025, no el 29/12/2025.
    - Cita de la Disp. DNRPA 152/2020 sobre mandatarios: mal atribuida.

---

## 4. Propuesta de `app_config.cost_estimator`

Los porcentajes van en %, los montos en ARS, y los rangos como `{min, max}`. Si un valor es exacto, `min = max`.

```json
{
  "as_of": "2026-10-30",
  "status": "propuesta",
  "fx": {"note": "Montos en ARS. Se pasan a USD con el fx_rate del blue del día, el mismo que usa price_usd."},
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
    "form_08": {
      "min": 8000, "max": 9600,
      "source": "IF-2026-06520679-APN-SSGA#MJ (https://www.dnrpa.gov.ar/portal_dnrpa/guia_tramites/IF-2026-06520679-APN-SSGA_MJ.pdf); max = +20 % no verificado en norma",
      "as_of": "2026-01-19"
    },
    "form_12": {
      "min": 0, "max": 9240,
      "source": "IF-2026-06520679-APN-SSGA#MJ (lista 7.700); min 0 por excepciones no confirmadas; max = +20 % no verificado",
      "as_of": "2026-01-19"
    },
    "domain_report_mrpa": {
      "min": 0, "max": 4,
      "source": "Res. MJ 412/2026, Anexo I, arancel 5A; opcional",
      "as_of": "2026-09-01"
    }
  },
  "stamp_tax_pct": {
    "caba": {
      "private": {"min": 3.0, "max": 3.0},
      "dealer": {"min": 3.0, "max": 3.0},
      "source": "Ley 6927 Anexo art. 32 (https://boletinoficial.buenosaires.gob.ar/normativaba/norma/829857); Res. 55/AGIP/26 arts. 9 y 14",
      "as_of": "2026-01-01"
    },
    "ba": {
      "private": {"min": 3.0, "max": 3.0},
      "dealer": {"min": 1.0, "max": 3.0},
      "source": "Ley 15.558 art. 39 A) 12 a) y b) (https://www.arba.gov.ar/archivos/Publicaciones/leyimpositiva2026.pdf); el 1 % exige factura de agencia",
      "as_of": "2026-01-01"
    },
    "rest": {
      "private": {"min": 1.0, "max": 3.0},
      "dealer": {"min": 0.5, "max": 3.0},
      "source": "Córdoba Ley 11.090 art. 45; Santa Fe nomenclador API (Ley 14.426); Mendoza Ley 9680 art. 7; Tucumán tabla Rentas feb-2026. Techo 3 % prudente: 19 provincias sin revisar",
      "as_of": "2026-10-30"
    }
  },
  "patente": {
    "caba": {
      "brackets": [
        {"from": 0,        "fixed": 0,       "pct": 1.60},
        {"from": 7460000,  "fixed": 119350,  "pct": 4.00},
        {"from": 17155000, "fixed": 507150,  "pct": 4.50},
        {"from": 26850000, "fixed": 943500,  "pct": 5.50},
        {"from": 36550000, "fixed": 1477000, "pct": 6.50},
        {"from": 50350000, "fixed": 2374000, "pct": 7.00},
        {"from": 73100000, "fixed": 3965000, "pct": 8.00}
      ],
      "cap_pct_of_vf": 6.0,
      "min_ars": 13300,
      "pickup_flat_pct": 2.30,
      "subte_factor": {"min": 1.00, "max": 1.10},
      "note": "Factor Subte después del tope. La bonificación de la Ley 6942 (IPCBA 2025 = 31,8 %) puede bajar el monto y no se calcula",
      "source": "Ley 6927 Anexo art. 50 (https://documentosboletinoficial.buenosaires.gob.ar/publico/PL-LEY-LCABA-LCBA-6927-25-ANX.pdf); Ley 6942",
      "as_of": "2026-01-01"
    },
    "ba": {
      "brackets": [
        {"from": 0,        "fixed": 0,       "pct": 1.00},
        {"from": 14100000, "fixed": 141000,  "pct": 2.00},
        {"from": 18700000, "fixed": 233000,  "pct": 3.00},
        {"from": 26100000, "fixed": 455000,  "pct": 4.00},
        {"from": 53900000, "fixed": 1567000, "pct": 4.50}
      ],
      "ipc_factor": {"min": 1.00, "max": 1.25},
      "discount_pct": 0,
      "min_model_year": 1990,
      "note": "ipc_factor.max provisorio hasta que ARBA publique el coeficiente; modelos < 1990 sin cálculo",
      "source": "Ley 15.558 arts. 33, 34, 35, 37 y 167 (https://normas.gba.gob.ar/ar-b/ley/2025/15558/554025)",
      "as_of": "2026-01-01"
    },
    "rest": {
      "min_pct": 0.85,
      "min_pct_model_year_le_2016": 0,
      "max_pct_bands": [
        {"vf_upto": 59100000, "pct": 2.30},
        {"vf_upto": 87500000, "pct": 2.50},
        {"vf_upto": null,     "pct": 3.00}
      ],
      "note": "Solo Córdoba, Santa Fe y Mendoza revisadas",
      "source": "Córdoba Ley 11.090 arts. 55-57; Santa Fe LIA art. 55 y Ley 14.426; Mendoza Ley 9680 art. 9",
      "as_of": "2026-01-01"
    }
  },
  "gestoria": {
    "in_total": false,
    "official_value": null,
    "note": "Sin tabla oficial; honorarios libres. Se muestra como línea aparte",
    "source": "Sin norma que fije honorarios (Res. MJ 412/2026 y Digesto revisados)",
    "as_of": "2026-10-30"
  }
}
```

Uso de `dealer`: aplica cuando el aviso tiene `seller_type = 'dealer'` o es `dealer_inferred` (vendedor con 6 o más avisos activos en 30 días, decisión de F-02), y se muestra con el texto «posible agencia». Para un particular se usa `private`, y el arancel DNRPA queda fijo en 1 %.

---

## 5. Puntos para que Juan decida

1. **k = 0,70 – 1,00** como supuesto propio para estimar la VF desde el precio. ¿Se acepta, o se ancla a un índice oficial (IPSA de SIOMAA o IPC del INDEC)?
2. **Formularios con +20 % no verificado.** ¿Se lleva el techo (08 hasta 9.600, 12 hasta 9.240) o se usa solo el precio de lista (8.000 y 7.700, con piso 0 para el 12)?
3. **Informe de dominio** (0 a 4 MRPA): ¿dentro del total o como línea recomendada aparte?
4. **Gestoría:** fuera del total, con el texto «Gestor opcional: sin tarifa oficial, se pacta con el gestor». ¿Se muestra o no la referencia no oficial de 2024 (ARS 54.184)? La propuesta es no mostrarla.
5. **Techo de sellos del resto en 3 %**, por las 19 provincias sin revisar. ¿OK, o se revisan más provincias antes?
6. **Agencias.** Rango 0,9–1 % en el arancel y rango de sellos de agencia, con el texto «posible agencia» para `dealer_inferred`. Confirmar que lo mismo vale para `seller_type = 'dealer'` declarado.
7. **Patente de CABA para autos muy viejos** (exención no verificada): ¿mínimo 0 para modelos de 25 años o más (2001 o anteriores) hasta confirmar el art. 433 del Código Fiscal?
8. **«Patente anual»** con valores 2026 cuando casi todo el primer año del comprador cae en 2027: ¿se rotula «patente anual (valores 2026)»?
9. **PBA, factor IPC hasta 1,25 (provisorio):** ¿OK hasta que ARBA publique el coeficiente?
10. **Texto que reemplaza el 8–10 %:** «Costo total estimado: USD X – Y (ARS A – B)», con desplegable por concepto y «parámetros al dd/mm». Siempre «estimado»; nunca «precio real».
11. **Pick-ups en CABA** (2,30 % plano): ¿se mapean con `body_type`? Las rurales y 4x4 quedan en la escala.
12. **Actualización.** Hay que revisar la tabla DNRPA, el MRPA (cada 4 meses), el coeficiente de ARBA y las leyes impositivas 2027 (diciembre y enero). ¿Quién lo carga en `/admin/config` y cada cuánto?
13. **Plan:** según el backlog, PAR-01 es de Particular. Confirmar si también va en Pro.
