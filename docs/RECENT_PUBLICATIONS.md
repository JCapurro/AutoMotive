# Plan e implementación: publicaciones recientes

## Objetivo

Buscar oportunidades nuevas en Mercado Libre y Facebook Marketplace. La primera
ejecución de cada combinación de fuente, marca y modelo carga los últimos **30
días**. Las siguientes buscan publicaciones del día, conservando la deduplicación
y el bootstrap silencioso existentes.

## Plan implementado

1. Calcular una ventana por target, compartida por todas las búsquedas de ese
   vehículo. Primera ejecución: 30 días. Luego: hoy en Argentina para Mercado
   Libre y últimas 24 horas para Facebook.
2. Aplicar filtros de la plataforma y comprobar localmente la fecha de cada
   publicación. Usar la fecha de la tarjeta o la guardada; si falta, abrir la
   ficha. Excluir fechas desconocidas; la primera detección no demuestra que el
   aviso sea nuevo. Excepción: lo que Mercado Libre lista en «Publicados hoy»
   se toma tal como viene (ver más abajo).
3. Recorrer la paginación de Mercado Libre y los lotes cargados al hacer scroll
   en Facebook. Leer cada lote antes del siguiente scroll, porque Facebook puede
   retirar tarjetas anteriores del DOM.
4. Ingerir resultados verificados incluso si el recorrido queda incompleto.
   Registrar el error y reintentar sin avanzar el checkpoint ni dar por terminado
   el bootstrap. Mantener silencioso todo el backfill inicial.
5. Verificar ventanas, cambio de día, recuperación, filtros, paginación,
   deduplicación y fallos con pruebas automáticas. Completar la validación en vivo
   en la máquina del worker: Mercado Libre se lee sin sesión; Facebook usa la suya.

## Ventanas y recuperación

| Situación | Mercado Libre | Facebook |
| --- | --- | --- |
| Primera ejecución | Últimos 30 días, comprobados por fecha | `daysSinceListed=30`, comprobado por fecha |
| Ejecución normal | «Publicados hoy»: una sola página, sin abrir fichas | `daysSinceListed=1` y últimas 24 horas comprobadas |
| Interrupción o cambio de día | Ampliar hasta el inicio del último recorrido completo; hasta 25 horas alcanza «Publicados hoy» | Usar el bucket 1, 7 o 30 que cubra la recuperación |
| Solo cuenta para el mail 2.5 (`count_only`) | «Publicados hoy», también en su primera ejecución | `daysSinceListed=1`, también en su primera ejecución |
| Fecha desconocida | Excluir y contar en logs, salvo en «Publicados hoy» | Excluir y contar en logs |

La recuperación agrega 10 minutos de solapamiento y tiene un máximo de 30 días.
El ID de la fuente evita duplicados. `last_run_at` conserva el inicio del último
scan completo; `next_run_at` se programa desde su finalización.

Facebook solicita orden por creación con `sortBy=creation_time_descend`, también
en búsquedas por texto; sus sugerencias igualmente pasan por la comprobación local.

No se corta al encontrar el primer aviso viejo: pueden aparecer resultados
patrocinados o sugeridos fuera del orden solicitado. Facebook termina después de
tres lecturas consecutivas sin IDs nuevos; esto es una heurística de agotamiento
del feed y requiere comprobación en vivo.

### Mercado Libre y «Publicados hoy»

Desde el 14/10/2026 Mercado Libre se lee por HTTP en el host público
`autos.mercadolibre.com.ar`, sin sesión. Ahí no hay orden por más recientes,
que pide cuenta, ni un filtro nativo de 30 días. Sí está «Publicados hoy», que
se arma con el sufijo `_PublishedToday_YES`.

- **Abarca las últimas 24 horas, no el día calendario.** Se comprobó el
  15/10/2026 a las 00:19: el filtro seguía listando 19 de los 26 Toyota Etios
  que había mostrado a las 18:54 del día anterior, 13 de 16 Suran y 10 de 13
  Golf.
- **Cuándo se usa.** Cuando la ventana dura hasta 25 horas (`_recency.TODAY_SPAN`)
  y en los objetivos que solo cuentan para el mail 2.5 (`count_only`). Así
  cubre también la ejecución que cruza la medianoche. La hora extra absorbe el
  solapamiento y las demoras del scheduler. Una interrupción de entre 24 y 25
  horas puede perder lo publicado en ese margen.
