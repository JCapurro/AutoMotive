# Admin de EseAuto: métricas y configuración

## Pantallas

- **Resumen:** seis indicadores del período, comparación anterior, devoluciones y pendientes actuales con enlaces para revisarlos.
- **Métricas / Activación:** altas, creación de búsqueda en 24 horas y primer resultado bueno en 24 horas, con sus denominadores.
- **Métricas / Ingresos:** pagos confirmados por fecha de pago, devoluciones por fecha de devolución, pases de Particular y mensualidades de Agencia/Pro. La diferencia entre cobros y devoluciones no representa ganancia.
- **Métricas / Operación:** salud actual de fuentes, estadísticas de procesamiento asistido y colas.
- **Diagnóstico:** conserva las tablas anteriores, sus propias ventanas y límites. No sigue el filtro del panel nuevo.

Los filtros de 7, 30 y 90 días usan días completos de Argentina. El día actual queda fuera y el período de comparación tiene igual duración. Fuentes y colas son fotos actuales; las estadísticas LLM conservan los días UTC de la vista existente y se identifican como tales.

## Definiciones y cobertura

Las cuentas admin quedan fuera de los agregados nuevos de usuarios, búsquedas e ingresos. Actividad exige una acción humana registrada, incluyendo pausar o reanudar una búsqueda; una entrega o una apertura de pixel no cuentan.

Activación en 24 horas usa cuentas creadas dentro del período, con al menos 24 horas de observación al cierre. Se cuenta la creación de búsqueda, aunque luego se elimine.

El primer resultado bueno requiere un hito persistente, capturado cuando un match entra por primera vez en `good` o `high`. Su fecha usa el momento real de esa operación; no se reconstruye a partir del nivel actual ni de la fecha original de un match reevaluado. Una degradación o eliminación posterior no borra el logro.

El seguimiento completo comienza al instalar la migración. Las búsquedas anteriores, sin observación completa, se muestran como excluidas del denominador; no se asignan éxitos ni fracasos históricos inventados. La mediana se calcula solo entre búsquedas observadas que alcanzaron el resultado dentro de 24 horas.

La creación y el primer logro sobreviven al borrado de una búsqueda. Al vincular cuentas, la observación sigue al dueño actual de la búsqueda. Borrar la cuenta elimina sus observaciones mediante la FK al perfil.

Los pendientes de búsquedas consultan los resultados actuales, no el logro histórico. El worker deshabilita búsquedas sin acceso comercial en su siguiente ciclo, por lo que puede existir un breve desfase entre vencimiento y esa foto.

Las mensualidades vigentes equivalentes se mantienen separadas de las suscripciones autorizadas. Campañas, gasto publicitario, infraestructura y costos de proveedores aún necesitan conexión o carga para medir rentabilidad. Las compras de vehículos del diagnóstico son autodeclaradas.

## Cambiar configuración

**Precios y oferta:** importes enteros en ARS y períodos de 30 días, conservando el contrato comercial actual. Cambiar un importe requiere cambiar la versión. El formulario muestra el alcance sobre nuevas confirmaciones y conserva campos desconocidos.

**Límites:** búsquedas, resultados, avisos diarios, zonas y funciones por plan. Los valores heredados se muestran como tales; un plan ausente no se completa silenciosamente al abrir el editor. La activación del piloto y la aplicación general de límites se administran desde Cobros.

**Emails:** activación general, tipos existentes, horario argentino, vigencia y tope diario. Los tipos desactivados por defecto no se habilitan al abrir el formulario. La vigencia debe superar el intervalo nocturno y admite hasta 720 horas. Editar contenido, duración de pruebas o reglas nuevas requiere desarrollo.

**Fuentes:** estado y frecuencia exacta en segundos, con rango de 60 a 86.400. No se interrumpe una ejecución que ya está corriendo.

Cada formulario muestra el cambio propuesto antes del guardado. La escritura y su auditoría ocurren en una transacción, con actor obtenido de la sesión y verificado como admin en SQL. Si otra persona cambió el valor, se exige recargar en lugar de sobrescribirlo. Restaurar una versión del historial prepara un borrador y vuelve a validar el guardado.

Las demás claves conservan su editor JSON avanzado. Agregar una clave no crea por sí solo un consumidor ni un comportamiento nuevo.

## Instalación y verificación

Migraciones requeridas:

1. `supabase/migrations/20261027145730_admin_decision_metrics.sql`
2. `supabase/migrations/20261027145911_admin_config_audit.sql`

La instalación no cambia precios, límites, envíos ni habilita cobros. Las funciones son `security invoker`, con acceso agregado y escritura administrativa restringidos a `service_role`. El registro de búsquedas usa RLS para permitir únicamente la creación de una observación propia que coincida con una búsqueda real; los usuarios no pueden cambiar su hito de valor.

El repositorio también contiene versiones de migración posteriores a estas fechas. Antes de publicar, revisar el historial remoto y aplicar las nuevas migraciones como pendientes anteriores cuando corresponda; no resetear la base ni volver a ejecutar migraciones existentes.

Validación automatizada:

```powershell
cd web
npm test
npm run typecheck
npm run lint
npm run build
```

Los tests SQL son `supabase/tests/admin_decision_metrics_test.sql` y `supabase/tests/admin_config_audit_test.sql`. Deben ejecutarse en una base local aislada; son transaccionales y terminan con rollback. Los errores de consultas se muestran como datos no disponibles y no como ceros. Si falta la RPC de métricas, la pantalla indica la migración necesaria.

### Evidencia de esta implementación (27/10/2026)

- Suite web completa: 556 pruebas aprobadas; tipos, lint y build de producción aprobados.
- Base dedicada `admin_decisions_20261027`: 62 pruebas de métricas y 36 de auditoría aprobadas, con rollback.
- Componentes reales renderizados con fixtures: seis vistas a 375 y 1280 píxeles, sin desborde horizontal de la página.
- Harness con React real: un borrador de fuente conserva su baseline ante un refresh externo; un guardado exitoso avanza el baseline para la siguiente edición.
- Revisión independiente: corregidos el primer valor retroactivo por reevaluación, la pérdida de historia al eliminar búsquedas, los límites heredados mal mostrados y la concurrencia de fuentes.
- La validación visual usa datos ficticios y stubs de transporte. No se verificó el recorrido autenticado completo contra un despliegue; no se aplicaron cambios a producción.
