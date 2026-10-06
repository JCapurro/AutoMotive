# Description Intelligence Implementation Plan

> **For agentic workers:** Execute this approved plan task by task in the isolated worktree. Review failures and evidence before reporting completion.

**Goal:** Usar descripciones para completar información, contextualizar el precio y preparar preguntas con evidencia.

**Architecture:** ListingFacts produce valores y citas; normalización comprueba que las citas existan y conserva los datos en description_facts JSONB. El worker limita/cachea lecturas; inteligencia y web consumen los datos sin llamadas adicionales al proveedor.

**Tech Stack:** Python, Pydantic, Postgres JSONB, Next.js server components, Vitest y pytest.

## Task 1: Contrato y conservación

- [x] Extender worker/llm/schemas.py y prompts/extract_listing_facts.md con campos nullable y evidence [{field, quote}].
- [x] Crear pruebas de extracción con citas válidas e inexistentes, ausencia, negaciones y round-trip JSON.
- [x] Extender DescriptionFacts y from_llm en worker/normalization/description_facts.py. Comprobar citas contra título + descripción; conservar false explícitos y rechazar texto inventado.
- [x] Completar versión solo si está ausente y coincide con una versión del catálogo; conservar motor y equipamiento en los datos extraídos.
- [x] Ejecutar: python -m pytest tests/test_description_facts.py tests/test_description_intelligence.py tests/test_normalization_v2.py -q (cwd worker).

## Task 2: Análisis de todas las descripciones y caché

- [x] Probar una descripción sin precios ambiguos, texto cambiado, versión antigua, concurrencia del límite y error de proveedor.
- [x] Extender DescriptionLLM.refine con huella de título + descripción y versión; un lock transaccional de Postgres protege el presupuesto compartido y cuenta intentos fallidos.
- [x] Revisar tools/reprocess.py para admitir reproceso de descripciones ya leídas y dry-run sin llamadas al proveedor.
- [x] Ejecutar: python -m pytest tests/test_description_intelligence.py tests/test_ingest_postgres.py -q (Postgres usa solo TEST_DATABASE_URL con guard).

## Task 3: Señales y preguntas

- [x] Integrar hechos con evidencia en worker/intelligence/red_flags.py y seller_questions.py.
- [x] Preguntar por alcance/costo de daños, comprobantes de mantenimiento, documentación, uso comercial y negociación cuando corresponda. Evitar afirmar condiciones no verificadas.
- [x] Ejecutar: python -m pytest tests/test_intelligence.py tests/test_description_intelligence.py -q.

## Task 4: Ficha y explicación

- [x] Crear web/lib/description.ts con lectura defensiva de JSON y lista de afirmaciones y factores.
- [x] Crear web/components/app/description-insights.tsx como server component con citas y aviso de origen.
- [x] Integrar en web/app/app/listings/[id]/page.tsx junto a la comparación de precio y mostrar la evidencia de campos completados.
- [x] Probar salida con pocos comparables, daños negados, contradicciones y JSON anterior.
- [x] Ejecutar npm test, npm run typecheck y npm run lint (cwd web).

## Task 5: Verificación y entrega

- [x] Ejecutar suite worker sin producción y revisar diff completo.
- [x] Actualizar docs de operación y marcar tareas completadas con resultados reales.
- [x] Ejecutar graphify update . y verificar que solo se incluyan cambios propios.
- [x] Crear commit en codex/description-intelligence y entregar estado de implementación, pruebas y límites de activación.

## Resultados de verificación

- Worker: 459 pruebas unitarias pasaron; 21 pruebas opcionales se omitieron. Las regresiones nuevas se ejecutaron después con 178, 52 y 45 casos enfocados, todos verdes.
- Postgres: 44 casos del flujo de ingestión/análisis pasaron; la revisión final de extracción, normalización y Postgres pasó 52 casos en la base separada automotive_description_test.
- Web: 115 pruebas pasaron, incluyendo renderizado real de los componentes con ReactDOM y las citas. TypeScript y ESLint pasaron. Se usaron los CLI de node_modules directamente porque los shims .bin no están presentes en las dependencias locales.
- Graphify: actualización AST, sin llamadas de IA. No se ejecutaron llamadas pagas ni migraciones/reprocesos sobre producción.
- Activación pendiente: integrar/publicar la rama, aplicar la migración y actualizar el worker; el reproceso de avisos anteriores es explícito y está documentado.