- **Banda de años de referencia** (TECHNICAL_PLAN.md 5.1). Solo estas lecturas
  de una pasada (`_recency.one_request_read`, la misma regla que decide
  «Publicados hoy») leen un año más de cada lado de las búsquedas, para los
  comparables. La primera ejecución y la recuperación usan los años exactos de
  las búsquedas: fechan cada aviso abriendo su ficha. Facebook nunca lee la banda.
- **Sin abrir fichas.** Sus resultados se guardan sin abrir cada ficha, porque
  la ficha pública solo dice «hace 1 día», sin fecha exacta, y el filtro ya
  garantiza que el aviso es reciente. Si no hay fecha guardada, la primera
  detección hace de fecha de publicación, y los recorridos frecuentes la
  mantienen cerca.
- **Ventanas largas.** Una ventana más larga (primera ejecución, recuperación)
  se recorre entera, en orden de relevancia. Cada aviso se fecha con la
  publicación guardada, con una fecha ya leída por el proceso o con su ficha,
  hasta `RECENT_ML_MAX_DATE_FETCHES` fichas por ejecución.

### Facebook: fichas, memoria de fechas y cola

Las tarjetas de Facebook no muestran la edad del aviso (la cuenta del VPS está
en inglés), así que cada aviso sin fecha conocida abre su ficha, 30 s después
de la anterior (`RECENT_FB_DETAIL_SECONDS`).

- **Tope por escaneo.** `RECENT_FB_MAX_DATE_FETCHES=12` fichas (~7 minutos).
  Al llegarlo, el escaneo queda incompleto con lo que guardó y se reintenta a
  los 180 s (`crawl.retry_seconds`). Un reinicio del worker tira a lo sumo ese
  escaneo, y un target en régimen espera como mucho uno.
- **Fechas conocidas por marca.** Antes de abrir una ficha se buscan las
  fechas guardadas de la misma marca vistas en los últimos 35 días
  (`targets.publication_dates`). Una búsqueda por texto trae modelos de nombre
  más largo (Gol → Gol Trend y Golf, Corolla → Corolla Cross), y 35 días cubren
  la ventana más ancha.
- **Memoria de fechas por target**, en `crawl_targets.prefilter_rejected` (un
  target de Facebook por modelo no usa esa columna para otra cosa,
  ver CARROCERIA.md):
  - `"id"`: la ficha fechó el aviso antes de la ventana. Mientras rige la
    política, el comienzo de la ventana nunca retrocede (`target_window`), así
    que ese aviso no entra nunca: su ficha no se vuelve a abrir.
  - `"id@epoch#n"`: la ficha cargó sin fecha, `n` veces, la primera en
    `epoch`. Se vuelve a leer a los 30 minutos, a las 2 horas y a las 6 horas
    de `epoch`, y después de esos 3 intentos se saltea. Si alguna lectura lo
    fecha, entra si se publicó hasta 24 horas antes de `epoch` (la ventana en
    la que se lo vio), aunque hoy quede antes del comienzo de la ventana. Un
    aviso que quedó sin fecha durante un bootstrap y se fecha recién después,
    con más de un día, no entra: en régimen se notificaría como nuevo. Esta
    parte va detrás de `FB_DATE_MEMORY_UNKNOWN`, apagada: en las 48 horas al
    22/10/2026 solo 15 fichas cargaron sin fecha en escaneos completos.
  - Una lectura que falló por excepción no se memoriza: se reintenta en el
    escaneo siguiente.
  - Un escaneo completo conserva solo los avisos que vio; uno incompleto
    conserva también los demás. Un cambio de `publication_policy` vacía la
    memoria (`sync_targets`), porque la ventana vuelve a 30 días.
- **Cola.** Dentro de cada fuente (`targets.claim_next`) va primero un target
  que nunca corrió, después los vencidos en régimen y al final los reintentos
  de bootstrap y los `count_only`, cada grupo por vencimiento. Un bootstrap
  largo ya no deja sin turno a los modelos en régimen.
- **Logs.** Cada escaneo deja `facebook publication window: ... dates_read
  skipped out_of_window undated unknown_dates ...`, y la línea `target=...`
  del worker agrega `probe={...}`. `undated` son las fichas que cargaron sin
  fecha; `unknown_dates` suma además las tarjetas que el tope dejó sin leer.
- **Sonda del feed (fase 2 pendiente).** Sin pedidos extra, el escaneo mira si
  los datos de la página de búsqueda (el JSON del HTML inicial y las
  respuestas `/api/graphql/` del scroll) traen un tiempo de creación por
  aviso, y lo compara con el `creation_time` de las fichas que leyó en ese
  mismo escaneo. Solo registra nombres de campo y conteos, nunca valores ni
  volcados. Con cobertura y coincidencia de al menos 95 % sobre 100 o más
  comparaciones, la fase 2 fecharía desde el feed. Si no, la alternativa es un
  bootstrap sin fecha detrás de un flag apagado: cambia esta política y
  necesita aprobación antes de implementarse.

