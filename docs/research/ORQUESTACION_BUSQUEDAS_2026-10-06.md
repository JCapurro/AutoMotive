# Orquestación de búsquedas de AutoMotive

Fecha: 2026-10-06. Investigación de documentación oficial; propuesta de diseño, sin benchmark ni cambios de código o infraestructura.

## Recomendación

Separar búsqueda interactiva, adquisición de publicaciones, matching y notificaciones. La web debe consultar un catálogo compartido indexado; las alertas expresan demanda y filtros. El planificador debe crear unidades de adquisición por fuente + modelo + cobertura geográfica, con cobertura base y frecuencia adaptada a demanda, novedades y presupuesto de cada fuente. Una búsqueda sin cobertura debe devolver lo disponible y mostrar que se está actualizando, mientras un único trabajo compartido completa la cobertura.

Cambiar el orquestador por sí solo no reduce búsquedas redundantes ni los límites de los portales. Esta recomendación es una decisión de arquitectura para el proyecto, no una propiedad garantizada por los productos investigados.

## Opciones

| Opción | Qué aporta | Coste o límite | Uso propuesto |
| --- | --- | --- | --- |
| Cola en PostgreSQL | Reserva concurrente de trabajos mediante `FOR UPDATE SKIP LOCKED`; puede coordinar estado y cambios del catálogo en transacciones de la misma base | Hay que implementar leases, recuperación, reintentos, limpieza y métricas; comparte recursos con consultas del producto | Primer paso incremental si la capacidad disponible de la base lo permite |
| Celery + Redis | Framework Python de tareas y distribución; Redis figura como broker estable y permite monitorización/control de workers | Otro servicio operativo; persistencia y memoria requieren configuración; hay que cuidar el visibility timeout | Alternativa si ya se opera Redis o al justificar la migración con métricas |
| Celery + RabbitMQ | Framework de tareas más broker con acknowledgements de consumo y confirmaciones de publicación | Otro servicio y su configuración de fiabilidad; duplicados siguen siendo posibles | Evolución para aislar el transporte y aprovechar herramientas del broker |
| Dagster | Assets, jobs, schedules, sensors y control de concurrencia por ejecución/pools | No determina la granularidad de adquisición ni resuelve por sí mismo la búsqueda web y el matching | Complemento para pipelines, backfills, controles de calidad y operación |

PostgreSQL documenta explícitamente `SKIP LOCKED` para varios consumidores de una tabla con comportamiento de cola. Advierte que la vista resultante es inconsistente: sirve para repartir trabajos, no para las consultas del catálogo. [SELECT](https://www.postgresql.org/docs/current/sql-select.html).

Los bloqueos de filas terminan al finalizar la transacción. Por eso la propuesta es reservar y guardar `lease_token`, `lease_until`, `attempts` y `available_at` en una transacción corta; después hacer el scraping fuera de ella. Renovar el lease con heartbeat; recuperar leases vencidos; completar únicamente si el token sigue vigente para evitar que un worker antiguo cierre un intento nuevo. Esa lógica es responsabilidad de la aplicación, no una funcionalidad automática de `SKIP LOCKED`. [Explicit locking](https://www.postgresql.org/docs/current/explicit-locking.html).

Celery proporciona reintentos y acknowledgement tardío (`acks_late`), pero necesita tareas idempotentes y una política explícita para excepciones y pérdida del worker. Su rate limit es por worker, por lo que multiplicar workers también puede multiplicar solicitudes al portal: hace falta coordinación global por fuente. [Tasks](https://docs.celeryq.dev/en/stable/userguide/tasks.html).

Redis y RabbitMQ constan como brokers estables. Redis admite broker y almacén de resultados, aunque persistencia/memoria deben decidirse; PostgreSQL puede seguir guardando el estado de negocio. No se extrae una conclusión de rendimiento comparado de esta tabla documental. [Backends and brokers](https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/index.html).

En Redis, las tareas sin acknowledgement pueden volver a entregarse al vencer el visibility timeout; tareas largas y ETA/countdown superiores al timeout pueden repetirse. La documentación desaconseja usar el broker como calendario lejano. Mantener `next_due_at` persistente y enviar trabajo cuando vence evita acumular todo el futuro en el broker. [Redis caveats](https://docs.celeryq.dev/en/stable/getting-started/backends-and-brokers/redis.html).

RabbitMQ distingue confirmación del productor y acknowledgement del consumidor; ambas participan en una entrega fiable. La retransmisión puede duplicar mensajes: se necesita idempotencia en persistencia, matching y notificaciones. [Reliability guide](https://www.rabbitmq.com/docs/reliability).

Celery no soporta oficialmente Windows desde 4.x. Adoptarlo para el worker local requiere planear un entorno Linux, por ejemplo contenedor o host dedicado. [Celery FAQ](https://docs.celeryq.dev/en/stable/faq.html#does-celery-support-windows).

Dagster permite límites de ejecuciones y pools entre ejecuciones para proteger recursos compartidos. Es una opción de operación de pipelines, pero no equivale a definir la cola del producto ni garantiza menos scraping. [Managing concurrency](https://dagster.io/docs/guides/operate/managing-concurrency).

## Secuencia incremental y criterios de decisión

1. Definir los trabajos compartidos por cobertura y desacoplar scrape, matching y envío; priorizar lo nuevo y reintentar etapas sin volver a adquirir la publicación.
2. Agregar cola durable con reserva atómica, lease recuperable, reintentos con espera creciente y variación aleatoria, límite de intentos y estados finales inspectables. Mantener un presupuesto global por portal.
3. Hacer idempotentes las escrituras y el encolado entre etapas; si una transacción cambia el catálogo, registrar también el evento pendiente para evitar perder matching después de una caída. Para envíos externos conservar deduplicación y evidencia del proveedor: una cola no garantiza exactamente una entrega externa.
4. Medir edad del trabajo más antiguo por fuente/etapa, tiempo hasta publicación visible, anuncios nuevos por solicitud, errores/bloqueos, duración de trabajos y coste de base. Separar latencia de búsqueda web de frescura del catálogo.
5. Migrar transporte a un broker dedicado cuando la cola afecte las consultas de negocio o se necesiten operación y aislamiento que compensen otro servicio. Mantener el contrato de trabajo permite hacerlo sin rediseñar catálogo o alertas.

No se fija cantidad soportada de usuarios, throughput o latencia garantizada: requiere medir el código desplegado, tamaño del catálogo, consultas y cuotas reales de fuentes.
