# IA sobre descripciones

El worker usa el proveedor LLM ya configurado para leer títulos y descripciones completas durante el enriquecimiento. Guarda las afirmaciones del vendedor en `listings.description_facts` versión 2, con `claims`, `evidence`, `input_hash` y `llm_at`. Las reglas de precio y normalización siguen funcionando si el proveedor falla, no hay credenciales o se agota el presupuesto.

## Comportamiento

- Los valores ausentes siguen siendo desconocidos. Las citas deben existir en el aviso; se comprueban contexto de negaciones, montos, precios parciales y kilometraje de mantenimiento.
- Año, kilómetros, caja, combustible y versión pueden completar campos vacíos. Una descripción que contradice un campo estructurado conserva el campo y muestra la contradicción. La versión debe coincidir con el catálogo del modelo.
- La ficha muestra «Según el vendedor» con las citas y «Qué puede influir en el precio». Los factores son cualitativos: no ajustan la mediana, el score ni inventan un costo de reparación. La diferencia numérica sigue saliendo de los comparables.
- Las preguntas se adaptan a daños, mantenimiento, distribución, uso comercial, documentación y negociación. La aplicación prepara el texto; no contacta al vendedor.
- Una nueva descripción invalida las afirmaciones anteriores. Las tarjetas sin descripción conservan el detalle ya leído.

## Presupuesto y caché

`app_config.description_facts` mantiene `llm` y `llm_daily_cap` (valor existente: 50). `description_llm_runs` reserva atómicamente cada intento antes de la llamada; fuentes concurrentes, errores, reinicios y avisos borrados no eluden el límite de las últimas 24 horas. Se permite un intento por aviso + texto + versión en ese intervalo. El ledger no contiene textos, respuestas ni credenciales y no es accesible para `anon` o `authenticated`.

El caché válido requiere `source=llm`, `v=2` y la huella del título + descripción. Incluso una lectura sin datos nuevos se conserva para no volver a pagarla. Para cambiar el contrato/prompt de forma incompatible, aumentar `VERSION`.

## Activación y reproceso

1. Aplicar `supabase/migrations/20261014120000_description_intelligence.sql` antes de actualizar el worker. Si falta la tabla de presupuesto, el worker conserva las reglas y no llama al proveedor.
2. Publicar la web y actualizar/reiniciar el worker con la rama integrada. Reutiliza `LLM_PROVIDER` y sus credenciales existentes; no agregar claves en la web.
3. Revisar los avisos anteriores desde `worker/`:

```powershell
python -m tools.reprocess --facts --llm --dry-run --source v6
```

El dry-run no hace llamadas de IA ni reserva intentos. Muestra el resultado de reglas/caché; las nuevas interpretaciones de IA aparecen al aplicar:

```powershell
python -m tools.reprocess --facts --llm --source v6
```

Se respetan el caché y el presupuesto. Todas las publicaciones que cambian se vuelven a evaluar, incluso si su precio no cambió. El enriquecimiento normal sigue priorizando los avisos con coincidencias y precios parciales; esta funcionalidad no implica analizar todo el catálogo inmediatamente.

## Verificación

Las pruebas usan respuestas simuladas, sin llamadas pagas. La integración se verifica contra `automotive_description_test`, una copia local sin datos de usuarios, con la migración nueva. Los resultados de contrato y simulación no verifican la calidad de un modelo en publicaciones reales ni constituyen evidencia de despliegue en producción.
