# Ese Auto · implementación del lanzamiento comercial

Fecha: 2/10/2026. Autorizado por el usuario: nuevo nombre y ruta B del backlog comercial.

Identidad visual elegida: **S Auto** en el logo y el ícono; **eseauto.com.ar** como nombre del sitio y dominio previsto. Ese Auto se conserva en los textos y la comunicación. El cambio de logo no registra ni configura el dominio: al publicar, configurar `SITE_URL=https://eseauto.com.ar`, `WEB_BASE_URL` y las redirecciones de Auth junto con hosting/DNS.

**Objetivo:** publicar Ese Auto y hacer efectivos Free (una búsqueda por 72 horas), Particular (ARS 15.000 / 30 días / 3 búsquedas) y Agencia (ARS 75.000 / 30 días con renovación manual / 10 búsquedas) en el piloto asistido PIL-01.

**Arquitectura:** conservar los identificadores internos `free`, `pass`, `pro`, las cuentas individuales y los motores existentes. La base determina acceso y capacidad; el worker vuelve a comprobarlos al consultar demanda, guardar coincidencias y enviar avisos. Los pagos verificados administrativamente registran referencia única, oferta e importe comprado, período y responsable. Autoservicio y renovación automática corresponden a la etapa posterior condicionada a pagos y recompra del backlog.

**Tecnologías:** Next.js 16, Supabase/PostgreSQL, worker Python, Vitest y pruebas PostgreSQL existentes.

- [x] Marca: nombre público, logo, metadatos, emails de acceso/notificación y textos del producto.
- [x] Oferta: dos planes pagos en ARS, prueba de 3 días, capacidades, condiciones, entrada particular/agencia y estados de acceso.
- [x] Base: inicio de prueba protegido, límite atómico de búsquedas activas, vencimiento exacto y vista de resultados limitada en servidor.
- [x] Worker: excluir acceso vencido de crawl, rematch, rescore, favoritos y preparación/despacho de alertas.
- [x] Piloto: registrar pagos, renovación manual, devoluciones verificadas y autogestión de intención de renovación, sin cobro automático.
- [x] Administración: habilitación explícita para cuentas existentes, períodos de prueba nuevos desde la habilitación y métricas de ingresos/pases separadas.
- [x] Verificación: SQL aislado y concurrencia, worker, oferta web, tipos, lint, build y recorrido de planes en móvil/escritorio.
- [x] Documentación: actualizar backlog y dejar instrucciones de migración/habilitación y tareas comerciales externas pendientes.

Para cuentas existentes, la habilitación inicia 72 horas nuevas desde el servidor en aquellas con búsquedas activas y sin prueba iniciada. Mantiene la búsqueda más antigua dentro de la capacidad; conserva las demás pausadas. La migración conserva el interruptor de límites del piloto; el administrador revisa la cuenta de usuarios y habilita el lanzamiento desde Cobros. No se infiere el inicio desde el registro ni se habilitan pagos reales por migrar el esquema.

## Habilitación del entorno destino

1. Aplicar `supabase/migrations/20261007120000_ese_auto_commercial.sql` antes de ejecutar la nueva versión del worker. Publicar web/worker y la plantilla de email de acceso. La migración conserva `plan_limits.enforced` y deja `commercial_pilot.enabled=false`; no inicia pruebas retroactivas por fecha de registro.
2. Confirmar en Config la oferta ARS 15.000/75.000, versión y capacidades 1/3/10. Configurar el email público de soporte, remitente de notificaciones y enlaces externos del proveedor. El dominio y usuario de Telegram actuales se conservan hasta configurar sus reemplazos; el nombre visible ya dice Ese Auto.
3. Revisar cuentas en **Administración → Cobros** y comunicar el inicio de la prueba. Usar **Habilitar prueba de 3 días y límites**, que inicia 72 horas para cuentas gratuitas activas sin prueba anterior y pausa las búsquedas excedentes. Repetir la operación no reinicia pruebas. Una prueba consumida sigue consumida al vincular Telegram.
4. El usuario elige Particular o Agencia en Planes. La solicitud aparece en Cobros. El administrador verifica el pago en el proveedor y registra cuenta, plan, referencia, fecha y responsable. Guardar habilita el período; no procesa ningún cargo. Agencia puede renovarse antes de vencer y extiende 30 días desde el fin vigente.
5. Revisar el registro de pagos y conciliar con el proveedor diariamente. Registrar una devolución total solo después de verificarla allí; si hay períodos prepagados, devolver primero el más nuevo. **Ajustes → No voy a renovar** registra intención; no acorta el período pagado. Al vencer, las búsquedas se pausan y conservan historial y favoritos; tras un pago, el usuario reanuda las que desea.

## Límites de esta entrega

No se publicó ni se habilitó el entorno de producción. No hay checkout, débitos automáticos, equipos, pase de 90 días ni mensajes a vendedores. Estos trabajos quedan condicionados en el backlog. Los planes definen acceso al monitoreo y avisos; el límite de 50 resultados se aplica en la vista/RPC normal y no convierte publicaciones compartidas en información secreta. La administración puede mantener concesiones históricas de acceso sin vencimiento.

## Comprobaciones reproducibles

Las pruebas PostgreSQL solo deben ejecutarse con `TEST_DATABASE_URL` en una base local separada cuyo nombre termine en `_test`; nunca contra la base de la aplicación. Se utilizó `ese_auto_release_test`, con esquema y referencias copiados, sin datos de usuarios de la aplicación.

- `worker/`: `python -m pytest tests/test_commercial_postgres.py -q`: inicio único, capacidad concurrente, permisos, precio histórico, pagos repetidos, renovación/devolución, vencimiento, entrega tardía, frecuencia Free, rollout, vinculación Telegram, límite de resultados y trabajos asistidos.
- `worker/`: pruebas existentes de base, notificaciones, inteligencia e ingesta; adaptaciones de snapshots únicamente para el nuevo nombre.
- `web/`: `npm run typecheck`, `npm test`, `npm run lint`, `npm run build`.
- Vista de la landing a 390 y 1280 px con precios ARS y sin desborde, errores de navegador ni enlaces de plan que pierdan la elección. Capturas en `design/ese-auto-comercial-390.png` y `design/ese-auto-comercial-1280.png`.

Los enlaces de pago, comprobantes, observación de cobertura, envío de correos reales y activación de la primera cohorte requieren operación del entorno destino y figuran pendientes en el backlog.

Resultado local: 9 pruebas comerciales aprobadas y 71 regresiones de base, notificaciones, inteligencia e ingesta verificadas entre la corrida principal y la comprobación de la medición del piloto. También se verificaron los canales y las plantillas con el nuevo nombre. Web: 44 pruebas, tipos, lint y build aprobados. El grafo de código se actualizó sin llamadas a modelos. No equivale a un cobro real ni a validación de producción.

Verificación previa a integrar en main: suite completa del worker sobre la base aislada, **420 aprobadas y 21 omitidas**; web, **44 aprobadas**, lint y compilación aprobados. Se actualizaron las expectativas de los recorridos de navegador para la nueva marca, landing y Particular de 30 días. No se ejecutó la suite e2e autenticada contra la base de la aplicación: esa base aún requiere la migración comercial; la verificación de accesos y pagos sí corrió en la base aislada.
