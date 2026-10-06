# Fuentes regionales de publicaciones

Código publicado en `main` mediante `dc222f9`. Migraciones aplicadas y worker supervisado reiniciado en producción el 6 de octubre de 2026.

## Fuentes agregadas

| ID | Origen | Recorrido | Cadencia inicial |
|---|---|---|---|
| `mardelusados` | [Mardel Usados](https://mardelusados.com/) | Catálogo público completo de autos/camionetas/utilitarios. ID `VH-…` independiente del slug. | 1 hora |
| `rosariogarage` | [Rosario Garage](https://www.rosariogarage.com/Autos) | Finder público filtrado por marca/modelo, en Autos, Camionetas y Utilitarios. Paginación por offsets reales, máximo 20 páginas por categoría. | 1 hora por target |
| `usadossantafe` | [Autos](https://usadossantafe.com.ar/autos) y [Camionetas](https://usadossantafe.com.ar/camionetas) | Datos Next.js públicos; usa el botón “Cargar más avisos” cuando existe. No consulta APIs privadas ni credenciales Firebase. | 1 hora |
| `onlycarsusados` | [@onlycarsusados](https://www.instagram.com/onlycarsusados/) | Feed reciente del perfil, con verificación del autor y shortcode de cada publicación. | 2 horas |
| `sc_clasificados` | [@sc_clasificados](https://www.instagram.com/sc_clasificados/) | Mismo lector de Instagram; captions, fotos y fecha del post propio. | 2 horas |

La migración y el seed insertan las cinco fuentes habilitadas porque los probes públicos de catálogo/feed y ficha fueron válidos. `ON CONFLICT DO NOTHING` conserva cualquier configuración ya ajustada por el operador. La web carga las fuentes habilitadas desde la base, por lo que no necesita una lista nueva en el frontend.

Mardel, Santa Fe y los perfiles Instagram comparten un target de inventario por fuente. No se asigna la marca/modelo de una búsqueda a todo el catálogo: cada aviso pasa por la normalización habitual y después se compara con cada perfil elegible. Se mantienen selección de fuentes, acceso vigente, deduplicación, bootstrap silencioso y alertas existentes.

## Evidencia pública — 6 de octubre de 2026

| Fuente | Prueba observada | Ficha y reprocesado |
|---|---|---|
| Mardel | Último recorrido: **306 avisos**, 305 con precio y 306 con ubicación. Un snapshot anterior dio 307; el catálogo cambia. | Punto `VH-0576`: 2012, 93.000 km, USD 8.000, 6 fotos; parser sobre HTML original/reducido idéntico. |
| Rosario Garage | **18 Fiesta** usados en la prueba con año 2018 y hasta 150.000 km, en las tres categorías. | `5645199`: 2018, 102.000 km, ARS 17.700.000, particular, Rosario/Santa Fe, 10 fotos. |
| Santa Fe | **56 avisos**, 53 con precio y 56 con ubicación, luego de cargar el catálogo adicional y combinar categorías. | Agile `260922-0841-48K68`: 2012, 140.000 km, ARS 11.000.000, 8 fotos; HTML reducido reprocesable. |
| Only Cars | Revalidación antes de publicar: sin sesión, límite habitual de 24 posts y **6 avisos válidos**, 5 con precio, en 46,3 segundos. Pins vendidos y contenido no vehicular excluidos. El feed público visible puede contener menos posts que el límite. | Honda Civic Hatchback `DeKDPcKETBd`: 1993, 30.000 km, USD 12.500, 11 fotos y 702 caracteres de caption; HTML original/reducido idéntico. Prueba anterior: Peugeot 208, 2021, 31.300 km, USD 13.200. |
| SC Clasificados | Sin sesión: **6 avisos válidos entre 6 posts**. | RAV4: 2010, 210.000 km, USD 11.800, Villa María, 20 fotos; caption completo y reprocesado idéntico. |

Estos números son **avisos leídos**, no publicaciones únicas adicionales ni ingesta observada en producción. La deduplicación entre fuentes sucede después. Las pruebas en vivo no escribieron en la base ni enviaron notificaciones.

La revalidación de Only Cars usó el mismo `aio.run` y `run_collector` que separan los loops de PostgreSQL y Playwright en Windows. Pasaron nuevamente las **45 pruebas de Instagram**. La consulta de operación fue de solo lectura: el entorno remoto configurado en el checkout principal tenía heartbeat reciente (33 segundos), pero todavía no tenía la fila `onlycarsusados` en `sources` ni ejecuciones de esa fuente en `collector_runs`. La tarea programada del worker apunta a ese checkout principal. La lectura pública valida el collector; su activación en producción requiere migración y reinicio después de publicar el código.

## Límites y errores

- Instagram recorre hasta `INSTAGRAM_MAX_POSTS=24` publicaciones recientes por ciclo, con máximo 60 y seis desplazamientos. No recupera todo el historial. Acceso anónimo comprobado hoy; si cambia, el collector registra un bloqueo o error.
- Las publicaciones explícitamente vendidas se excluyen. Falta de autor, identidad, caption completo o markup reconocido no se interpreta como una baja.
- Precio de consulta/placeholder `1` queda desconocido. Moneda y otros campos se conservan solo cuando hay evidencia. No se toma el precio tachado ni un anticipo como precio total.
- Los fallos HTTP o de páginas intermedias en Rosario fallan el ciclo. Repetición de página con más resultados también falla. El límite de 20 páginas deja una advertencia en logs si quedan resultados.
- Santa Fe requiere Chromium/Playwright para la carga adicional. Si el botón no termina, falla el ciclo en lugar de declarar completo el catálogo inicial.
- Las búsquedas con fuentes específicas conservan su selección. Las que abarcan todas las fuentes incorporan las nuevas después de habilitarlas.

## Probar y activar

Activación realizada en el proyecto configurado `dnqyravczgcpuowijbja`: ambas migraciones de fuentes constan en `supabase_migrations.schema_migrations` y las ocho fuentes nuevas están habilitadas. Se conservó la migración histórica remota `20261005042219_admin_search_access`, ausente del repositorio: su SQL se recuperó en un directorio temporal de despliegue para que la CLI verificara el historial. El dry-run incluyó exclusivamente `20261006141335_regional_sources.sql` y `20261006144025_agency_sources.sql`; se aplicaron con la CLI 2.119.0, `--include-all` y `--skip-vault`, sin seed ni roles.

La tarea `\\AutoMotive\\Worker` se reinició y mantiene el supervisor habitual de `ops/run-forever.ps1`. El nuevo heartbeat identifica PID `33152`, inicio `2026-10-06T16:04:18Z`, checkout principal y entorno de producción. La lectura bajo el rol `authenticated` confirmó las 13 fuentes habilitadas que utiliza el formulario de búsquedas. El primer ciclo creó los siete targets compartidos de inventario y siete targets por vehículo para Rosario Garage, e inició ejecuciones reales de las ocho fuentes. La evidencia del resultado se registra en [FUENTES_AGENCIAS.md](FUENTES_AGENCIAS.md).

1. Publicar el código del worker y aplicar la migración generada `supabase/migrations/20261006141335_regional_sources.sql` en el entorno elegido; verificar el orden de migraciones existentes, que en este repositorio incluye versiones con fechas futuras. No activar en una máquina que todavía carezca de los collectors.
2. Reiniciar el worker con su entorno habitual. Revisar `sources`, los nuevos `crawl_targets`, `collector_runs` y `/admin/sources`; confirmar ingesta y matches antes de afirmar que producción quedó conectada.
3. Las fichas se pueden probar sin ingesta con la CLI, desde `worker/`:

```powershell
python -m tools.scraper_cli detail https://mardelusados.com/vehiculo/fiat-punto-2012-vh-0576/
python -m tools.scraper_cli detail "https://www.rosariogarage.com/index.php?action=carro/showProduct&itmId=5645199&rbrId=107"
python -m tools.scraper_cli detail https://usadossantafe.com.ar/aviso/260922-0841-48K68
python -m tools.scraper_cli detail https://www.instagram.com/onlycarsusados/p/DeISPZ4jh7c/
python -m tools.scraper_cli detail https://www.instagram.com/sc_clasificados/p/Ddtw2eVlgWL/
```

Para una URL Instagram genérica `/p/…` sin nombre de cuenta, indicar `--source onlycarsusados` o `--source sc_clasificados`. La búsqueda de la CLI abre el pool habitual para el filtro geográfico; la modalidad `detail` no realiza ingesta.

Si Instagram empieza a exigir autenticación, crear la sesión local de forma manual:

```powershell
python -m tools.instagram_login
```

El usuario inicia sesión en el navegador que abre el comando y confirma su guardado en la terminal. Configurar `INSTAGRAM_STORAGE_STATE=ig_state.json` en `.env`; el archivo queda ignorado por Git. No se creó ni reutilizó una sesión privada durante esta implementación.

## Validación de código

- Baseline: 52 tests de parsers/normalización.
- Suite sin DB: **548 passed, 21 skipped, 120 deselected**.
- Nuevos parsers/transporte: fixtures reales recortados y casos reconstruidos etiquetados; identidad, precios, vendido, bloqueos y reprocesado.
- Integración PostgreSQL: **9 passed** en base local dedicada `automotive_sources_20261006_test`, con esquema actualizado y sin datos de usuarios del entorno original. Verificados target único para dos modelos, matches por perfil, acceso, selección de fuentes y migración idempotente.
- `git diff --check` válido; `graphify update .` terminó mediante AST sin LLM (4.443 nodos, 10.775 relaciones). Las etiquetas semánticas de comunidades quedan sustituidas por nombres derivados de sus nodos centrales, tal como informa la herramienta.
- Un test legacy de Telegram (`test_a_price_drop_of_a_matched_listing_alerts_through_the_crawl`) falla por ausencia de mensaje tanto en esta rama como en un archivo limpio de `dba6da5`, con el mismo esquema de prueba. No se modificó ese flujo para esta incorporación.

La ampliación con Autocity, Car One y Grupo Randazzo está documentada en [FUENTES_AGENCIAS.md](FUENTES_AGENCIAS.md). Los otros candidatos siguen en [AGENCIAS_USADOS_2026-10-06.md](research/AGENCIAS_USADOS_2026-10-06.md).
