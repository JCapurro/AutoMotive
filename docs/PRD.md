# PRD — Automotive

- **Versión:** 1.0
- **Estado:** MVP Definition
- **Producto:** Automotive
- **Mercado inicial:** Argentina
- **Plataforma inicial:** Web responsive + notificaciones externas
- **Visión futura:** Aplicación mobile para búsqueda, análisis, seguimiento y gestión del ciclo de vida de vehículos.

> Referencia versionada del PRD. El plan técnico ([TECHNICAL_PLAN.md](TECHNICAL_PLAN.md)) cita estas secciones como §N.

## 1. Resumen ejecutivo

Automotive es una plataforma que monitorea publicaciones de vehículos usados en distintas fuentes y notifica al usuario cuando aparece un vehículo que coincide con sus criterios de búsqueda.

El producto actual parte de una funcionalidad sencilla:

> El usuario configura qué vehículo busca y recibe una alerta cuando aparece una publicación compatible.

El objetivo del nuevo MVP es evolucionar desde un sistema de alertas por filtros hacia un asistente de búsqueda de vehículos usados capaz de:

1. entender qué vehículo busca el usuario;
2. monitorear continuamente nuevas publicaciones;
3. eliminar publicaciones irrelevantes;
4. detectar publicaciones potencialmente interesantes;
5. priorizarlas utilizando información de mercado;
6. alertar al usuario rápidamente;
7. ayudarlo a evaluar si vale la pena avanzar con una publicación.

La propuesta de valor del MVP será:

> Automotive monitorea el mercado por vos y te avisa cuando aparece una oportunidad compatible con lo que estás buscando.

El producto no intentará resolver todavía todo el proceso de compra de un vehículo ni convertirse en una aplicación automotriz integral.

## 2. Problema

Comprar un vehículo usado requiere revisar repetidamente múltiples marketplaces, concesionarias y sitios de clasificados.

El comprador debe realizar manualmente tareas como:

- repetir las mismas búsquedas varias veces por día;
- detectar publicaciones nuevas;
- descartar automáticos cuando busca manuales;
- comprobar versión, año y kilometraje;
- comparar precios con otros vehículos similares;
- identificar rápidamente publicaciones potencialmente baratas;
- revisar descripciones;
- detectar información faltante;
- contactar al vendedor;
- recordar qué vehículos ya vio;
- distinguir una verdadera oportunidad de un precio aparentemente atractivo.

Esta búsqueda es especialmente problemática cuando el usuario está buscando:

- modelos específicos;
- determinadas versiones;
- vehículos poco frecuentes;
- precios por debajo del mercado;
- publicaciones recientes;
- oportunidades que pueden desaparecer rápidamente.

Los filtros tradicionales de marketplaces resuelven parcialmente el problema, pero obligan al comprador a seguir entrando y analizando las publicaciones.

Automotive busca invertir esta lógica:

> el usuario define una vez qué está buscando y Automotive monitorea el mercado permanentemente.

## 3. Hipótesis principal

Si Automotive puede detectar publicaciones interesantes antes de que el usuario tenga que buscarlas manualmente, filtrar el ruido y explicar rápidamente por qué una publicación puede ser una oportunidad, entonces compradores activos de vehículos usados estarán dispuestos a utilizar el servicio frecuentemente durante su período de búsqueda y eventualmente pagar por él.

## 4. Visión del producto

Automotive debería evolucionar progresivamente desde:

**Alertas de publicaciones**

hacia:

**Asistente para encontrar vehículos**

y posteriormente:

**Asistente para tomar decisiones durante todo el ciclo de vida del vehículo.**

Visión futura:

`Buscar → Encontrar → Evaluar → Comprar → Mantener → Reparar → Vender → Reemplazar`

Sin embargo, el MVP cubre únicamente:

`Buscar → Encontrar → Evaluar`

## 5. Objetivo del MVP

Validar que Automotive puede convertirse en una herramienta recurrente durante la búsqueda de un vehículo.

El MVP debe responder cuatro preguntas:

1. **¿Las personas quieren delegar el monitoreo?** ¿Configuran búsquedas y mantienen las alertas activas?
2. **¿Automotive encuentra vehículos relevantes?** ¿Las publicaciones enviadas realmente coinciden con lo que busca el usuario?
3. **¿La priorización agrega valor?** ¿Los usuarios interactúan más con publicaciones identificadas como buenas oportunidades?
4. **¿Existe willingness to pay?** ¿Alguna parte de los usuarios pagaría por monitoreo más frecuente, más alertas, análisis de mercado o detección temprana?