## Activación y ritmo

No requiere migración de esquema. `publication_policy=1` en la consulta del target
reinicia una sola vez el bootstrap de los targets existentes de estas dos
fuentes. Los IDs y matches ya guardados se conservan. Los cambios ordinarios de
filtros y las reactivaciones posteriores no vuelven a reiniciarlo.

Se mantienen los intervalos de `sources.crawl_interval_seconds`: en el seed,
Mercado Libre cada 10 minutos y Facebook cada 60 minutos; en producción
(22/10/2026), las dos cada 30 minutos. Están sujetos al tick del worker y a la
duración de los recorridos. «Del día» describe la ventana de
publicación, no una ejecución única al día. La carga inicial puede tardar mucho
si necesita abrir numerosas fichas; consultar logs y estado de la fuente.

| Variable de entorno | Valor inicial | Uso |
| --- | --- | --- |
| `RECENT_ML_MAX_PAGES` | 100 | Tope de seguridad de páginas por ejecución |
| `RECENT_FB_MAX_SCROLLS` | 200 | Tope de seguridad de scrolls por ejecución |
| `RECENT_ML_DETAIL_SECONDS` | 8 | Pausa antes de consultar una fecha en ficha |
| `RECENT_ML_MAX_DATE_FETCHES` | 200 | Tope de fichas de Mercado Libre leídas por ejecución para conocer la fecha |
| `RECENT_FB_DETAIL_SECONDS` | 30 | Pausa antes de consultar una fecha en ficha |
| `RECENT_FB_MAX_DATE_FETCHES` | 12 | Tope de fichas de Facebook leídas por ejecución para conocer la fecha |
| `FB_DATE_MEMORY_UNKNOWN` | 0 | 1 memoriza también las fichas que cargaron sin fecha (`"id@epoch#n"`) |

Estas pausas regulan las lecturas de fecha durante el crawl; la cola de enrichment
mantiene su configuración independiente. Si se alcanza un tope con resultados
pendientes, el recorrido es incompleto y vuelve a intentarse. No hay cursor de
reanudación entre ejecuciones: si el catálogo siempre supera el tope, hay que
ajustarlo para poder completar el bootstrap. Las fechas guardadas de avisos ya
ingeridos evitan abrir sus fichas nuevamente para conocer la fecha. En Mercado
Libre, además, el worker recuerda mientras sigue corriendo la fecha leída de un
aviso que quedó fuera de la ventana. Así no vuelve a pedir esa ficha en cada
recorrido, y con el tope de fichas la ejecución siguiente sigue donde quedó la
anterior. Un reinicio borra esa memoria. En Facebook la memoria se guarda en
la base y sobrevive a los reinicios (ver «Facebook: fichas, memoria de fechas
y cola»).

## Validación

Desde la raíz del repositorio, con las dependencias del worker instaladas:

```bash
pytest -q worker/tests/test_recent_crawls.py
pytest -q -m 'not db'
```

Las pruebas de base requieren una instancia local de Supabase con las migraciones
aplicadas. Preparar su copia de prueba con `python -m tools.test_db` desde
`worker/`; los tests usan `automotive_test`, separada de la base del worker:

```bash
TEST_DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:54322/automotive_test pytest -q worker/tests/test_ingest_postgres.py
```

Para comprobar ambas plataformas en la máquina del worker, desde `worker/`, con
la base configurada (Mercado Libre no necesita sesión; Facebook usa la habitual).
Con `publication_days=1`, Mercado Libre lee «Publicados hoy»:

```bash
python -m tools.scraper_cli mercadolibre marca=Ford modelo=Fiesta publication_days=30
python -m tools.scraper_cli mercadolibre marca=Ford modelo=Fiesta publication_days=1
python -m tools.scraper_cli facebook marca=Ford modelo=Fiesta publication_days=30
python -m tools.scraper_cli facebook marca=Ford modelo=Fiesta publication_days=1
```

El CLI muestra las fechas verificadas, avisa de fechas desconocidas y termina con
código 2 si el recorrido fue incompleto. Sin `publication_days`, el CLI conserva
el recorrido manual anterior. El scheduler siempre aplica la política nueva a
estas dos fuentes. Verificar además un cambio de día en hora argentina y que la
carga inicial no genere alertas. La validación automática usa páginas simuladas,
y en Facebook también sesiones simuladas, así que no demuestra cómo responden hoy
los portales.
