# Autocity, Car One y Grupo Randazzo

Implementación junto con las cinco [fuentes regionales](FUENTES_REGIONALES.md). Código publicado en `main` (`dc222f9`), migraciones aplicadas y worker reiniciado en producción el 6 de octubre de 2026.

## Operación

| ID | Catálogo oficial | Cadencia inicial |
|---|---|---|
| `autocity` | [Autocity](https://autocity.com.ar/catalogo/usados/) | 1 hora |
| `carone` | [Car One](https://carone.com.ar/comprar) | 1 hora |
| `gruporandazzo` | [Grupo Randazzo](https://www.gruporandazzo.com/usados/disponible?map=estado) | 1 hora |

Cada fuente comparte un target de inventario con todos los perfiles elegibles que la seleccionen. Las marcas y modelos de cada aviso se normalizan sin atribuirle los filtros de un usuario a todo el catálogo. Deduplicación, selección de fuentes, acceso, bootstrap silencioso y matching permanecen en el pipeline común.

Migración: `supabase/migrations/20261006144025_agency_sources.sql`. Inserción idempotente que preserva ajustes del operador; `supabase/seed.sql` incluye las mismas fuentes. La web obtiene su lista desde `sources.enabled`.

## Validación

Lecturas públicas del 6 de octubre de 2026:

| Fuente | Recorrido observado | Ficha pública conservada y reprocesada |
|---|---|---|
| Autocity | 220 avisos, 19 páginas completas. | Chery Fulwin `95281`: 2018, 76.800 km, ARS 13.900.000, 6 fotos. |
| Car One | 199 usados válidos, todos con precio, luego de recorrer 485 productos en stock en 10 páginas. | Ford Ka `62441`: 2021, 88.000 km, ARS 18.850.000, Tortuguitas; galería live de 10 URLs reprocesable. |
| Grupo Randazzo | Último recorrido: **190 usados disponibles**, todos con precio. Cinco rangos cubren 217 productos del filtro Disponible; 26 con Km=0 y una nueva reserva se excluyen. Primer snapshot: 191. | Sandero Stepway `AE074XF_8091`: 2020, 132.476 km, ARS 20.000.000; galería live de 45 URLs reprocesable y reserva de ARS 400.000 ignorada. Otro ejemplo: Hilux `AH251JH_8339`, 2025, 39.674 km, ARS 43.800.000. |

Car One consulta el GraphQL público que utiliza su web y retiene sólo la etiqueta `2`, “Usados garantizados”, con stock disponible. Excluye etiquetas de 0 km y planes. El precio se toma de `final_price`; no del importe sin impuestos.

Autocity utiliza el ID de publicación de WordPress y el shortlink oficial `/?p=ID`. Verifica el ID de la ficha después de la redirección y conserva el ID solicitado en el HTML guardado para su reprocesado. Las tres agencias activan `STRICT_DETAIL_ID`: enriquecimiento/reprocesado comprueban fuente e ID antes de reemplazar la identidad almacenada o ejecutar el análisis/persistencia; una discrepancia se registra sin actualizar el aviso ni declararlo de baja.

Randazzo utiliza las especificaciones públicas de la unidad: la propiedad `Precio` es el precio del auto; el importe del comercio electrónico es la reserva y no se utiliza. Se excluyen reservados, “a ingresar” y unidades de 0 km, aunque la web las ubique en la categoría Usados. Sólo ingresa el estado Disponible. La búsqueda usa el REST público VTEX publicado por la web (`/api/catalog_system/pub/products/search`), categoría Usados 40 y la faceta Estado descubierta desde `/api/catalog_system/pub/facets/category/40`. Comprueba `Resources`, rangos, IDs, total y especificaciones de cada respuesta 200/206. La página pública aporta la moneda y la ficha sigue leyendo su propio estado SSR.

El REST filtrado pasó el último recorrido completo en 16,7 segundos, sin credenciales: `0-49/217`, `50-99/217`, `100-149/217`, `150-199/217`, `200-249/217` (17 registros finales). El índice conservó `AG587QG_5781`, cuyo estado propio cambió a Reservado: se cuenta su ID para verificar cobertura, se excluye de la salida y se registra una advertencia. No se incorpora como disponible por el filtro del índice. Categoría/estado faltante o desconocido y una página entera sin estado Disponible fallan visiblemente, al igual que rango, contador o IDs inválidos.

Los recorridos verifican el contador y los IDs de todas las páginas. Un cambio de stock durante la paginación, una página repetida, un límite alcanzado o un fallo intermedio falla el ciclo completo. Cada salto HTTP se valida antes de seguirlo; una ficha con estado ausente o desconocido falla visiblemente en lugar de declarar una baja.

Suite offline final: **592 passed, 21 skipped, 124 deselected**. Suite específica de agencias: **34 passed**, más las diez pruebas offline de registro/targets/transporte/identidad en integración. PostgreSQL: **16 passed, 10 deselected** en la base local dedicada `automotive_sources_20261006_test`, sin datos del entorno original: targets únicos para distintos modelos/selección de fuentes, migración idempotente que respeta ajustes previos, discrepancia de identidad que no modifica datos y cuatro casos de enriquecimiento legacy. Revisión de cumplimiento y calidad aprobadas; última adaptación REST revisada con contrato de rango/filtro, transporte y fixtures reales. HTML original/reducido reprocesable en 200/404/410.

El fallo legacy de Telegram documentado en [FUENTES_REGIONALES.md](FUENTES_REGIONALES.md) se reprodujo en el baseline anterior y queda fuera de este cambio. No se afirma haber aprobado toda la suite DB. `git diff --check` pasó y `graphify update .` terminó mediante AST, sin LLM: 4.570 nodos, 11.151 relaciones y 278 comunidades. Las etiquetas de comunidades se derivan de sus nodos centrales; no se ejecutó reconstrucción semántica.

Las pruebas públicas no realizan ingesta ni envían notificaciones. Las cantidades observadas son avisos leídos en un snapshot, no autos adicionales únicos ni stock sincronizado.

Los campos no publicados se mantienen desconocidos: estas fichas de Autocity y Randazzo no ubican la unidad; Car One no aporta descripción para el Ka. No se completa ubicación con la dirección global del grupo ni texto con anuncios de otros vehículos.

Desde `worker/`, las fichas se prueban sin ingesta:

```powershell
python -m tools.scraper_cli detail 'https://autocity.com.ar/?p=95281'
python -m tools.scraper_cli detail https://carone.com.ar/comprar/usados/ford-ka-1-5-s-plus-4p-l18-1
python -m tools.scraper_cli detail https://www.gruporandazzo.com/ae074xf_8091-renault-sandero-stepway-ph2-1-6-zen----l19-2020/p
```

## Activación

Las dos migraciones se aplicaron el 6 de octubre en el entorno de producción configurado. La tarea supervisada `\\AutoMotive\\Worker` se reinició y las 13 fuentes habilitadas se verificaron bajo el rol `authenticated`. Se preservó el historial remoto de migraciones; ver [FUENTES_REGIONALES.md](FUENTES_REGIONALES.md).

Primer ciclo real observado a las 16:22:40 UTC: Autocity **220**, Car One **199**, Grupo Randazzo **188**, Mardel **311** y Rosario Garage **504** avisos guardados. Las cinco fuentes tuvieron ejecuciones `ok`, completaron el bootstrap de sus once targets y generaron **193 matches** en total. Los reservados que permanecían en el índice de Randazzo se excluyeron por su estado propio. Son registros por fuente; pueden representar autos publicados también en otras webs.

Only Cars, SC Clasificados y Santa Fe tuvieron timeouts de navegación en la primera carga simultánea. El diagnóstico reprodujo ocho cargas síncronas de certificados para ocho solicitudes HTTP, con inicializaciones individuales de 0,7 a 2,4 segundos. Se agregó `worker/http_clients.py`: los clientes conservan sesiones independientes y reutilizan un contexto TLS verificado según `SSL_CERT_FILE`/`SSL_CERT_DIR` o el bundle habitual de certifi. La carga se sincroniza entre los threads del worker y los collectors; `trust_env=False` conserva su comportamiento. La prueba regresiva falla antes del cambio (8 cargas frente a 1) y pasa después. Otras pruebas comprueban verificación de hostname, `CERT_REQUIRED`, cookies separadas, certificados configurados y carga única entre ocho threads.

Validación del ajuste: **597 passed, 21 skipped, 124 deselected** sin DB. Medición de ocho inicializaciones: 1,7474 segundos la primera, y **0,0043 segundos** entre las siete siguientes. Los transports de catálogos/fichas y geocoding usan la misma fábrica. `graphify update .` terminó mediante AST: 4.600 nodos, 11.201 relaciones, 283 comunidades. Corrección publicada y desplegada mediante `4a2da6a`.

### Resultado observado en producción

Consulta a las **16:27:24 UTC del 6 de octubre de 2026**:

| Fuente | Avisos persistidos | Matches | Última ejecución |
|---|---:|---:|---|
| Only Cars Usados | 4 | 1 | `4956`, `ok` |
| SC Clasificados | 10 | 1 | `4955`, `ok` |
| Mardel Usados | 311 | 1 | `4925`, `ok` |
| Rosario Garage | 504 | 180 | `4937`, `ok`; siete targets completados |
| Usados Santa Fe | 33 | 1 | `4960`, `ok` |
| Autocity | 220 | 7 | `4929`, `ok` |
| Car One | 199 | 1 | `4930`, `ok` |
| Grupo Randazzo | 188 | 4 | `4931`, `ok` |
| Total | **1.469** | **196** | Ocho fuentes con `consecutive_failures=0` |

Los perfiles de Instagram completaron su reintento antes del segundo reinicio. Santa Fe completó la ejecución con el worker actualizado en 18 segundos. El heartbeat final identifica PID `41192`, inicio `16:26:52 UTC`, checkout principal, tarea supervisada activa y base remota configurada. Los catorce targets nuevos completaron el bootstrap. Próximas ejecuciones registradas: fuentes web aproximadamente una hora después de su ciclo; Instagram, dos horas después. La ingesta, el matching y el enriquecimiento posterior se observaron en las tablas reales; los totales cambian con el stock y pueden incluir el mismo auto en distintas fuentes.