## 6. No objetivos del MVP

Automotive NO será todavía:

- una app mobile nativa;
- un marketplace propio;
- una concesionaria;
- una plataforma de compra/venta;
- una plataforma de financiación;
- un comparador de seguros;
- un gestor de mantenimiento;
- un historial mecánico;
- un sistema de tasación certificado;
- una plataforma de inspección vehicular;
- un sistema que garantice que un vehículo está en buen estado;
- un agente que contacte vendedores automáticamente;
- una herramienta que compre vehículos automáticamente.

Estas funcionalidades pueden aparecer posteriormente.

## 7. Público objetivo

### ICP inicial

Persona que está buscando activamente comprar un vehículo usado en Argentina durante los próximos 1–3 meses.

Características:

- revisa Mercado Libre u otros sitios frecuentemente;
- tiene modelos concretos en consideración;
- posee un presupuesto definido;
- compara varias publicaciones;
- está dispuesto a movilizarse rápidamente si aparece una oportunidad;
- tiene miedo de perder una buena publicación;
- dedica varias horas por semana a buscar.

## 8. Persona principal

### Comprador activo

Ejemplo:

> “Busco Fiesta Titanium manual 2016–2018, Polo Highline o Focus SE Plus manual. Presupuesto máximo USD 12.000. Preferentemente menos de 140.000 km y dentro de AMBA.”

Actualmente esta persona realiza búsquedas similares varias veces por día.

Con Automotive debería poder configurar esa intención una única vez.

## 9. Persona secundaria futura

### Comprador profesional / revendedor

Busca permanentemente oportunidades según:

- precio;
- modelos;
- kilómetros;
- margen potencial;
- zona;
- antigüedad de publicación.

No será el target principal del primer MVP, pero la arquitectura debe permitir soportarlo en el futuro.

## 10. Propuesta de valor

### Propuesta principal

> Decinos qué auto estás buscando. Automotive monitorea las publicaciones y te avisa cuando aparece uno que vale la pena mirar.

### Mensaje alternativo

> Encontrá las oportunidades antes que los demás.

### Diferenciación

Automotive no debe limitarse a:

> “Apareció un nuevo Fiesta.”

Debe progresivamente llegar a:

> “Apareció este Fiesta hace 6 minutos. Cumple tus filtros, está aproximadamente 8% debajo de publicaciones similares y tiene un Opportunity Score de 87/100.”

## 11. Principios de producto

1. **Menos alertas, mejores alertas.** No maximizar cantidad. Maximizar relevancia.
2. **Rapidez.** Una publicación interesante pierde valor si llega seis horas después.
3. **Explicabilidad.** Automotive debe explicar por qué recomienda mirar una publicación.
4. **Control del usuario.** Los criterios duros deben poder configurarse explícitamente.
5. **No fingir certeza.** Una publicación barata no significa automáticamente que sea buena.
6. **Evolución progresiva.** El MVP debe poder convertirse posteriormente en app sin reemplazar el backend central.

## 12. Flujo principal

### Onboarding

Usuario ingresa a Automotive.

CTA: **Crear búsqueda**

Puede crear su búsqueda de dos maneras.

### Modo estructurado

- marca;
- modelo;
- versión;
- año desde;
- año hasta;
- kilometraje máximo;
- precio máximo;
- transmisión;
- combustible;
- ubicación;
- radio geográfico.

### Modo asistido

Campo: **¿Qué auto estás buscando?**

Ejemplo:

> “Busco Fiesta Titanium manual 2016 a 2018 hasta USD 11.500 y menos de 150.000 km. También podría ser Polo Highline.”

Automotive interpreta el texto y genera filtros.

El usuario siempre puede revisar/modificar la interpretación antes de guardar.

## 13. Concepto de Search Profile

La entidad central del MVP será **Search Profile**.

Ejemplo:

- **Búsqueda:** Fiesta
- **Modelos:** Ford Fiesta Titanium.
- **Año:** 2016–2018.
- **Transmisión:** Manual.
- **Precio:** ≤ USD 11.500.
- **Kilometraje:** ≤ 150.000 km.
- **Zona:** AMBA.
- **Alertas:** Inmediatas.

El usuario puede tener múltiples Search Profiles.

Ejemplo:

- Búsqueda 1: Fiesta Titanium.
- Búsqueda 2: Polo Highline.
- Búsqueda 3: Cruze LTZ.

Esto es preferible inicialmente a intentar crear una única búsqueda extremadamente compleja.

## 14. Ingesta de publicaciones

Automotive deberá ejecutar procesos periódicos sobre las fuentes integradas.

Por cada publicación detectada almacenar:

- fuente;
- external_listing_id;
- URL;
- título;
- descripción;
- marca;
- modelo;
- versión;
- año;
- precio;
- moneda;
- kilometraje;
- transmisión;
- combustible;
- ubicación;
- vendedor;
- tipo de vendedor;
- fecha de publicación;
- fecha de primera detección por Automotive;
- imágenes disponibles;
- atributos adicionales;
- estado;
- fecha de última observación.

Debe conservarse una copia normalizada de los atributos relevantes.

## 15. Detección de publicación nueva

No se debe alertar nuevamente por la misma publicación.

Automotive debe distinguir:

### Nueva publicación

Listing nunca detectado.

### Publicación actualizada

Cambió:

- precio;
- descripción;
- kilometraje;
- imágenes;
- algún atributo significativo.

### Re-publicación

Vehículo posiblemente idéntico publicado con nuevo ID.

La deduplicación avanzada puede ser imperfecta en MVP.

Como mínimo:

`source + listing_id`

debe ser único.

Posteriormente puede utilizarse:

`modelo + precio + km + vendedor + similitud imágenes/texto`.

## 16. Matching Engine

Cada publicación entrante debe compararse con Search Profiles activos.

### Hard filters

Si no cumple, no alertar.

Ejemplos:

- transmisión;
- precio máximo;
- año mínimo;
- año máximo;
- modelo;
- ubicación.

### Soft preferences

No necesariamente descartan.

Ejemplos:

- kilometraje;
- versión preferida;
- vendedor particular;
- color;
- distancia;
- precio objetivo.

Estas preferencias alimentarán el ranking.

## 17. Opportunity Score

Una de las evoluciones centrales del MVP será pasar de:

**match / no match**

a:

**qué tan interesante parece este match.**

Escala: 0–100.

Ejemplo:

> Opportunity Score: 87

El algoritmo inicial no necesita machine learning.

Debe ser determinístico y explicable.

## 18. Componentes iniciales del Opportunity Score

Ejemplo conceptual:

| Componente | Peso | Descripción |
|---|---|---|
| Precio | 35% | Comparación contra vehículos similares. |
| Match con búsqueda | 25% | Qué tan exactamente coincide con lo pedido. |
| Kilometraje | 15% | Comparado contra vehículos similares. |
| Versión/equipamiento | 10% | Preferencia definida. |
| Antigüedad de publicación | 10% | Más nueva = mayor oportunidad temporal. |
| Completitud/confianza | 5% | Cantidad y calidad de información disponible. |

Los pesos deben ser configurables.

## 19. Price Intelligence

Automotive debe calcular una referencia de precio basada en publicaciones comparables.

Comparables iniciales:

- misma marca;
- mismo modelo;
- años cercanos;
- misma versión cuando sea posible;
- misma transmisión;
- kilometraje similar.

Ejemplo:

- Precio publicación: USD 10.300
- Mediana comparable: USD 11.200
- Diferencia: -8%

UI:

> 8% debajo del mercado observado

Debe utilizarse terminología prudente:

- “mercado observado”;
- “publicaciones comparables”;
- “precio publicado”.

No:

- “vale exactamente”;
- “precio real”;
- “tasación oficial”.

## 20. Niveles de oportunidad

Para facilitar la UX:

| Nivel | Score |
|---|---|
| 🔥 Alta oportunidad | 85–100 |
| 🟢 Buena coincidencia | 70–84 |
| 🟡 Coincidencia | 50–69 |
| ⚪ Baja prioridad | <50 |

Inicialmente los thresholds deberán ser configurables.

## 21. Alertas

Canales MVP:

### Obligatorio

- email o canal existente actualmente;
- web.

### Prioridad alta

- WhatsApp o Telegram.

### Futuro

- push notification mobile.

El sistema de notificación debe estar desacoplado del canal para facilitar posteriormente push notifications desde una app.

## 22. Tipos de alertas

### Match normal

> 🚗 Nuevo vehículo encontrado
> Ford Fiesta Titanium 2017
> 128.000 km
> USD 11.000

