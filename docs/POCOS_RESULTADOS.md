# Bot de pocos resultados

Detecta las búsquedas que traen pocos resultados y le explica a la persona por qué, con un LLM.

## Cuándo se activa

El worker corre `pipeline/low_results.py` cada `LOW_RESULTS_TICK_SECONDS` (1 h). Diagnostica una búsqueda que:

- está habilitada, con acceso vigente, preparada (bootstrapped, sin rematch pendiente) y es por modelo;
- tiene `min_age_hours` (24) o más;
- muestra `max_results` (3) resultados o menos, sin importar el nivel: avisos activos no descartados.

Se rehace si cambian los filtros (fingerprint) o pasados `recheck_days` (7). Si la búsqueda supera el umbral, el diagnóstico se borra.

## Qué hace

1. Toma el mercado del modelo: publicaciones activas de los últimos 30 días, todas las fuentes.
2. Lo pasa por los filtros duros del matching (`intelligence/low_results.py`): por filtro, cuántas descarta (`fails`) y cuántas descarta él solo (`only`, lo que sumaría aflojarlo); además años, precios, km y fuentes.
3. El LLM (`explain_low_results`, prompt `llm/prompts/explain_low_results.md`) escribe la explicación y hasta 3 sugerencias. Si falla, se usa un texto fijo con los mismos números.
4. Se guarda en `search_diagnoses` y se avisa una vez por juego de filtros por los canales de la búsqueda (Telegram, email). La web lo muestra en `/app/searches/<id>` como «¿Por qué hay pocos resultados?»; la persona puede ocultarlo.

## Configuración

`app_config.low_results`: `enabled`, `max_results`, `min_age_hours`, `recheck_days`, `max_per_tick`, `notify`.
