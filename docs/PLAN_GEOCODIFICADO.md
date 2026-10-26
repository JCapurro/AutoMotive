# Plan: más publicaciones con geocodificado (y lectura de descripciones con IA)

Medido en producción el 2026-10-26, sobre 11.937 avisos activos.

## 1. Punto de partida

**2.253 avisos activos (19 %) no tienen coordenadas.** Con un radio en la búsqueda, el matching los deja pasar como "desconocido" (`worker/intelligence/matching.py:251`). Por eso llegan avisos lejanos a quien busca en Córdoba, Paraná o el interior.

| Fuente | Sin coordenadas | Causa |
|---|---|---|
| rosariogarage | 1.305 de 1.948 | 1.297 sin `location_text`; el texto que sí viene es "Ciudad, est.xxx, Provincia" |
| facebook | 491 de 1.164 | 373 "Ciudad de Buenos Aires, CF" guardados antes del fix PR #31; 85 "Recién publicado"; el resto trae el título en la ubicación |
| gruporandazzo | 274 de 274 | sin ubicación (concesionaria) |
| mercadolibre | 146 de 4.170 | "X - Buenos Aires Interior" y "X - Bs.As. Costa Atlántica" no se resuelven |
| autocosmos | 33 de 783 | "Barrio, Buenos Aires (A.M.B.A.)" (La Tablada, Wilde, Villa Ballester…) |
| otras | 5 | casos sueltos |

El resto de las fuentes (deruedas, autocity, kavak, carone, mardelusados, v6) tiene 100 %.

## 2. Plan por fases (de mayor a menor retorno)

### Fase 1 — Backfill de lo que ya se puede resolver (≈ 500 avisos, sin costo)
- Script único (`worker/tools/`, estilo `reprocess.py`) que toma avisos activos con `lat IS NULL AND location_text IS NOT NULL` y vuelve a pasar por `geocode_location`.
- Cubre los 373 de CABA (ya están en la tabla de ubicaciones conocidas desde PR #31) y los de autocosmos.
- Después, refrescar los matches de los avisos que cambiaron (`pipeline/rescore.py`), sin notificar (como backfill).
- Requiere OK para escribir en producción (transacción + verificación de conteos antes y después).

### Fase 2 — Limpiar el texto de ubicación antes de geocodificar (≈ 250 avisos)
- Normalizadores por fuente en `normalization/geo.py`:
  - Mercado Libre: quitar el sufijo " - Buenos Aires Interior" / " - Bs.As. Costa Atlántica" y buscar "Ciudad, Buenos Aires".
  - rosariogarage: tomar "Ciudad" y "Provincia" del formato "Ciudad ,est.xxx, Provincia".
  - autocosmos: quitar "(A.M.B.A.)".
- Descartar ubicaciones que no son lugares: "Recién publicado", títulos de aviso ("2017 Ford mondeo…"). Hay que dejar de guardarlas en `location_text`, para no marcar `location` como conocido en `scoring.py:157`.
- Ampliar la tabla de ubicaciones conocidas con las ciudades que más se repiten (Necochea, Chivilcoy, San Nicolás, Cañuelas, Tres Arroyos, Azul, Bragado…) para no depender de Nominatim. Tests en `worker/tests/test_location_radius.py`.

### Fase 3 — Fuentes sin ubicación (≈ 1.580 avisos)
- **rosariogarage (1.297) y gruporandazzo (274):** son concesionarias. La ubicación sale de la sede de la fuente, no del aviso. Agregar una ubicación por defecto por fuente (columna en `sources` o en config) y usarla cuando el aviso no trae ninguna. Es el cambio de mayor volumen.
- **Facebook "Recién publicado" y títulos:** re-leer la ficha del aviso (`fetch_detail`) para obtener la ubicación real; si no existe, dejar `NULL` en vez de guardar basura.

### Fase 4 — Que lo no resuelto no llegue a quien busca lejos
- Con radio y aviso sin ubicar: no mostrarlo (o mostrarlo aparte, como "sin ubicación confirmada"). Decisión de producto, hoy se muestra.
- Hacer que `rescore` use la misma regla para limpiar los matches existentes.

### Fase 5 — Para que no vuelva a pasar
- Métrica diaria: % de avisos activos con coordenadas por fuente, con alerta si baja de 95 % en una fuente.
- Registrar los `location_text` que fallan (ya existe el caché de fallas de geocodificado) y revisarlos semanalmente.

**Resultado esperado:** de 19 % sin coordenadas a menos de 3 %.

## 3. ¿Ya se lee la descripción con IA?

**Sí, ya está implementado y activo** (`worker/pipeline/enrich.py`, configuración `app_config.description_facts = {llm: true, llm_daily_cap: 50}`):
- Las reglas leen todas las descripciones. El LLM relee la descripción completa y guarda evidencia y declaraciones del vendedor en `description_facts`.
- Hay 463 lecturas exitosas y 1 error. 437 avisos activos tienen lectura de IA.
- Solo se enriquecen avisos que hicieron match con alguna búsqueda (la tarjeta del listado no trae descripción, hay que pedir la ficha).

**Dónde está el límite:**
- El tope de **50 lecturas por día** se está agotando: 50 en las últimas 24 h.
- Hay **2.696 avisos con descripción que nunca pasaron por el LLM**. Al ritmo actual serían unos 54 días.
- Faltan datos estructurados: sin transmisión 3.779 avisos (mercadolibre 1.495, deruedas 1.092, facebook 769), sin combustible 4.419, sin versión 2.310. Solo 1.293 de los avisos de mercadolibre tienen descripción, así que la IA no puede completar el resto: ahí falta traer la ficha.

**Recomendación:**
1. **Para geocodificado no hace falta IA.** Es un problema de limpieza de texto y de ubicación por fuente (Fases 1-3). Salvo para extraer la localidad de la descripción de avisos de Facebook sin ubicación, y eso es un caso marginal.
2. **Para completar datos del auto (transmisión, combustible, versión), sí conviene subir el tope**, pero primero priorizar:
   - avisos que ya hicieron match con una búsqueda activa;
   - avisos de fuentes con muchos vacíos (Facebook, Mercado Libre);
   - dejar el resto para después.
3. Antes de subir el tope, medir cuánto cuesta una lectura (tokens por aviso) y fijar un presupuesto mensual. Hoy no tengo ese número; hay que sacarlo de los logs del proveedor LLM. Cambiar el tope es solo un cambio en `app_config`, pero implica gasto: lo decide Juan.

## 4. Orden sugerido
1. Fase 1 (rápida, sin riesgo, gran efecto en Buenos Aires/CABA).
2. Fase 2 y ubicación por defecto de rosariogarage/gruporandazzo (Fase 3).
3. Decidir la regla de la Fase 4.
4. Subir gradualmente el tope de IA con prioridad por match, midiendo el costo.
5. Fase 5 como cierre.

Cada fase termina con la verificación en producción: avisos sin coordenadas por fuente y matches fuera de radio (la consulta de esta sesión sirve de base).