### Oportunidad

> 🔥 Nueva oportunidad
> Ford Fiesta Titanium 2017
> 112.000 km
> USD 10.300
> Opportunity Score 88/100
> 8% debajo de publicaciones comparables.
> Publicado hace 4 minutos.
> `Ver publicación`

### Baja de precio

> 📉 Bajó de precio
> Ford Fiesta Titanium 2017
> Antes: USD 11.500
> Ahora: USD 10.800
> -6,1%

## 23. Página de resultado

Cada publicación deberá tener una vista interna simplificada.

Información:

- **Vehículo:** Ford Fiesta Titanium 2017.
- **Precio:** USD 10.300.
- **Kilometraje:** 112.000 km.
- **Ubicación:** Vicente López.
- **Publicado:** Hace 8 minutos.
- **Opportunity Score:** 88/100.

### ¿Por qué apareció?

Automotive debe mostrar:

- ✅ versión buscada
- ✅ caja manual
- ✅ dentro del presupuesto
- ✅ kilometraje compatible
- ✅ zona compatible

### Análisis de precio

- Precio publicación: USD 10.300.
- Publicaciones comparables: USD 11.200 mediana.
- Diferencia: -8%.

## 24. Señales y red flags

El MVP puede incluir una capa sencilla de análisis de publicación.

Ejemplos:

- ⚠️ No especifica cantidad de dueños.
- ⚠️ No informa services.
- ⚠️ No informa distribución.
- ⚠️ Publicación significativamente más barata que comparables.
- ⚠️ Descripción muy corta.
- ⚠️ Kilometraje inusualmente bajo para la antigüedad.

Estas señales no deben afirmar fraude ni problemas mecánicos.

Sólo: **información que conviene verificar.**

## 25. Asistente de contacto

Feature MVP recomendable pero secundaria.

Botón: **¿Qué le pregunto al vendedor?**

Automotive genera preguntas contextuales.

Ejemplo:

> Hola, ¿cómo estás? ¿Lo seguís teniendo? ¿Sos titular? ¿Cuándo se hizo la distribución por última vez? ¿Tiene VTV vigente? ¿Tuvo choques o reparaciones importantes? ¿Tenés historial de services?

El usuario copia el mensaje.

Automotive NO contactará automáticamente al vendedor durante el MVP.

## 26. Estados de una publicación

El usuario debe poder clasificar listings.

Estados:

- Nuevo.
- Visto.
- Me interesa.
- Descartado.
- Contactado.
- Visita agendada.
- Comprado.

Esto permitirá aprender posteriormente del comportamiento del usuario.

## 27. Razones de descarte

Cuando un usuario descarta una publicación puede opcionalmente seleccionar:

- demasiado caro;
- demasiados kilómetros;
- mala versión;
- ubicación;
- automático;
- vendedor;
- estado aparente;
- documentación;
- otro.

Esto genera datos muy valiosos para ajustar búsquedas.

No hace falta automatizar el aprendizaje inicialmente.

Pero deben almacenarse.

## 28. Dashboard principal

El dashboard del MVP debe ser extremadamente simple.

### Header

Automotive.

### Mis búsquedas

Cards:

- **Fiesta Titanium** — 14 nuevos esta semana. 2 oportunidades. `Ver resultados`
- **Polo Highline** — 7 nuevos. 1 oportunidad.

### Oportunidades recientes

Feed ordenado por:

1. Opportunity Score;
2. fecha de detección.

## 29. Search Results

Filtros:

- nuevos;
- oportunidades;
- todos;
- favoritos;
- descartados.

Orden:

- más recientes;
- mejor oportunidad;
- menor precio;
- menor kilometraje.

## 30. Watchlist / favoritos

El usuario podrá guardar una publicación.

Automotive continuará monitoreándola.

Eventos interesantes:

- precio bajó;
- publicación desapareció;
- publicación cambió;
- publicación lleva X días publicada.

Esto permite comenzar a construir histórico.

## 31. Histórico de precios

Si Automotive detecta múltiples cambios:

> Ford Fiesta 2017
> 01/09 — USD 11.800
> 10/09 — USD 11.300
> 21/09 — USD 10.900

Esto debe mostrarse cuando exista información suficiente.

Es una feature de alto valor y relativamente bajo costo técnico si la ingesta ya existe.

## 32. Configuración de frecuencia

El usuario puede seleccionar:

- **Inmediata:** avisar cuando aparece.
- **Resumen periódico:** digest.

