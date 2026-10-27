# Admin de EseAuto: decisiones y configuración

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Track the steps below during implementation.

**Goal:** Implementar la primera etapa aprobada: Resumen, Activación, Ingresos y Operación, con formularios de planes, emails y fuentes.

**Architecture:** Next.js mantiene las rutas existentes y usa agregaciones SQL solo accesibles por service_role después de requireAdmin. Los períodos son 7/30/90 días completos de Argentina, comparados con el período inmediatamente anterior. Los formularios modifican configuraciones ya consumidas y registran cambios atómicos con control de concurrencia.

**Tech Stack:** Next.js 16, React 19, TypeScript, Zod, Supabase/PostgreSQL, Vitest, pgTAP y Playwright.

## Alcance y definiciones

- Resumen: actividad real, cuentas nuevas, activación en 24 h, primer resultado bueno en 24 h, cobros y atención operativa.
- Métricas: vistas Activación, Ingresos y Operación; conservar tablas históricas como Diagnóstico.
- Sin campañas o costos inventados: indicar qué conexiones faltan. Compras de autos siguen siendo autodeclaradas.
- Contar usuarios no admin en las agregaciones nuevas; actividad exige acciones humanas, no recibir un email.
- Activación: cuentas creadas en el período que crearon una búsqueda dentro de 24 h. Denominador: cuentas con 24 h de observación al cierre del período.
- Primer valor: búsquedas creadas en el período con match good/high dentro de 24 h; mostrar también denominador y búsquedas sin ese resultado. Mediana solo entre búsquedas que lo lograron, identificada como tal.
- Ingresos por fecha de pago, devoluciones por fecha de devolución. Particular y mensualidades de Agencia separados. Mensualidades vigentes no se llaman MRR autorizado.
- Cada bloque muestra los errores de lectura; nunca convertir un error en un cero.
- Configuración: formularios para pro_offer, plan_limits y lifecycle_emails, JSON avanzado para las demás claves. Preservar campos desconocidos. Validar las mismas reglas en servidor.
- Guardado de configuración y fuentes: exigir valor anterior para detectar cambios concurrentes y registrar actor, antes/después y fecha en la misma transacción. Restaurar una versión vuelve a pasar por validación y control de concurrencia.
- No aplicar migraciones a producción ni habilitar cobros. Preparar cambios revisables y verificar en entorno local aislado.

## Task 1: contrato y períodos

Files: web/lib/admin-dashboard.ts, web/lib/admin-dashboard.test.ts.

- [x] Probar los límites de medianoche argentina, rangos consecutivos, parámetro inválido, cero denominador y comparación con base cero.
- [x] Implementar rangos semiabiertos y tipos del snapshot compartidos por SQL, carga y UI.

## Task 2: agregados confiables

Files: nueva migración admin_decision_metrics, supabase/tests/admin_decision_metrics_test.sql, web/lib/admin-dashboard-data.ts, web/types/database.ts (solo firma RPC).

- [x] Escribir casos SQL con usuarios admin/no admin, límites temporales, búsquedas sin resultados y pagos/devoluciones en períodos diferentes.
- [x] Crear RPC security invoker, search_path fijo, permiso de ejecución solo service_role y rango máximo de 90 días.
- [x] Agregar series diarias completas y estado operativo actual sin truncar filas en cliente.
- [x] Cargar snapshot, salud de fuentes y LLM con errores separados y validación de respuesta.

## Task 3: páginas para decisiones

Files: web/app/admin/page.tsx, web/app/admin/metrics/page.tsx, web/app/admin/metrics/diagnostic/page.tsx, web/components/admin/dashboard-*.tsx.

- [x] Filtro por 7/30/90 días, comparación y fecha de actualización visibles; tabs por propósito.
- [x] Tarjetas con base/definición y tendencias simples; listas de atención con enlaces concretos.
- [x] Estados de error, vacío y datos disponibles. Mantener criterios de validación y acceso al detalle histórico.
- [x] Verificar móvil sin desborde y controles con etiquetas accesibles.

## Task 4: configuración guiada y trazable

Files: web/lib/admin-config.ts, sus tests, web/app/admin/actions.ts, web/app/admin/config/page.tsx, web/components/admin/config-editor.tsx, nuevos formularios y migración de auditoría.

- [x] Probar límites, enteros, horarios, oferta ARS/30 días, versión de oferta, preservación de campos y modificaciones concurrentes.
- [x] Formulario de oferta, tabla de límites y horario/tipos/topes de emails; resumen antes de guardar.
- [x] Validar servidor, guardar y auditar atómicamente; historial legible y restauración validada.
- [x] Fuentes: mantener frecuencia/pausa con efecto explicado y registro auditado.

## Task 5: integración y verificación

- [x] Ejecutar Vitest completo, typecheck y lint.
- [x] Aplicar migraciones y pgTAP en base local dedicada; verificar permisos anon/authenticated/service_role.
- [x] Verificar en navegador los componentes reales con fixtures de Resumen, las tres vistas, Config y error a 1280 px y 375 px; probar concurrencia con React real. Validar escrituras reales por separado con acciones y pgTAP. El recorrido autenticado completo queda como verificación de despliegue.
- [x] Revisión independiente de requisitos y seguridad/correctitud; corregir hallazgos.
- [x] Ejecutar graphify update . y dejar documentación de alcance, comandos y límites de verificación.


## Resultado verificado

556 pruebas web, 62 pruebas SQL de métricas y 36 de auditoría aprobadas; typecheck, lint y build aprobados. Revisión visual de componentes reales con fixtures y prueba de concurrencia con React real. Producción sin modificar.

graphify update . terminó sin LLM: 8.666 nodos, 23.130 relaciones y 405 comunidades. Emitió aviso de 54 fuentes sin nodos AST (entre ellas ARCHIVOS.json y PROMPTS.json); las comunidades nuevas usan nombres de sus hubs. No se ejecutó etiquetado semántico ni se solicitaron claves API.