Para MVP:

- inmediata;
- diaria.

## 33. Freemium inicial

No necesariamente activar pagos desde el primer día, pero diseñar límites.

### Free

- 1 Search Profile;
- frecuencia estándar;
- cantidad limitada de resultados;
- filtros básicos.

### Pro

Hipótesis inicial: USD 10–20 / mes.

Incluye:

- múltiples búsquedas;
- monitoreo más frecuente;
- alertas inmediatas;
- Opportunity Score;
- Price Intelligence;
- histórico de precios;
- filtros avanzados.

Debe validarse antes de fijarse definitivamente.

## 34. Alternativa de pricing

Debido a que la búsqueda de un auto tiene duración limitada, puede funcionar mejor:

### Automotive Search Pass

- 30 días: USD 10–15.
- 90 días: USD 20–30.

Esto evita exigir una suscripción permanente para una necesidad temporal.

Testear ambos modelos.

## 35. Métricas principales

### North Star Metric

Cantidad de publicaciones relevantes abiertas desde una alerta por usuario activo.

Esto mide si Automotive realmente está encontrando cosas que vale la pena mirar.

## 36. Métricas de activación

### Search Profile Creation Rate

Usuarios registrados → búsqueda creada.

Objetivo inicial: 70%.

### First Value

Tiempo desde creación de búsqueda hasta primer match relevante.

## 37. Métricas de relevancia

- **Alert Open Rate:** qué porcentaje de alertas genera apertura.
- **Listing Click Rate:** qué porcentaje termina abriendo publicación original.
- **Save Rate:** qué porcentaje se marca “Me interesa”.
- **Dismiss Rate:** qué porcentaje se descarta.
- **High Score Engagement:** comparar engagement `Opportunity >85` vs. `match normal`. Si no existe diferencia significativa, el score no está agregando valor.

## 38. Métricas de outcome

Evento más importante:

### Purchased Vehicle

El usuario marca: **Compré este vehículo.**

Registrar:

- listing;
- búsqueda;
- precio;
- fecha;
- tiempo usando Automotive.

Pregunta posterior:

> ¿Automotive influyó en que encontraras este vehículo?

Opciones:

- mucho;
- algo;
- poco;
- no.

## 39. Evento clave futuro

Cuando el usuario presiona **Compré este vehículo**, Automotive debe guardar una entidad:

`OwnedVehicle`

aunque todavía no exista ninguna funcionalidad alrededor de ella.

Esto permitirá posteriormente construir **Automotive Garage** y funcionalidades como:

- mantenimiento;
- gastos;
- repairs;
- valuación;
- Repair-or-Replace.

La estructura de datos debe contemplarlo desde ahora.

## 40. Modelo conceptual de datos

### User

- id
- email
- phone
- plan
- created_at

### SearchProfile

- id
- user_id
- name
- filters
- preferences
- notification_frequency
- enabled

### VehicleDefinition

- make
- model
- trim
- year
- transmission
- fuel

### Listing

- id
- source
- external_id
- url
- vehicle attributes
- seller attributes
- price
- mileage
- location
- published_at
- first_seen_at
- last_seen_at

### ListingSnapshot

- listing_id
- timestamp
- price
- attributes

### Match

- search_profile_id
- listing_id
- score
- match_reasons
- generated_at

### UserListingInteraction

- user_id
- listing_id
- status
- rejection_reason
- timestamp

### OwnedVehicle

- user_id
- listing_id
- purchase_price
- purchase_date

## 41. Arquitectura conceptual

La arquitectura debería dividirse desde el comienzo en cinco capas.

1. **Collectors.** Obtienen publicaciones.
2. **Normalization.** Transforman diferentes fuentes en un schema común.
3. **Intelligence.** Matching; comparable vehicles; pricing; opportunity scoring; red flags.
4. **Notification Engine.** Decide: a quién alertar; cuándo; por qué canal.
5. **Client.** Inicialmente: web responsive. Futuro: mobile app.

Esto permite reemplazar el frontend sin tocar collectors o intelligence.

## 42. Frecuencia de crawling

La frecuencia ideal dependerá de cada fuente y sus restricciones.

Conceptualmente:

- **Fuentes importantes:** cada pocos minutos.
- **Fuentes secundarias:** intervalos mayores.

Guardar `first_seen_at` es fundamental.

El diferencial futuro podría ser:

> “Automotive detectó esta publicación 3 minutos después de aparecer.”

## 43. Inteligencia artificial

IA debe utilizarse donde reduzca trabajo.

No agregar IA únicamente para marketing.

Usos adecuados en MVP:

- **Interpretar búsqueda natural:** “Quiero Fiesta Titanium manual…” → filtros estructurados.
- **Normalizar títulos/descripciones:** detectar versión, transmisión, equipamiento.
- **Analizar descripción:** extraer services, titular, distribución, detalles importantes.
- **Generar preguntas:** según información faltante.

## 44. Qué NO debería depender de un LLM

- precio;
- filtros duros;
- deduplicación primaria;
- comparación numérica;
- Opportunity Score base;
- timestamps;
- reglas del usuario.

Estas deben ser funciones determinísticas.

## 45. Admin / Backoffice

El MVP necesita un pequeño backoffice.

Debe permitir:

- ver usuarios;
- búsquedas;
- listings;
- fuentes;
- errores;
- matches;
- alertas enviadas;
- scores;
- frecuencia collectors.

Y fundamentalmente: **inspeccionar por qué una alerta fue enviada.**

Ejemplo:

```
Listing #4837
matched Search #222

model = true
year = true
transmission = true
price = true
location = true

score = 87
```

Esto será crítico durante validación.

## 46. Observabilidad

Registrar:

- collector failures;
- cantidad de listings capturados;
- listings nuevos;
- listings actualizados;
- matches generados;
- alertas enviadas;
- errores de normalización;
- errores de notificación.

Dashboard simple.

No necesita infraestructura sofisticada inicialmente.

## 47. Riesgos principales

### Dependencia de fuentes externas

Los marketplaces pueden:

- cambiar HTML;
- limitar requests;
- modificar APIs;
- aplicar anti-bot;
- bloquear scraping.

Mitigación: arquitectura desacoplada por collector.

### Datos incompletos

Publicaciones pueden omitir:

- versión;
- transmisión;
- km;
- información técnica.

Mitigación: normalización + extracción inteligente + confidence score.

### Falsas oportunidades

Auto barato puede ser:

- mal publicado;
- chocado;
- tener problemas;
- ser precio financiado;
- publicación engañosa.

Por eso Automotive debe decir:

> “precio debajo del mercado observado”

y no:

> “compralo”.

### Demasiadas alertas

Puede destruir rápidamente el valor del producto.

KPI: alerts/user/day.

Debe existir control estricto.

## 48. Feature prioritization

### P0 — indispensable

- registro/login;
- creación de Search Profile;
- edición de filtros;
- collectors;
- normalización;
- detección de listings nuevos;
- matching;
- deduplicación;
- alertas;
- dashboard;
- listado de resultados;
- enlace a publicación original;
- favoritos;
- descartados;
- tracking de eventos.

### P1 — MVP fuerte

- Opportunity Score;
- comparables;
- referencia de precios;
- alertas de precio;
- interpretación de búsqueda natural;
- explicación “por qué apareció”;
- estados de publicación;
- preguntas para vendedor;
- múltiples Search Profiles.

### P2 — después de validar

- análisis avanzado de fotos;
- análisis profundo de red flags;
- aprendizaje automático de preferencias;
- contacto vendedor;
- inspección;
- integración financiación;
- seguros;
- dealer accounts;
- app;
- Automotive Garage.

## 49. MVP final recomendado

No lanzaría simplemente:

> “Recibí alertas de autos.”

El MVP que considero suficientemente fuerte es:

### Automotive Search

El usuario puede:

1. describir qué vehículo busca;
2. configurar filtros;
3. activar búsquedas;
4. recibir alertas;
5. ver publicaciones nuevas;
6. ver Opportunity Score;
7. comparar precio contra mercado observado;
8. entender por qué hizo match;
9. guardar/descartar;
10. recibir alertas cuando cambia el precio.

Eso ya constituye un producto completo y defendible para validar.

## 50. Home / landing propuesta

### Hero

> Encontrá las oportunidades antes que los demás.
>
> Decinos qué auto estás buscando.
>
> Automotive monitorea las publicaciones y te avisa cuando aparece uno que vale la pena mirar.

`Crear mi búsqueda`

### Ejemplo visual

> 🔥 Nueva oportunidad
> Ford Fiesta Titanium 2017
> 112.000 km
> USD 10.300
> 88 / 100
> 8% debajo de publicaciones comparables.
> Publicado hace 4 minutos.

### Beneficios

- **No busques todo el día.** Automotive monitorea por vos.
- **No revises cientos de publicaciones.** Filtramos según lo que realmente buscás.
- **Detectá oportunidades.** Comparamos cada publicación contra vehículos similares.
- **Llegá temprano.** Recibí la alerta cuando aparece.

## 51. Estrategia de lanzamiento

Evitar un lanzamiento masivo inicialmente.

Primer objetivo: 20–50 usuarios buscando activamente un auto.

Ideal: personas que estén realmente pensando comprar dentro de 90 días.

Canales iniciales:

- Reddit/comunidades automotrices;
- grupos de Facebook;
- conocidos;
- foros;
- comunidades de modelos específicos;
- Marketplace communities;
- contenido SEO;
- contenido corto mostrando oportunidades detectadas.

## 52. Experimento de monetización

No esperar meses.

Cuando un usuario tenga actividad real mostrar:

> ¿Querés enterarte antes?

Automotive Pro:

- búsqueda cada X minutos;
- alertas inmediatas;
- Opportunity Score;
- análisis de precios;
- múltiples búsquedas.

CTA: `Probar Automotive Pro`

Incluso antes de implementar cobro puede medirse intención mediante:

- click;
- checkout;
- lista de espera.

## 53. Criterio para considerar validado el MVP

Automotive debe demostrar:

- **Uso:** ≥30 usuarios con búsquedas activas.
- **Relevancia:** ≥30% de las alertas abiertas.
- **Engagement:** ≥15% de publicaciones alertadas generan click o guardado.
- **Retención:** usuarios siguen utilizando búsqueda durante varias semanas.
- **Outcome:** al menos algunos usuarios llegan a visitar/contactar vehículos descubiertos mediante Automotive.
- **Monetización:** ≥10% de usuarios activos muestran intención clara de pagar. Idealmente: primeros usuarios pagos.

## 54. Decisión de construir app

La app NO debería construirse simplemente porque el producto “queda mejor” en mobile.

La decisión debería tomarse cuando tengamos evidencia de que:

- usuarios utilizan Automotive varias veces por semana;
- las notificaciones son críticas;
- existe repetición de uso;
- usuarios guardan y comparan vehículos;
- existe comportamiento que justifique push notifications;
- la adquisición/retención funcionan.

En ese momento la app mejora una experiencia ya validada.

No intenta validarla.

## 55. Evolución hacia la app

Cuando llegue ese momento:

- **Tab 1 — Discover:** feed personalizado.
- **Tab 2 — Searches:** búsquedas activas.
- **Tab 3 — Saved:** vehículos guardados.
- **Tab 4 — Garage:** vehículos comprados.
- **Tab 5 — Profile:** preferencias.

Esto conecta perfectamente con futuras extensiones.

## 56. Roadmap conceptual

- **Automotive 1.0 — Find.** Buscar + monitorear + alertar.
- ↓ **Automotive 1.5 — Understand.** Opportunity Score + precios + red flags.
- ↓ **Automotive 2.0 — Buy.** Comparación + checklist + inspección + contacto.
- ↓ **Automotive 3.0 — Garage.** Historial, gastos y mantenimiento.
- ↓ **Automotive 4.0 — Decide.** Repair-or-Replace.
- ↓ **Automotive 5.0 — Lifecycle.** Encontrar → comprar → mantener → vender → reemplazar.

## 57. La apuesta del MVP

El principal diferencial que Automotive debe validar no es scraping.

No es IA.

No es una app.

Es:

> ¿Podemos saber suficientemente bien qué busca una persona y detectar entre cientos de publicaciones cuáles realmente merecen su atención?

Si la respuesta es sí, Automotive puede convertirse en una capa de inteligencia por encima de los marketplaces.

El marketplace muestra inventario.

Automotive decide qué inventario merece tu atención.

## 58. Definición final del producto

### Automotive

Automotive es un asistente para compradores de vehículos usados que monitorea el mercado, encuentra publicaciones compatibles con lo que buscan y los alerta cuando aparece una potencial oportunidad.

### Promesa MVP

> Vos elegís qué auto querés. Automotive busca por vos.

### Evolución inmediata

> Vos elegís qué auto querés. Automotive busca, compara y te avisa cuando aparece uno que vale la pena mirar.

### Visión

> Automotive te ayuda a tomar mejores decisiones durante toda la vida de tu auto.
