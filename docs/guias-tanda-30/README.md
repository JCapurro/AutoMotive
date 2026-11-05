# Guías de la tanda de 30 (PAR-04)

Las 25 guías que faltaban para completar los 30 modelos con más búsquedas activas (`admin_guide_candidates(30)` en producción, 05/11/2026). Las otras 5 son las piloto de `docs/guias-piloto/`, que ya están publicadas.

Siguen el mismo formato y criterio que las piloto (ver `docs/guias-piloto/README.md`). Cada archivo es el `p_values` completo para `admin_save_model_guide`: `make, model, generation_label, year_from, year_to, slug_make, slug_model, body, questions, sources`.

- Marca y modelo con la grafía de `vehicle_catalog`. Los slugs coinciden con `slugify()` de `web/lib/guides.ts`.
- Validadas con `python -m json.tool` y con un test temporal de vitest (no commiteado) que corrió `GuideValuesInput` (zod), `lintGuide` (términos prohibidos y cifras de dinero), `publishProblem` y los slugs: las 25 pasan.
- No hay montos de dinero.
- `verified: true` quiere decir que la fuente se abrió y respalda renglones concretos de la guía. Los renglones sin fuente argentina están marcados en `applies_to` («reportes en Brasil», «otros mercados») o piden confirmar en el manual o con el VIN. Igual, quien publique tiene que leerlas y marcar «La revisé».
- **Cargadas en producción el 05/11/2026 como borradores** (`status = draft`, sin publicar) con `admin_save_model_guide`: el Golf sobre el borrador id 6 y las otras 24 con ids 7 a 30. Se comparó un md5 de `body`, `questions`, `sources`, `generation_label` y años de cada fila contra estos archivos: las 25 coinciden. Para publicarlas hay que revisarlas en `/admin/guides` y marcar «La revisé».

## Decisiones de generación que conviene revisar

Algunas guías cubren otros años que el catálogo o que lo sugerido, porque las fuentes argentinas dicen otra cosa:

- **Chevrolet Corsa** cubre el Corsa II (2002–2010), porque el catálogo tiene «Classic» como modelo aparte. Las búsquedas de 2011–2014 van a caer más en el Classic.
- **Chevrolet Celta** cubre 2011–2016: entre 2003 y 2011 el auto se vendió acá como **Suzuki Fun**, que tiene su propia guía.
- **Suzuki Fun**: según las fuentes era importado de Brasil (Gravataí), no fabricado en Argentina.
- **Peugeot 208**: la primera generación venía de Brasil (y el XY y el GTi de Francia), no de Palomar. `year_to` queda en 2020, cuando llegó la segunda generación.
- **Honda City**: en Argentina hubo una sola generación (2009–2015). La búsqueda que llega a 2016 queda afuera.
- **Honda HR-V**: la prensa argentina llama «segunda» a la generación 2015–2022.
- **Kia K3**: se vende desde marzo de 2025, así que `year_from` es 2025 y no 2024 como dice el catálogo.
- **Citroën C4**: 2007–2014 con hatch y sedán juntos. «C4 Pallas» es el nombre brasileño.
- **Mercedes-Benz Clase C** (W204): `year_to` es 2015, porque el W205 llegó en mayo de 2015 y el llamado Takata cubre 2007–2015.
- **Volkswagen Vento**: cubre la sexta generación (Jetta VI, 2011–2018), que abarca las búsquedas de 2010–2015.
- **Fiat Palio**: una sola guía para 1996–2017. El Nuevo Palio y la Palio Weekend tienen un renglón cada uno y quizás merezcan guía propia.

| Archivo | Guía | Años | Fuentes | Preguntas |
|---|---|---|---|---|
| `volkswagen-golf.json` | Volkswagen Golf, Golf VII | 2015–2021 | 11 | 6 |
| `peugeot-208.json` | Peugeot 208, Primera generación | 2013–2020 | 9 | 6 |
| `volkswagen-gol.json` | Volkswagen Gol, Gol G3 y G4 (incluye Gol Power) | 1999–2014 | 10 | 6 |
| `volkswagen-polo.json` | Volkswagen Polo, Polo, sexta generación (MQB A0) | 2018– (year_to null) | 8 | 6 |
| `chevrolet-corsa.json` | Chevrolet Corsa, Corsa II | 2002–2010 | 8 | 7 |
| `volkswagen-saveiro.json` | Volkswagen Saveiro, Saveiro sobre base Gol Trend (G5, G6 y G7) | 2010– (year_to null) | 13 | 6 |
| `volkswagen-vento.json` | Volkswagen Vento, Vento, sexta generación (Jetta VI) | 2011–2018 | 11 | 6 |
| `chevrolet-onix.json` | Chevrolet Onix, Segunda generación | 2020– (year_to null) | 14 | 6 |
| `fiat-punto.json` | Fiat Punto, Punto (Grande Punto regional) | 2007–2017 | 13 | 7 |
| `volkswagen-bora.json` | Volkswagen Bora, Bora renovado (restyling 2008) | 2008–2015 | 7 | 6 |
| `audi-a3.json` | Audi A3, A3 tercera generación (8V) | 2013–2020 | 11 | 6 |
| `chevrolet-celta.json` | Chevrolet Celta, Celta 1.4 (lanzamiento argentino de 2011) | 2011–2016 | 10 | 6 |
| `citroen-c4.json` | Citroën C4, Primera generación (hatchback y sedán argentinos) | 2007–2014 | 8 | 5 |
| `fiat-palio.json` | Fiat Palio, Primera generación (proyecto 178) y restylings | 1996–2017 | 12 | 6 |
| `ford-maverick.json` | Ford Maverick, Primera generación (pick-up compacta) | 2022– (year_to null) | 9 | 6 |
| `honda-city.json` | Honda City, Quinta generación | 2009–2015 | 9 | 6 |
| `honda-hr-v.json` | Honda HR-V, Segunda generación (Campana y México) | 2015–2022 | 10 | 6 |
| `kia-k3.json` | Kia K3, Primera generación (importado de México) | 2025– (year_to null) | 6 | 5 |
| `mercedes-benz-clase-c.json` | Mercedes-Benz Clase C, Clase C W204 | 2007–2015 | 11 | 6 |
| `renault-clio.json` | Renault Clio, Clio II y Clio Mío | 2000–2016 | 9 | 5 |
| `renault-kardian.json` | Renault Kardian, Primera generación | 2024– (year_to null) | 8 | 5 |
| `suzuki-fun.json` | Suzuki Fun, Fun (Chevrolet Celta con marca Suzuki) | 2003–2011 | 9 | 5 |
| `suzuki-grand-vitara.json` | Suzuki Grand Vitara, Grand Vitara tercera generación (JIII) | 2008–2018 | 11 | 5 |
| `toyota-hilux.json` | Toyota Hilux, Séptima generación | 2005–2015 | 11 | 7 |
| `toyota-rav4.json` | Toyota RAV4, Cuarta generación (XA40) | 2013–2019 | 8 | 6 |

La tabla está ordenada por cantidad de búsquedas activas.

## Volkswagen Golf VII (2015–2021)

Fuentes:
- Autoweb, «Primer contacto: Volkswagen Golf VII» (09/04/2015): https://www.autoweb.com.ar/2015/04/09/primer-contacto-volkswagen-golf-vii/
- Monkey Motor, «El Volkswagen Golf VII está llegando a la Argentina» (29/01/2015): https://www.monkeymotor.net/2015/01/el-volkswagen-golf-vii-esta-llegando-la.html
- Monkey Motor, Golf 2018 en Argentina (restyling, 26/09/2017): https://www.monkeymotor.net/2017/09/volkswagen-golf-2018-argentina.html
- Autotest, el Golf que seguía a la venta a fines de 2020 (28/12/2020): https://autotest.com.ar/noticias/volkswagen-golf-dejo-de-comercializar/
- Parabrisas, «Volkswagen se despide del Golf VII» (21/01/2021): https://parabrisas.perfil.com/noticias/novedades/volkswagen-golf-vii-7-nuevo-hatchback-argentina-mexico-produccion-adios.phtml
- Autotest, Golf R de séptima generación (13/02/2023): https://autotest.com.ar/noticias/volkswagen-golf-r-septima-generacion-argentina/
- Defensa del Consumidor, alerta Golf, Tiguan y Vento (23/07/2019): https://www.argentina.gob.ar/noticias/alerta-propietarios-de-autos-volkswagen-golf-tiguan-y-vento-y-nissan-tiida
- Volkswagen Argentina, Libro de Servicio Postventa (2017, PDF): https://www.volkswagen.com.ar/idhub/content/dam/onehub_pkw/importers/ar/tengo-un-volkswagen/mantenimiento/Vw_LibroBlanco.pdf
- Auto+ TV (Brasil), DSG en Golf GTI y Jetta GLI (30/08/2025): https://www.automaistv.com.br/curiosidades/volkswagen-golf-gti-e-jetta-gli-o-cambio-dsg-ainda-e-um-problema-explicamos/
- Volkswagen Nueva Zelanda, campaña 35E5 de mecatrónica DQ200: https://volkswagen.co.nz/en/owners-and-servicing/about-my-car/campaigns-and-recalls/mechatronics-unit.html
- Opinautos, foro «Ruido caja DSG» del Golf: https://www.opinautos.com/volkswagen/golf/temas/bc945d6e0e/ruido-caja-dsg

Dudas:
- **Años**: llegó a concesionarios en enero de 2015 (Monkey Motor) con lanzamiento oficial en abril (Autoweb). 16 Válvulas habla de unidades desde 2013 «por las políticas de importación», no lo usé. `year_to` 2021 es aproximado: la producción en México terminó en enero de 2021 y a fines de 2020 quedaban la Highline 250 TSI y los últimos GTI; no encontré cuándo se vendió la última unidad.
- **Campaña DQ200**: la de Nueva Zelanda cubre mecatrónicas fabricadas hasta noviembre de 2014; el Golf VII argentino se fabricó en Puebla desde 2014, así que puede haber unidades tempranas en el rango, pero no lo confirmé. La guía pide consultar con el VIN.
- **Síntomas de la DSG**: salen de prensa brasileña (Auto+ TV, con comentarios de lectores que discuten partes de la nota) y de un foro con usuarios de Argentina, México y España. No encontré una nota de prensa argentina sobre fallas de la DSG del Golf VII.
- **Correa de distribución del 1.4 TSI y del 1.6**: ninguna fuente que abrí lo confirma para el Golf. Usé la recomendación general del libro de VW Argentina (90.000 km) y se pide confirmar en el manual.
- **Llamado de resortes (2019)**: el rango de chasis del Golf es 3VW**6AU*FM071868 a 3VW**6AU*KM000440; no puse años porque la nota no los da.
- **Golf R**: el catálogo lo lista, pero Autotest (2023) dice que nunca llegó oficialmente; Monkey Motor 2017 decía que llegaría en 2018.

Correcciones tras el chequeo de fuentes (11/2026):
- Trendline: Autoweb dice manual de cinco y Monkey Motor de seis; la guía muestra las dos y pide confirmarlo.
- Airbags 2015: Autoweb dice siete airbags en todas y Monkey Motor airbags frontales en la Trendline; ya no se afirma ninguna de las dos, se pide confirmarlo (renglón y pregunta 6).
- Potencia del 1.4 TSI en 2015: 140 CV (Autoweb y Monkey Motor). Saqué la prueba de Parabrisas (150 CV) para no mezclar cifras; 150 CV queda solo para el restyling.
- GTI: saqué «se sumó ese mismo año» (ninguna fuente abierta confirma la fecha) y quedó «llegó después», con 220 CV antes del restyling y 230 CV después.
- Mantenimiento DSG: «las reparaciones que más aparecen» pasó a «aparecen entre las reparaciones reportadas».
- Ruido en DSG: atribuido a relatos de foros, con el diagnóstico de los concesionarios «según esos relatos».
- No se quitó ninguna fuente: las 11 cargan y respaldan algo de la guía.

## Peugeot 208 primera generación (2013–2020)

Fuentes:
- Autoblog Uruguay, «Peugeot lanzó en Argentina al 208 fabricado en Brasil» (06/2013): https://www.autoblog.com.uy/2013/06/peugeot-lanzo-en-argentina-al-208.html
- Monkey Motor, «Peugeot Argentina presentó la nueva actualización del 208» (07/2016): https://www.monkeymotor.net/2016/07/peugeot-argentina-presento-nuevo-208.html
- Parabrisas, prueba del 208 Allure Tiptronic (fechada 30/06/2019 en la página): https://parabrisas.perfil.com/noticias/test/peugeot-208-allure-tiptronic-test-prueba-de-manejo-feline-115-cv-16.phtml
- 16Válvulas, «Test Drive: Peugeot 208 Feline caja automática 6 marchas» (22/01/2018): https://www.16valvulas.com.ar/test-drive-peugeot-208-feline-caja-automatica-6-marchas/
- iProfesional, «El Peugeot 208 incorpora el motor diésel y una renovada caja automática» (25/10/2017): https://www.iprofesional.com/autos/257674-el-peugeot-208-incorpora-el-motor-diesel-y-una-renovada-caja-de-cambios-automatica
- Vrum (Brasil), cajas automáticas con problemas (AL4) (12/2024): https://www.vrum.com.br/aceleradas/2024/12/7008662-alem-do-powershift-carros-automaticos-famosos-por-darem-problemas-no-cambio.html
- Auto Express (Reino Unido), 208 Mk1 usado: problemas y llamados (06/12/2021): https://www.autoexpress.co.uk/peugeot/208/99371/used-peugeot-208-mk1-2012-2019-problems-recalls
- Parabrisas, lanzamiento del 208 de segunda generación (25/08/2020): https://parabrisas.perfil.com/noticias/novedades/peugeot-208-lanzamiento-argentina-precio-2020-nuevo-2021-210-aniversario.phtml
- L'argus, inicio de producción en El Palomar (26/08/2020): https://www.largus.fr/actualite-automobile/peugeot-208-la-production-a-debute-en-argentine-10399398.html

Dudas:
- **Origen**: el encargo decía «hecho en Palomar», pero las fuentes dicen que la primera generación llegaba importada de Brasil (Porto Real; Autoblog 2013 y Monkey Motor 2016 «viene importado de Brasil»), con XY y GTi de Francia. El Palomar fabrica la segunda generación desde el 31/07/2020 (L'argus). La guía no dice que la primera se hiciera acá.
- **year_to**: puse 2020 (lanzamiento de la segunda generación en agosto de 2020). Puede haber unidades de primera generación patentadas después por stock; el encargo hablaba de 2022.
- **Like**: según Parabrisas 2020 es una versión de la segunda generación (1.2 de 82 CV). No encontré una Like en la primera; quedó solo en `generations`.
- **AL4 en el 208**: que la automática de cuatro sea la AL4 sale de 16Válvulas. La nota de Vrum sobre los problemas de la AL4 nombra 206, 207, C3 y Xsara Picasso, no al 208; la guía lo dice así.
- **Correa o cadena** del 1.5, 1.6 VTi (EC5) y 1.6 THP: no encontré manual del 208 de primera generación (los PDF de peugeot.com.ar dan 404). La guía pide confirmarlo en el manual.
- No encontré llamados a revisión argentinos de la primera generación (sí uno de 2025 para la segunda). Los llamados citados son del Reino Unido y van marcados como otros mercados.
- Fallas del 1.6 THP (cadena, carbonilla) solo aparecen en sitios de poca calidad; no se incluyeron.
- Equipamiento por versión antes del restyling 2016 (2013–2015) no quedó confirmado; los renglones de equipamiento tienen `applies_to` 2016–2017.

Correcciones tras el chequeo de fuentes (11/2026):
- Mantenimiento de la GT/GTi: saqué «el motor turbo pide seguir el plan al pie de la letra» (sin fuente); ahora solo pide las facturas y compararlas con el plan del manual.
- ESP: redactado como «según la prensa» (Monkey Motor lo lista solo en la GT en 2016; 16Válvulas lo marca como falta en 2018) y se pide confirmarlo en la unidad.
- La prueba de Parabrisas de la Tiptronic de cuatro se cita sin año en el texto de la guía, porque la página dice 2019 pero el contenido parece anterior.
- Pantalla táctil y llamados: `applies_to` «otros mercados»; se aclara que son autos fabricados en Europa.
- No se quitó ninguna fuente: las 9 cargan y respaldan algo de la guía.

## Volkswagen Gol G3 y G4 (incluye Gol Power) (1999–2014)

Fuentes:
- Autotest, «Volkswagen Gol: repaso de la historia de un ícono»: https://autotest.com.ar/noticias/volkswagen-gol-repaso-historia-icono/
- Autocosmos, el Gol alcanza las 7 millones de unidades (30/08/2012): https://noticias.autocosmos.com.ar/2012/08/30/volkswagen-gol-alcanza-las-7-millones-de-unidades-producidas
- Autotest, Gol Country, rurales queridas por los argentinos: https://autotest.com.ar/noticias/volkswagen-gol-country-rurales-queridas-argentinos/
- 16 Válvulas, Gol Power con motor 1.4 (24/03/2011): https://www.16valvulas.com.ar/volkswagen-gol-power-con-motor-1-4/
- Car.Blog.BR (Brasil, cita a Autoblog Argentina), Gol G4 1.4 llega a Argentina (15/03/2011): https://www.car.blog.br/2011/03/gol-g4-com-motor-14-chega-argentina-com.html
- Monkey Motor, ficha técnica Gol Power 1.6 (2003): https://www.monkeymotor.net/2024/01/ficha-tecnica-volkswagen-gol-power-16-2003.html
- Autocosmos, recall Gol Power, Fox y Suran 2006–2010 (03/06/2022): https://noticias.autocosmos.com.ar/2022/06/03/recall-para-volkswagen-gol-power-fox-y-suran
- El Economista, llamado de VW por airbags 2006–2018 (18/12/2023): https://eleconomista.com.ar/autos/si-sos-dueno-volkswagen-fabricado-2006-2018-marca-te-esta-buscando-n69427
- Autoblog Uruguay, el Gol deja de ser el más vendido de Brasil (01/2015): https://www.autoblog.com.uy/2015/01/tras-27-anos-el-vw-gol-dejo-de-ser-el.html
- Vrum (Brasil), los 5 defectos crónicos del Gol (04/2026): https://www.vrum.com.br/aceleradas/2026/04/7394191-volkswagen-gol-os-5-maiores-defeitos-cronicos-do-queridinho-do-brasil.html

Dudas:
- **Años**: el catálogo dice 1995–2014. La guía cubre G3 y G4 (1999–2014, años de Autotest); la segunda generación (AB9) y el Gol Trend van solo en `generations`. Para el AB9 usé 1996 como inicio (llegó a fines de 1995 y se vendió masivamente desde 1996).
- **Correa de distribución**: ninguna fuente abierta lo confirma para el AP 1.6 ni el 1.4 (solo blogs de talleres). La guía pide confirmarlo en el manual, igual que el piloto del Gol Trend.
- **Fallas**: termostato, bobina, eléctricas y ruidos salen de una sola nota brasileña (Vrum 2026) y van marcadas «reportes en Brasil». No hay una nota argentina de «usados» del Gol G3/G4 que haya podido abrir.
- **Fin de producción**: Autoblog Uruguay vincula el fin del Gol Power con la obligatoriedad de doble airbag y ABS desde enero de 2014, pero no dice de qué país es la norma. La guía la presenta como «la prensa uruguaya vincula».
- **Versiones del catálogo** (GL, GLD, GLi, GTi, Comfortline, Dublin, Format, Trendline): no encontré fuentes que las ubiquen en G3/G4, así que solo se mencionan Power, Country y la GTI (de la etapa AB9, según Autotest).
- **Potencia del 1.6**: Monkey Motor da 97 CV para el Gol Power 2003 y Autotest/16 Válvulas implican 92 CV para el de los últimos años. La guía atribuye cada cifra a su fuente sin unificarlas.
- Que airbags y ABS fueran opcionales en el 1.4 de 2011 sale de un blog brasileño que cita a Autoblog Argentina.
- GNC: conocimiento general argentino, igual que en el piloto del Gol Trend.

Correcciones tras el chequeo de fuentes (11/2026):
- «Muchas unidades no tienen airbags ni ABS» pasó a «No todas las unidades tienen airbags ni ABS» (la fuente solo dice que eran opcionales en el 1.4 de 2011); igual en checklist y en el «por qué» de la pregunta 2.
- Gol Trend: saqué «con motor transversal» (lo decía una fuente del piloto, no una de esta guía); queda «basada en la plataforma del Fox» (Autocosmos).
- Motores 1.6, 1.8 y 1.9 SD: los atribuí al G3 (1999) tras releer la nota de Autocosmos, que los lista en el párrafo de la tercera generación, no de la segunda.
- La nota de Autoweb sobre las trompas del Gol (usada en el piloto) no se citó: su resumen de fechas argentinas no fue claro.
- No se quitó ninguna fuente: las 10 cargan y respaldan algo de la guía.

## Volkswagen Polo, sexta generación (2018–presente)

Fuentes:
- Autocosmos, lanzamiento del Polo en Argentina (04/01/2018): https://noticias.autocosmos.com.ar/2018/01/04/nuevo-volkswagen-polo-se-lanza-en-argentina
- Autoweb, Polo y Virtus GTS (07/08/2020): https://www.autoweb.com.ar/2020/08/07/volkswagen-lanza-los-polo-y-virtus-gts/
- Autocosmos, Polo Track (01/06/2023): https://noticias.autocosmos.com.ar/2023/06/01/nuevo-vw-polo-track-presentacion-precio-y-equipamiento-en-argentina
- Parabrisas, gama completa del nuevo Polo (03/08/2023): https://parabrisas.perfil.com/noticias/novedades/volkswagen-presento-la-gama-completa-del-nuevo-polo-en-argentina.phtml
- Autocosmos, Polo Comfortline con motor turbo y fin del GTS (12/06/2025): https://noticias.autocosmos.com.ar/2025/06/12/el-vw-polo-comfortline-pasa-al-motor-turbo-en-argentina
- Parabrisas, llamado de VW, Ford y Renault (03/05/2019): https://parabrisas.perfil.com/noticias/novedades/volkswagen-ford-y-renault-llaman-a-revision-a-mas-de-85000-vehiculos.phtml
- Vrum (Brasil), «Volkswagen Polo 2018: 10 fatos» (30/10/2022): https://www.vrum.com.br/bom-negocio/volkswagen-polo-2018-hatch-compacto/
- Volkswagen Argentina, Libro de Servicio Postventa (2017, PDF): https://www.volkswagen.com.ar/idhub/content/dam/onehub_pkw/importers/ar/tengo-un-volkswagen/mantenimiento/Vw_LibroBlanco.pdf

Dudas:
- **Fallas**: agua en faros y habitáculo, tirones de la automática y discos de freno salen de una sola nota brasileña (Vrum). Los tirones son de las versiones turbo de Brasil (200 TSI), que no se vendieron acá antes del restyling; no confirmé si se repiten en el 170 TSI o en el 1.6 MSI automático argentino. Todo queda marcado como «reportes en Brasil».
- **Correa de distribución**: Vrum la lista como repuesto del 1.6 MSI y del TSI (con costo, sin intervalo). El intervalo de 90.000 km es la recomendación general del libro de VW Argentina, no específica del Polo.
- **Llamado de 2019 (pilar B)**: Parabrisas da 29.378 Polo y Virtus y los rangos 9BWAL5BZ*JP001744 a 9BWAL5BZ*KP553823 (hatch) y 9BWDL5BZ*JP016154 a 9BWDL5BZ*KP543170 (sedán); en el texto de Parabrisas el primer número del hatch aparece cortado. No asigna explícitamente cada rango a cada modelo.
- **Versión «MSI» de 2023**: Parabrisas la lista sin detallar motor ni caja; por el nombre sería el 1.6 MSI, pero la guía no lo afirma.
- **year_to**: null, porque sigue a la venta según la nota de 06/2025.
- La versión «Comfortline Plus» de 2018 la nombra Autocosmos como «Confortline Plus».

Correcciones tras el chequeo de fuentes (11/2026):
- Llamado de 2019: saqué «unidades 2018–2019» del `applies_to` y de la pregunta (lo deducía de la letra del año en el VIN; la nota no lo dice). Queda «según chasis (confirmar con el VIN)».
- Restyling: «Track y MSI (1.6 MSI con manual de cinco)» pasó a «Track (1.6 MSI con manual de cinco), una versión MSI», porque Parabrisas no da la mecánica de la MSI.
- Cuatro airbags y control de estabilidad en toda la gama 2023: atribuido a «según la prensa» (Parabrisas; Autocosmos lo confirma para el Track).
- No se quitó ninguna fuente: las 8 cargan y respaldan algo de la guía. Varias notas tienen precios; la guía no los usa.

## Chevrolet Corsa II (2002–2010)

Fuentes:
- Autocosmos, «Autos clásicos de Argentina: Chevrolet Corsa» (08/02/2024): https://noticias.autocosmos.com.ar/2024/02/08/autos-clasicos-de-argentina-chevrolet-corsa
- Autoweb, «Los Chevrolet/Opel Corsa que no tuvimos» (20/10/2021): https://www.autoweb.com.ar/2021/10/20/los-chevrolet-opel-corsa-que-no-tuvimos/
- Parabrisas, «Así hubiera sido el Chevrolet Corsa II rural, si no fuera por Meriva»: https://parabrisas.perfil.com/noticias/novedades/chevrolet-corsa-rural-ii-meriva-argentina-brasil-asi-seria-wagon-suv-proyecto.phtml
- 16 Válvulas, «Corsa y Meriva con caja automática» (12/07/2007): https://www.16valvulas.com.ar/?p=237
- Parabrisas, «Chevrolet Corsa/Classic: récord y despedida» (31/10/2016): https://parabrisas.perfil.com/noticias/general/2016-10-31-chevrolet-corsaclassic-record-y-despedida.phtml
- Autotest, Chevrolet Corsa y Classic usados (08/2022): https://autotest.com.ar/noticias/chevrolet-corsa-classic-usado/
- Oficina Brasil, evaluación del reparador del Corsa (Brasil): https://oficinabrasil.com.br/noticia/avaliacao-do-reparador/chevrolet-corsa-e-de-manutencao-simples-e-barata-na-opiniao-de-quem-lida-com-ele
- Vrum (Brasil), recall de Corsa, Montana, Meriva, S10 y Blazer (24/09/2007): https://www.vrum.com.br/noticias/gm-anuncia-recall-do-corsa-montana-meriva-s10-e-blazer/

Dudas:
- **Elección de generación**: el catálogo tiene «Classic» como modelo aparte (LS, LT, Spirit, hasta 2016), así que la guía «Corsa» cubre el Corsa II, que es el que se vendía como «Corsa» a secas en 2008–2010 (el Corsa Classic, según Autocosmos, llega hasta 2008). Las búsquedas 2011–2014 caen sobre todo en el Classic, que tiene su propia guía. Las versiones del encargo City, Wind, Swing, Super y GSi son del Corsa B/Classic, no del Corsa II; solo se mencionan en `generations` las que nombra Parabrisas (Base, GL, GLS, Sport, City).
- **year_to 2010**: sale de Autocosmos (sedán hasta 2010, hatch hasta 2007). En avisos aparecen Corsa II 2011, pero ninguna fuente lo confirma.
- **Versiones GL, GLS y CD**: solo aparecen en avisos; no abrí una fuente de prensa que detalle el equipamiento de cada una. La guía pide confirmarlo en la unidad.
- No confirmé si el Corsa II vendido en Argentina se fabricó en Rosario o se importó de Brasil (una nota de GM de 2002 hablaba de producción en Rosario, pero theautochannel no cargó).
- Todas las fallas (cajas que pierden aceite, ruido de dirección, suspensión, aire acondicionado) salen de mecánicos citados por Oficina Brasil sobre el Corsa brasileño; van marcadas «reportes en Brasil».
- El recall de bulones de 2007 es de GM do Brasil con rangos de chasis brasileños; no hay confirmación de que alcance a autos argentinos.
- Intervalo de la correa de distribución: ninguna fuente abierta lo da; la guía pide el manual.
- Easytronic: 16 Válvulas da el equipamiento (doble airbag, ABS) para esas versiones; no se sabe si el resto de la gama los traía.
- Fechas del Classic: Autocosmos dice restyling y cambio de nombre en 2009; Autotest dice rediseño profundo en 2011. Se mencionan las dos.

Correcciones tras el chequeo de fuentes (11/2026):
- Saqué «puede haber unidades patentadas más tarde» del Corsa II (ninguna fuente lo dice; mismo criterio que en el Gol Trend).
- Easytronic: «desde julio de 2007 hubo versiones» pasó a «en julio de 2007 se presentaron versiones», porque la nota es de esa fecha y no dice cuándo empezaron las ventas.
- La rural: queda como «no hubo Corsa II rural en la región; la rural era la del Corsa anterior», como dice Parabrisas.
- Frenos traseros: «se gastan más rápido que en el Corsa anterior», como lo dicen los mecánicos de Oficina Brasil, sin generalizar.
- No se quitó ninguna fuente: las 8 cargan y respaldan algo de la guía.

## Volkswagen Saveiro sobre base Gol Trend (G5, G6 y G7) (2010–presente)

Fuentes:
- Autocosmos, lanzamiento de la nueva Saveiro (29/01/2010): https://noticias.autocosmos.com.ar/2010/01/29/nueva-saveiro-diseno-armonia-y-funcionalidad
- Autocosmos, restyling 2013 (03/07/2013): https://noticias.autocosmos.com.ar/2013/07/03/volkswagen-argentina-lanza-la-nueva-saveiro
- Autocosmos, Saveiro Cabina Doble en Argentina (22/11/2014): https://noticias.autocosmos.com.ar/2014/11/22/vw-saveiro-cabina-doble-se-presenta-en-argentina
- Autocosmos, renovación 2016 (24/06/2016): https://noticias.autocosmos.com.ar/2016/06/24/las-volkswagen-saveiro-y-saveiro-cross-se-renuevan-en-argentina
- Autocosmos, gama 2019 (16/05/2018): https://noticias.autocosmos.com.ar/2018/05/16/la-volkswagen-saveiro-se-renueva-en-argentina
- 16 Válvulas, gama 2019 (17/05/2018): https://www.16valvulas.com.ar/?p=154099
- Autoweb, ESP en toda la gama (20/01/2022): https://www.autoweb.com.ar/?p=26843
- Autoweb, renovada gama con ESP y solo 1.6 16v (14/04/2023): https://www.autoweb.com.ar/?p=35338
- Autoweb, rediseño de fines de 2023 (28/12/2023): https://www.autoweb.com.ar/?p=41952
- 16 Válvulas, lanzamiento del rediseño (09/01/2024): https://www.16valvulas.com.ar/?p=224120
- 16 Válvulas, Saveiro Robust cabina doble (Brasil, 02/05/2017): https://www.16valvulas.com.ar/?p=138172
- El Economista, llamado de VW por airbags 2006–2018 (18/12/2023): https://eleconomista.com.ar/autos/si-sos-dueno-volkswagen-fabricado-2006-2018-marca-te-esta-buscando-n69427
- Vrum (Brasil), reclamos de la Saveiro (07/2025): https://www.vrum.com.br/aceleradas/2025/07/7195446-vw-saveiro-veja-as-reclamacoes-da-2-picape-mais-vendida-no-brasil.html

Dudas:
- **Etiquetas G5/G6/G7**: son las del uso común (y del encargo); ninguna fuente abierta las define con años. Los años de `generations` siguen las notas argentinas de lanzamiento (2010, 2013, 2016, fines de 2023).
- **Fallas**: todas salen de una nota brasileña (Vrum) que recoge reclamos de propietarios en Reclame Aqui; no encontré una nota argentina de usados de la Saveiro. Van marcadas «reportes en Brasil».
- **Correa de distribución**: ninguna fuente abierta lo confirma para el 1.6 8v ni para el 1.6 MSI 16v. La guía pide confirmarlo en el manual.
- **Llamados**: solo encontré el de airbags Takata 2006–2018 (que nombra a la Saveiro). No encontré otros llamados de la Saveiro en Argentina.
- **ESP**: Autocosmos 2016 dice que la versión tope tenía ESP sin aclarar si era solo la Cross; para 2019 sí dice que solo la Cross. La fecha exacta en que toda la gama sumó ESP es aproximada («hacia 2022», según Autoweb 2022 y 2023).
- **Robust**: la nota de 16 Válvulas está orientada a Brasil; no confirmé que se vendiera oficialmente en Argentina. La guía lo aclara.
- Airbags y ABS en 2010: la nota los menciona sin decir si estaban en todas las versiones; la guía pide confirmarlos. Desde el restyling de 2013 son de serie (Autocosmos).
- GNC y uso con carga: consejos generales, sin fuente.

Correcciones tras el chequeo de fuentes (11/2026):
- ESP en toda la gama: «Desde 2022» pasó a «Hacia 2022».
- Consumo de aceite: era «casos de consumo»; la nota trae un solo propietario (Saveiro 2017), así que ahora dice eso. La pregunta 4 quedó con pérdidas de aceite.
- Lanzamiento 2010: el doble airbag y ABS quedan como «la nota de lanzamiento menciona... confirmalos en la unidad».
- Ruidos de suspensión: se acotan a los dos reclamos (2017 y 2025) que trae Vrum, sin decir que sean de la Cross.
- No se quitó ninguna fuente: las 13 cargan y respaldan algo de la guía.

## Volkswagen Vento, sexta generación / Jetta VI (2011–2018)

Fuentes:
- 16 Válvulas, versiones del nuevo Vento para Argentina (16/06/2010): https://www.16valvulas.com.ar/?p=14170
- 16 Válvulas, «El Nuevo Volkswagen Vento en nuestras manos» (31/05/2011): https://www.16valvulas.com.ar/?p=31934
- 16 Válvulas, restyling del Vento (11/01/2015): https://www.16valvulas.com.ar/?p=93141
- Autocosmos, Vento GLI en Argentina (08/06/2016): https://noticias.autocosmos.com.ar/2016/06/08/volkswagen-vento-gli-se-lanza-en-argentina
- Autocosmos, Vento 1.4 TSI (30/09/2016): https://noticias.autocosmos.com.ar/2016/09/30/el-volkswagen-vento-14tsi-llega-a-argentina
- Autotest, evolución de los sedanes VW (28/10/2024): https://autotest.com.ar/noticias/evolucion-sedanes-volkswagen-historia/
- Autoweb, historia de Jetta, Bora y Vento (24/09/2018): https://www.autoweb.com.ar/?p=4012
- Volkswagen Argentina, Libro de Servicio Postventa (2017, PDF): https://www.volkswagen.com.ar/idhub/content/dam/onehub_pkw/importers/ar/tengo-un-volkswagen/mantenimiento/Vw_LibroBlanco.pdf
- Auto+ TV (Brasil), DSG en Golf GTI y Jetta GLI (30/08/2025): https://www.automaistv.com.br/curiosidades/volkswagen-golf-gti-e-jetta-gli-o-cambio-dsg-ainda-e-um-problema-explicamos/
- Volkswagen Nueva Zelanda, campaña 35E5 de mecatrónica DQ200: https://volkswagen.co.nz/en/owners-and-servicing/about-my-car/campaigns-and-recalls/mechatronics-unit.html
- Opinautos, «Caja DSG con problemas» del Vento: https://www.opinautos.com/ar/volkswagen/vento/defectos/32896/caja-dsg-con-problemas-repuestos-caros-y-vw-no-los-tiene

Dudas:
- **Generación elegida**: las búsquedas piden 2010–2015 y las versiones del catálogo (Advance, Luxury, Sportline, GLI, Comfortline, Highline) coinciden con el Jetta VI vendido acá. Autotest la fecha 2010–2018; la prueba de 16 Válvulas es de mayo de 2011 y los comentarios hablan de entregas desde abril de 2011, así que usé 2011. Un Vento 2010 probablemente sea de la quinta generación; confirmalo con el auto.
- **Caja de 7 marchas del 1.4 TSI**: Autocosmos dice «doble embrague de 7 relaciones» sin decir si es la DQ200 en seco. La guía pone los reportes de la DQ200 al lado y pide confirmar la caja; no lo afirma.
- **Sportline**: la nota de 2010 la lista solo con caja manual. Hay usadas publicadas como «Sportline DSG», pero no encontré una nota que lo confirme y no lo puse.
- **GLI que reemplaza a la Sportline**: lo dice un resumen de búsqueda de 16 Válvulas que no abrí; la guía no lo afirma.
- **Llamado de resortes de 2019**: incluye un rango de chasis del Vento (3WV**6BU*JM502374 a 3VW**6BU*KM103976, con prefijos distintos en la propia nota) que por la letra del año parece de la séptima generación. No lo puse en esta guía.
- **Correa de distribución**: no confirmé qué motores usan correa o cadena; usé la recomendación general del libro de VW Argentina y se pide confirmar en el manual.
- No encontré fallas documentadas de la Tiptronic del 2.5 ni de los TDI; el checklist de la Tiptronic es genérico.
- Los relatos de Opinautos con modo de emergencia son en su mayoría de Vento 2006–2008 TDI DSG (generación anterior); solo uno es de un 1.4 TSI 2017.

Correcciones tras el chequeo de fuentes (11/2026):
- Pregunta 3: «el síntoma que más describen» pasó a «un síntoma que describen».
- Quinta generación: años 2005–2010 según Autotest, marcados como aproximados.
- Séptima generación: dejé solo lo que dice Autotest (1.4 turbo de 150 CV y GLI 2.0 de 230 CV) y aclaro que no la cubre esta guía.
- Gama 2011: la DSG figura solo en el TDI de 140 CV, como dice la nota de 2010.
- No se quitó ninguna fuente: las 11 cargan y respaldan algo de la guía.
- Relatos de Opinautos: aclaré en el renglón que la mayoría son de la generación anterior y que el del 1.4 TSI 2017 es «letra D parpadeando», no modo de emergencia.

## Chevrolet Onix segunda generación (2020–presente)

Fuentes:
- Autocosmos, lanzamiento de los nuevos Onix y Onix Plus (28/11/2019): https://noticias.autocosmos.com.ar/2019/11/28/nuevos-chevrolet-onix-y-onix-plus-se-lanzan-en-argentina
- Autoweb, «Chevrolet lanza el Onix (hatch y sedán)» (28/11/2019): https://www.autoweb.com.ar/?p=12672
- 16 Válvulas, Onix Premier 1.0 Turbo en Argentina (02/01/2020): https://www.16valvulas.com.ar/?p=178020
- Parabrisas, prueba del Onix Plus Premier II (04/07/2020): https://parabrisas.perfil.com/noticias/test/test-drive-prueba-de-manejo-chevrolet-onix-plus-premier-sedan-compacto.phtml
- 16 Válvulas, Onix LTZ y RS (15/04/2021): https://www.16valvulas.com.ar/?p=195157
- Autoweb, «Todos los Chevrolet Onix vendrán con el motor 1.0 turbo» (22/07/2024): https://www.autoweb.com.ar/?p=46036
- Autoweb, rediseño del Onix en Argentina (24/07/2025): https://www.autoweb.com.ar/?p=53639
- Diario Uno, lanzamiento del Onix Activ (25/07/2026): https://www.diariouno.com.ar/motores/chevrolet-lanzo-argentina-el-nuevo-onix-activ-equipamiento-motorizacion-y-precios-n1578640
- Autocosmos, Onix Plus y Latin NCAP (12/09/2019): https://noticias.autocosmos.com.ar/2019/09/12/nuevo-chevrolet-onix-plus-recibe-la-maxima-calificacion-de-latin-ncap
- Diario de Cuyo, entregas suspendidas en Brasil por riesgo de incendio (07/11/2019): https://www.diariodecuyo.com.ar/economia/Chevrolet-suspendio-la-entrega-del-nuevo-Onix-por-riesgo-de-incendio-ya-se-quemaron-dos-20191107-0003.html
- AutoPapo (Brasil), acción de GM por la correa bañada en aceite (14/03/2025): https://autopapo.com.br/noticia/gm-acao-correia-dentada-banhada-oleo/
- Vrum (Brasil), nueva correia del Onix 2026 (15/08/2025): https://www.vrum.com.br/noticias/2025/08/7227031-onix-2026-nova-correia-dentada-banhada-a-oleo-roda-ate-240-mil-km.html
- Vrum (Brasil), problemas del motor turbo (20/07/2026): https://www.vrum.com.br/mercado/2026/07/7464702-motor-do-onix-turbo-quebra-os-problemas-mais-comuns-e-como-evitar.html
- Cuyo Motor, llegada del Onix en 2013 (07/09/2012): https://cuyomotor.com.ar/2012/09/07/chevrolet-anuncio-la-llegada-a-la-argentina-en-2013-del-onix-2

Dudas:
- **year_from 2020**: se presentó a fines de 2019 (28/11 precios; la Premier en enero de 2020). Usé 2020 como primer año modelo; puede haber unidades 2019.
- **Correa bañada en aceite**: que el 1.0 turbo argentino la usa lo dice 16 Válvulas. Los problemas, la campaña y la correa reforzada 2026 son de Brasil; no encontré campaña ni comunicado de Chevrolet Argentina. No sé si las unidades argentinas 2026 traen la correa nueva.
- **Intervalo de la correa**: AutoPapo y Vrum 2026 dicen 240.000 km (con 15 años en una nota y 10 años en otra). La guía solo cita los 240.000 km como dato de Brasil y pide el manual argentino.
- **Aceite**: Vrum 2026 dice 5W-30 Dexos 1 para el turbo y 0W-20 para los aspirados; otras notas dicen 0W-20 Dexos 1 Gen 2 para el turbo. No puse ninguna especificación: la guía pide la del manual.
- No sé si el 1.2 usa también correa bañada en aceite; la guía lo limita al 1.0 turbo.
- **Onix Joy**: Autocosmos solo dice que seguía a la venta en 2019 junto a la nueva gama; no encontré cuándo empezó ni cuándo terminó (year_from y year_to null).
- **Primera generación**: 2013 sale del anuncio de Cuyo Motor; no abrí una nota del lanzamiento real.
- **Premier I / II**: la diferencia sale de Parabrisas (2020); no sé hasta cuándo se usaron esos nombres (en 2024 la gama ya era LT, LTZ, Premier, RS).
- El recall de software de 2019 es de Brasil y anterior al lanzamiento argentino; la filial dijo que no afectaba el lanzamiento local.

Correcciones tras el chequeo de fuentes (11/2026):
- Campaña de la correa: «GM anunció una campaña» pasó a «GM dijo que preparaba una campaña» (AutoPapo no da fecha de inicio ni lista de modelos), y la correa reforzada quedó como «allí, desde la línea 2026».
- Saqué «la prensa describe su cambio como un trabajo complejo»: la nota de O Mecânico que lo dice no la abrí.
- Garantía: «pedí que el service esté hecho según el plan» pasó a «pedí los comprobantes de service según el plan».
- Onix Joy: saqué «no es la misma plataforma» (ninguna fuente lo dice); ahora dice que es un auto de la generación anterior, como Autocosmos, y year_from pasó a null.
- No se quitó ninguna fuente: las 14 cargan y respaldan algo de la guía. Varias tienen precios; la guía no los usa.

## Fiat Punto (Grande Punto regional) (2007–2017)

Fuentes:
- La Nación, «Fiat Punto ELX 1.4: belleza latina» (28/09/2007): https://lanacion.com.ar/autos/al-volante/fiat-punto-elx-14-belleza-latina-nid947917
- Autocosmos, «Test Fiat Punto 1.4 ELX: pequeño seductor» (21/11/2007): https://noticias.autocosmos.com.ar/2007/11/21/test-fiat-punto-14-elx-pequeno-seductor
- 16 Válvulas, Punto con motor E-torQ 1.6 (08/02/2011): https://www.16valvulas.com.ar/?p=26039
- InfoNegocios, «Fiat incorpora la caja Dualogic al Punto» (06/06/2011): https://infonegocios.info/infoautos/fiat-incorpora-la-caja-dualogic-al-punto
- 16 Válvulas, Nuevo Punto 2013 en Argentina (27/11/2012): https://www.16valvulas.com.ar/?p=59883
- Autocosmos, «Probamos el nuevo Fiat Punto» (29/01/2013): https://noticias.autocosmos.com.ar/2013/01/29/probamos-el-nuevo-fiat-punto
- AutoPapo (Brasil), recall de Linea y Punto por el eje trasero (19/01/2017): https://autopapo.com.br/noticia/atencao-recall-de-linea-e-punto/
- O Mecânico (Brasil), recall Dualogic 2014 (06/01/2015): https://omecanico.com.br/fiat-faz-recall-de-modelos-2014-com-cambio-dualogic/
- Fiat Brasil, manual del propietario Punto 2017 (PDF; plan de mantenimiento en las páginas D-2 y D-3): https://servicos.fiat.com.br/content/dam/fiat/products/handbooks/118/2017/handbook-2017-punto.pdf
- Oficina Brasil, opinión de mecánicos sobre el Punto 1.4 8v (13/04/2015): https://oficinabrasil.com.br/noticia/avaliacao-do-reparador/conheca-os-aspectos-positivos-e-negativos-do-fiat-punto-1-4-8-v-flex-2007-na-hora-da-manutencao
- Agora Motor (Brasil), problemas del Punto (26/03/2025): https://www.motoragora.com.br/?p=170178
- Autocosmos, «Fiat Punto T-Jet: bien deportivo» (27/10/2008): https://noticias.autocosmos.com.ar/2008/10/27/fiat-punto-t-jet-bien-deportivo
- 16 Válvulas, fin del Palio y Siena; el Argo reemplaza al Punto (27/11/2017): https://www.16valvulas.com.ar/?p=147525

Dudas:
- **T-Jet**: no encontré ninguna fuente que confirme que se vendió en Argentina. La guía la menciona como presentada en Brasil (2008) y pide confirmar con documentación y número de motor.
- Intervalo de correa (60.000 km o 3 años, salvo E.torQ con cadena): sale del manual **brasileño** 2017, leyendo la tabla del PDF por columnas (texto extraído con pdftotext). No encontré el manual argentino; la guía pide confirmarlo en el de la unidad. No es seguro que autos 2007–2012 tengan el mismo plan.
- Ninguno de los dos llamados (eje trasero 2009–2012 y actuador Dualogic 2014) aparece en prensa argentina. Los rangos de chasis son brasileños; los Punto argentinos venían de Brasil, pero no hay nada que diga que la campaña se aplicó acá.
- No confirmé si la Dualogic se ofreció con otro motor que el 1.6 E.torQ en Argentina (las fuentes solo la nombran en la Essence).
- Los problemas de la Agora Motor (filtraciones, eléctricos) son de un sitio brasileño de tono genérico sin fuentes propias; quedaron como «reportes en Brasil». El consumo de aceite del 1.8 E.torQ que menciona no aplica: ese motor no se vendió en el Punto argentino según las fuentes.

Correcciones tras el chequeo de fuentes (11/2026):
- Lanzamiento: «septiembre de 2007» (La Nación del 28/09/2007 dice que se presentó días antes), no una fecha exacta.
- Equipamiento 2007: ABS y airbags quedan como opcionales del ELX según Autocosmos y La Nación; no se generaliza a HLX y Sporting.
- 2011: el doble airbag de serie y el ABS opcional se atribuyen a 16 Válvulas y a la Essence; no a toda la gama.
- Restyling 2013: doble airbag + ABS con EBD de serie (paquete HSD) en todas, como dice 16 Válvulas.
- Dualogic: Autocosmos solo critica el «bajón» al pasar de cambio y la falta de fluidez; tirones, dificultad para enganchar y fallas de la central quedaron atribuidos a la prensa brasileña.
- Mecánicos de Oficina Brasil: la bomba de agua se cambia con la correa porque «se daña al retirarla»; saqué cualquier intervalo de correa de esa nota (no lo da).
- Se agregó la nota de 16 Válvulas (2017) para respaldar que el Argo reemplazó al Punto.
- No se quitó ninguna fuente: las 13 cargan y respaldan algo de la guía.

## Volkswagen Bora renovado (restyling 2008) (2008–2015)

Fuentes:
- Autotest, «Usados: Volkswagen Bora 1.9 TDI» (2022): https://autotest.com.ar/noticias/usados-volkswagen-bora-1-9-tdi/
- Autotest, el estado de un Bora abandonado: https://autotest.com.ar/noticias/estado-volkswagen-bora-abandonado/
- Autocosmos, Nuevo Bora 2008: llega la renovación (11/09/2007): https://noticias.autocosmos.com.ar/2007/09/11/nuevo-bora-2008-llega-la-renovacion
- Autocosmos, Nuevo Bora: disfrutar lo sofisticado (01/10/2007): https://noticias.autocosmos.com.ar/2007/10/01/nuevo-bora-disfrutar-lo-sofisticado
- Parabrisas, «Así probábamos el Volkswagen Bora» (prueba de 2000/2001): https://parabrisas.perfil.com/noticias/clasicos/volkswagen-bora-test-argentina-2001-prueba-manejo-retro-motor.phtml
- Autocosmos, se viene el reemplazo del Bora (16/10/2013): https://noticias.autocosmos.com.ar/2013/10/16/se-viene-el-nuevo-volkswagen-bora
- CarsGuide (Australia), problemas del VW Bora: https://www.carsguide.com.au/volkswagen/bora/problems

Dudas:
- **Fallas**: no encontré ninguna fuente argentina sobre fallas del Bora. Caja automática, eléctricas, bobinas, sondas, caudalímetro, correa del 2.0 (cerca de 100.000 km) y lodo por aceite descuidado salen de CarsGuide (Australia), con casos sobre todo de la primera etapa (2001–2005). Todo va marcado «reportes en otros mercados». No está confirmado que el 2.0 australiano sea el mismo motor que el argentino.
- **Años**: elegí el restyling (2008–2015) porque las búsquedas activas piden 2008–2015. Llegó en septiembre de 2007 (año modelo 2008). Autotest dice que se retiró «alrededor de 2014» y convivió con el Vento hasta 2014; dejé `year_to` 2015 por el catálogo y la guía pide confirmar el año modelo.
- **Versiones Trendline / Comfortline / Highline**: las notas de lanzamiento de 2007 nombran las versiones por motor y caja; los nombres Trendline y Highline aparecen solo en avisos de venta, que no cito. No encontré «Comfortline» para el Bora. La guía no los usa.
- **ASR**: la nota de Autocosmos del 11/09/2007 dice control de tracción en todas las versiones; la del 01/10/2007 lo pone solo en el 1.8T. Usé la segunda (más detallada) y la guía pide confirmar el equipamiento.
- **Llamados**: el Bora no figura en las notas del llamado Takata 2006–2018 que leí. Hubo un llamado en México (2020, Bora 2007–2010, unidad de mando, 242 vehículos) que no incluí porque no confirmé que alcance a autos argentinos. La guía solo pide consultar el VIN.
- Correa del 1.8T y del TDI: sin fuente; la guía pide confirmarlo en el manual.

Correcciones tras el chequeo de fuentes (11/2026):
- Tiptronic: saqué «una reparación de la automática es de las más caras» (superlativo sin fuente argentina); ahora pide revisarla antes de comprar.
- Caja automática: se aclara que son reportes de la primera etapa en otro mercado, en vez de «no encontré reportes en Argentina».
- Frente: «aire al Passat de la época» pasó a «parecido al del Passat de la generación anterior», como dice Autocosmos.
- Pregunta 6: el «por qué» ya no dice que ESP y airbags laterales «no figuraban» en las demás versiones (la nota solo no los menciona); ahora dice que eran opcionales del 1.8T.
- No se quitó ninguna fuente: las 7 cargan y respaldan algo de la guía.

## Audi A3 8V (2013–2020)

Fuentes:
- Autocosmos, «Audi lanza el nuevo A3 al mercado argentino» (12/04/2013): https://noticias.autocosmos.com.ar/2013/04/12/audi-lanza-el-nuevo-a3-al-mercado-argentino
- Mega Autos, «El Nuevo Audi A3 ya se comercializa en Argentina» (16/04/2013): https://www.megautos.com/el-nuevo-audi-a3-ya-se-comercializa-en-argentina/
- 16 Válvulas, A3 Sportback en el Salón de Buenos Aires (21/06/2013): https://www.16valvulas.com.ar/?p=69343
- 16 Válvulas, «Probamos el nuevo Audi A3 1.8 TFSI» (05/08/2013): https://www.16valvulas.com.ar/probamos-el-nuevo-audi-a3-1-8-tfsi/
- Parabrisas, «Llegó a la Argentina el Audi A3 Sedán» (28/10/2014): https://parabrisas.perfil.com/noticias/mercado/2014-10-28-llego-a-la-argentina-el-audi-a3-sedan.phtml
- Monkey Motor, Audi A3 2017 (05/04/2017): https://www.monkeymotor.net/2017/04/audi-argentina-a3.html
- Defensa del Consumidor, alerta A3 Sedán 2018 (27/05/2019): https://www.argentina.gob.ar/noticias/alerta-propietarios-de-autos-audi-a3-sedan-y-4x4-ram-1500-y-ram-2500
- km77, cambio DSG de 7 velocidades: https://www.km77.com/coches/volkswagen/tecnica/2008/cambio-dsg-7-velocidades/estandar/informacion
- Fiches Auto (Francia), fiabilidad A3 8V: https://www.fiches-auto.fr/fiabilite-audi/fiabilite-388-pannes-audi-a3.php
- Carbuyer (Inglaterra), A3 2012-2020: https://www.carbuyer.co.uk/reviews/audi/a3/sportback/76459/engines
- Autoweb, A3 8Y en Argentina (16/03/2022): https://www.autoweb.com.ar/?p=27565

Dudas:
- **Nombres de versión**: ninguna nota argentina que abrí usa Attraction, Ambition o S line; las versiones se nombran por motor y caja. Attraction/Sport/S line salen de Autoblog Uruguay 2017 (no citado). RS3: no encontré fuente de venta oficial en Argentina del 8V; no lo mencioné. S3 sí (Monkey Motor 2017).
- **year_to 2020**: ninguna fuente dice cuándo dejó de venderse el 8V; el 8Y llegó en 2022 (Autoweb). Puede haber 8V 2021.
- **Qué caja tiene cada versión**: la prensa dice «S tronic de siete» para 1.4 y 1.8 TFSI, sin decir si es la seca (DQ200). km77 dice que la seca es para hasta 250 Nm; el 1.4 TFSI de 122 CV tiene 200 Nm (16 Válvulas) y el 1.8 TFSI 250 Nm. No afirmé que el 1.8 quattro use la seca; la guía pide confirmar la caja en la unidad.
- Las fallas (mecatrónica, bomba de agua/termostato, pantalla del MMI, ruido del 1.4) salen de reseñas de Francia e Inglaterra con pocos casos por motor (Fiches Auto lo aclara). Todas marcadas «otros mercados».
- No encontré el plan de mantenimiento de Audi Argentina para el 8V; maintenance_costs no da intervalos.
- Los llamados por la DSG en China, Japón y Australia (2013) fueron para A3 fabricados 2008-2011 (8P); no los incluí.
- Autodato (Sportback 2013), MotorMagazine y la página de propietarios de Honest John/Parkers no cargaron (403/402/503).

Correcciones tras el chequeo de fuentes (11/2026):
- Mecatrónica: «cerca de los 80.000 km» pasó a «un cambio de mecatrónica y una falla de caja entre unos 77.000 y 84.000 km», que es lo que cuentan dos propietarios en Fiches Auto.
- Título de la fuente de Autoweb corregido («Audi confirma los equipamientos del nuevo A3»; había puesto el título de otra nota) y la etapa 8Y ahora dice «según Autoweb».
- La 8P queda solo con lo que dicen las notas del 8V (1.8 TFSI de 160 CV); sin años de inicio.
- La versión Sedán de 2014: el equipamiento se atribuye a Parabrisas y se aclara «1.4 TFSI de 122 CV con S tronic de siete», sin decir que no hubo otras.
- No se quitó ninguna fuente: las 11 cargan y respaldan algo de la guía.

## Chevrolet Celta 1.4 (2011–2016)

Fuentes:
- La Nación, «Chevrolet lanzó el Celta» (30/04/2011): https://www.lanacion.com.ar/autos/al-volante/chevrolet-lanzo-el-celta-nid1369188
- 16 Válvulas, presentación del nuevo Celta en Argentina (26/04/2011): https://www.16valvulas.com.ar/?p=29973
- Autocosmos, «El Chevrolet Celta suma una versión con más seguridad» (02/05/2013): https://noticias.autocosmos.com.ar/2013/05/02/el-chevrolet-celta-suma-una-version-con-mas-seguridad
- 16 Válvulas, lanzamiento del Celta MY 2014 con airbags y ABS con EBD (02/05/2013): https://www.16valvulas.com.ar/lanzamiento-chevrolet-celta-my-2014-con-airbags-y-abs-con-ebd-desde-70-300-pesos/
- Autoweb, «Recall para casi 100.000 Chevrolet Classic y Celta» (26/09/2020): https://www.autoweb.com.ar/2020/09/26/recall-para-casi-100-000-chevrolet-classic-y-celta/
- Autocosmos, «Chevrolet Classic y Celta vuelven a ser llamados a revisión» (16/05/2022): https://noticias.autocosmos.com.ar/2022/05/16/chevrolet-classic-y-celta-vuelven-a-ser-llamados-a-revision
- Latin NCAP, Chevrolet Celta sin airbags (2011): https://www.latinncap.com/en/result/11/chevrolet-celta-no-airbags
- Autotest, autos que se vendieron con otra marca en Argentina (Suzuki Fun): https://autotest.com.ar/noticias/dia-del-hermano-5-autos-vendieron-diferente-marca-argentina
- Autoblog Uruguay, lanzamiento del Celta Advantage (09/2014): https://www.autoblog.com.uy/2014/09/lanzamiento-chevrolet-celta-advantage.html
- Oficina Brasil, evaluación del reparador del Celta (Brasil): https://oficinabrasil.com.br/noticia/avaliacao-do-reparador/gm-celta-e-um-velho-conhecido-do-reparador-e-seus-problemas-cronicos-ainda-estao-na-oficina

Dudas:
- **Años**: el catálogo dice 2003–2016, pero en Argentina el Celta se vendió con su nombre desde abril de 2011; entre 2003 y 2011 fue el Suzuki Fun (Autotest). Usé 2011–2016 y el Fun va en `generations`. El año de fin del Fun (2011) sale de que el Celta lo reemplazó en 2011 (La Nación), no de una fecha explícita.
- **year_to 2016**: Autocosmos 2022 habla de modelos 2013 a 2016 en el llamado; Autoweb 2020 dice fabricados hasta abril de 2015. Ninguna fuente da la fecha de fin de venta.
- **Life y Super** (versiones del encargo) no aparecen en ninguna fuente argentina del Celta; parecen del Fun o de Brasil. No las mencioné.
- **Advantage**: solo la confirman avisos argentinos 2014–2015; el equipamiento citado es del lanzamiento en Uruguay. La guía lo dice y pide confirmarlo en la unidad.
- Las fallas de Oficina Brasil no siempre separan por motor y muchas se refieren a los 1.0 brasileños (VHC); el Celta argentino es 1.4. Usé solo las que no dependen del motor (bobina, bieletas, manguera de admisión, aire acondicionado, frenos traseros) y las marqué «reportes en Brasil».
- Intervalo de la correa de distribución: ninguna fuente lo da; la guía pide el manual.
- La prueba de Latin NCAP fue a un Celta fabricado en Brasil sin airbags; no hay prueba publicada de las versiones con airbags.

Correcciones tras el chequeo de fuentes (11/2026):
- Latin NCAP: «la carrocería se calificó como inestable» pasó a «indicó que la estructura no podía soportar más cargas», que es lo que dice la ficha.
- Airbags desde el MY 2014: el «por qué» de la pregunta 2 ahora dice «según la prensa… venían en las versiones más equipadas» (LS de tres puertas y LT de cinco), sin afirmar que las demás no los traían.
- Reemplazo: «en lugar del Suzuki Fun y del Classic de tres puertas», como dice La Nación (16 Válvulas dice Corsa Classic tres puertas).
- Corregí «los bieletas» a «las bieletas».
- No se quitó ninguna fuente: las 10 cargan y respaldan algo de la guía. La nota de 16 Válvulas de 2013 tiene precios en la URL y el texto; la guía no los usa y el título de la fuente se reescribió sin cifras.

## Citroën C4 primera generación, hatchback y sedán argentinos (2007–2014)

Fuentes:
- Autocosmos, «Autos clásicos de Argentina: Citroën C4» (07/03/2024): https://noticias.autocosmos.com.ar/2024/03/07/autos-clasicos-de-argentina-citroen-c4
- La Nación, «Citroën C4, el nuevo auto argentino» (20/04/2007): https://www.lanacion.com.ar/autos/al-volante/citron-c4-el-nuevo-auto-argentino-nid901587
- La Nación, «Citroën C4 Hatchback va por más» (22/08/2008): https://lanacion.com.ar/autos/al-volante/citron-c4-hatchback-va-por-mas-nid1041999
- Autocosmos Chile, «Exclusivo: C4 Sedán, la novedad de Citroën para Sudamérica» (09/05/2007): https://noticias.autocosmos.cl/2007/05/09/exclusivo-c4-sedan-la-novedad-de-citroen-para-sudamerica
- Autocosmos, ficha C4 Hatchback 2.0 Exclusive: https://www.autocosmos.com.ar/catalogo/comparar?v1=152106
- Autocosmos, ficha C4 2.0i Exclusive BVA: https://www.autocosmos.com.ar/catalogo/comparar?v1=152098
- Vrum (Brasil), cajas automáticas con problemas (AL4) (12/2024): https://www.vrum.com.br/aceleradas/2024/12/7008662-alem-do-powershift-carros-automaticos-famosos-por-darem-problemas-no-cambio.html
- Autoweb, «Citroën también llama a revisión por los airbags defectuosos» (29/09/2020): https://www.autoweb.com.ar/?p=17721

Dudas:
- **C4 Pallas**: según Autocosmos Chile (2007), el nombre Pallas era solo para Brasil; en Argentina el sedán se vendió como «C4 Sedán» (Autocosmos AR). Si el catálogo tiene un modelo «C4 Pallas» aparte, corresponde a la grafía brasileña; esta guía cubre hatch y sedán argentinos porque comparten motores y equipamiento.
- **Años**: el catálogo dice 2006–2013, pero la producción argentina empezó con el sedán en 2007 (abril) y el hatch en 2008 (agosto); Autocosmos da sedán 2007–2013 y hatch 2008–2014. Usé 2007–2014. No encontré evidencia de un C4 importado en 2006 salvo el C4 Coupé VTS de Francia (sin fecha exacta).
- **Versiones X, SX, Exclusive, Tendance, VTR**: solo la Exclusive aparece en una fuente abierta (fichas de Autocosmos, sin año modelo). X y SX solo en avisos; Tendance y VTR no aparecieron. La guía no describe su equipamiento y pide confirmarlo en la unidad.
- **AL4**: ninguna fuente abierta dice explícitamente que la automática de cuatro del C4 sea la AL4; la ficha dice «automática secuencial 4 velocidades». La guía cita la AL4 como la automática de cuatro de PSA en otros modelos y pide confirmar qué caja lleva.
- Fallas propias del C4 argentino (eléctricas, dirección, refrigeración) solo aparecieron en foros de dueños o sitios de repuestos británicos; no se incluyeron. Las reseñas británicas de calidad (What Car) no se pudieron abrir.
- Correa de distribución de 1.6, 2.0 y 2.0 HDi: sin manual abierto; la guía pide confirmarlo en el manual.
- No encontré llamados a revisión argentinos de esta generación.

Correcciones tras el chequeo de fuentes (11/2026):
- «Motores fabricados para el C4 argentino» pasó a «motores del C4 argentino según Autocosmos».
- Saqué «adonde se exportaba» del renglón del sedán: la exportación a Brasil como Pallas salía de un resumen de búsqueda, no de una fuente abierta.
- «Terminó vendiéndose más que el sedán» pasó a «según Autocosmos, el público terminó prefiriéndolo», que es lo que dice la nota.
- Llamado por airbags 2020: se aclara que nombra al C4 Lounge desde 2013 y no a esta generación; no se afirma que no la alcance.
- Se descartó la nota de prensa de Citroënet (2007) para no duplicar lo que ya respalda La Nación.
- No se quitó ninguna fuente de las 8 listadas.

## Fiat Palio primera generación (proyecto 178) y restylings (1996–2017)

Fuentes:
- Autotest, «Retro test: Fiat Palio HLX 1.8 2004» (04/11/2019): https://autotest.com.ar/noticias/retro-test-fiat-palio-hlx-1-8-2004/
- Autocosmos, «Nuevo Palio 2008: todo nuevo» (19/04/2007): https://noticias.autocosmos.com.ar/2007/04/19/nuevo-palio-2008-todo-nuevo
- La Nación, «Fiat volvió a fabricar el Palio en el país» (25/06/2008): https://www.lanacion.com.ar/economia/fiat-volvio-a-fabricar-el-palio-en-el-pais-nid1024495
- 16 Válvulas, primer Palio producido en Córdoba (24/09/2008): https://www.16valvulas.com.ar/?p=5685
- Autocosmos, estrategia del Nuevo Palio en Argentina para 2012 (16/11/2011): https://noticias.autocosmos.com.ar/2011/11/16/la-estrategia-del-nuevo-fiat-palio-en-argentina-para-2012
- Autoblog Uruguay, fin de producción del Palio (15/12/2017): https://www.autoblog.com.uy/2017/12/tramites-jubilatorios-fiat-dejo-del.html
- 16 Válvulas, despedida de Palio, Palio Fire y Siena EL (27/11/2017): https://www.16valvulas.com.ar/?p=147525
- Los Andes, qué mirar en un Palio usado (2026): https://www.losandes.com.ar/automotores/que-mirar-un-fiat-palio-usado-antes-comprarlo-y-no-caer-un-gasto-taller-n5993680
- 16 Válvulas, campaña Takata de Stellantis Argentina (27/02/2026): https://www.16valvulas.com.ar/airbags-defectuosos-stellantis-argentina-continua-con-el-recall-que-afecta-a-varios-modelos-de-fiat-citroen-ds-jeep-chrysler-dodge-y-ram/
- 16 Válvulas, recall FCA Argentina de airbags 2014 (02/04/2021): https://www.16valvulas.com.ar/fca-argentina-anuncio-un-recall-para-los-fiat-uno-fiorino-palio-y-grand-siena/
- Agora Motor (Brasil), problemas del Palio (25/03/2025): https://www.motoragora.com.br/?p=170204
- Autocosmos, Palio Weekend 2009 (22/08/2008): https://noticias.autocosmos.com.ar/2008/08/22/palio-weekend-2009-nueva-facha-y-equipamiento

Dudas:
- Alcance: el catálogo junta 1996–2017 bajo «Palio». La guía cubre el Palio del proyecto 178 (original, restylings y Palio Fire hasta 2017) y trata el Nuevo Palio (326, 2012–2017) y la Palio Weekend como modelos aparte, mencionados en una línea cada uno. Si el catálogo los separa, habría que hacer guías propias.
- Años de las etapas: las fuentes no coinciden. Autoblog Uruguay habla de actualizaciones en 2000, 2003, 2007 y 2010; Autotest menciona el restyling de 2001 y prueba un 2004. Usé 2001–2006 y 2007–2011 en `generations`, aproximados.
- Producción en Córdoba: La Nación dice 1997–2001 y reinicio de la planta en enero de 2008; 16 Válvulas fecha el primer Palio hecho íntegramente allí en septiembre de 2008. Entre 2002 y 2008 no está documentado de dónde venían los Palio que se vendían en Argentina (no lo afirmo).
- Intervalo de correa: no encontré el manual argentino del Palio Fire; Los Andes solo da el service cada 10.000 km y que hay reemplazos por tiempo. La guía pide confirmarlo en el manual.
- Campaña Takata (Palio fabricados 2012–2018) y recall 2014: las notas dicen «Palio» sin separar Fire de Nuevo Palio. La guía pide consultar el VIN.
- No incluí la Dualogic ni el diésel: no encontré fuentes argentinas de que se vendieran en el Palio del proyecto 178 de esos años.

Correcciones tras el chequeo de fuentes (11/2026):
- ABS: se apoya en Autotest (HLX 2004 sin ABS, con doble airbag) y en Autocosmos (Weekend 2009, airbags y ABS opcionales); saqué «sobre todo 2004–2011».
- Saqué la inferencia «hubo años de unidades importadas» de la línea de La Nación, porque la nota no lo dice.
- 2008: «el primer Palio hecho íntegramente en Córdoba en septiembre de 2008, ELX 1.4 nafta para Argentina» (16 Válvulas), en vez de «entre las primeras unidades».
- Palio Weekend: se precisó modelo 2009, ELX y Trekking, 1.4 Fire de 82 CV.
- Cuarta generación: `year_from` 2007 (lanzada en abril de 2007 según Autocosmos), y la Fire con «la carrocería de la tercera generación».
- Fin: «terminó a fines de 2017 y lo reemplazó el Argo» (Autoblog Uruguay, 16 Válvulas); no se afirma 2018.
- Los reclamos de la Agora Motor que dependen del etanol (arranque en frío, bomba de combustible) no se usaron porque no aplican al uso argentino.
- No se quitó ninguna fuente: las 12 cargan y respaldan algo de la guía.

## Ford Maverick primera generación (2022–presente)

Fuentes:
- Parabrisas, presentación en Argentina (04/11/2021): https://parabrisas.perfil.com/noticias/novedades/ford-maverick-argentina-presentacion-pick-up-compacta-versiones-2022.phtml
- Autoweb, lanzamiento en Argentina (15/02/2022): https://www.autoweb.com.ar/?p=27313
- Autotest, Maverick híbrida (22/05/2023): https://autotest.com.ar/lanzamientos/nueva-ford-maverick-hibrida/
- Autocosmos, restyling y Tremor (23/04/2025): https://noticias.autocosmos.com.ar/2025/04/23/ford-maverick-renovacion-precio-y-nueva-variante-offroad-en-argentina
- Autocosmos, recall en EE.UU. por el tablero (05/03/2024): https://noticias.autocosmos.com.ar/2024/03/05/recall-para-la-ford-maverick-en-eeuu-por-una-falla-en-el-tablero
- Infonegocios, Ford Argentina llama a revisión Maverick y Bronco Sport (17/06/2026): https://infonegocios.info/default/ford-llama-a-revision-a-maverick-y-bronco-sport-recomienda-no-usar-las-unidades-afectadas
- Infonegocios, recall de Ford en Argentina, cinco modelos (27/03/2026): https://infonegocios.info/default/recall-de-ford-en-argentina-cinco-modelos-afectados-y-llamados-a-revision
- Shelby County Today, recall 26S36 / NHTSA 26V340 (08/06/2026): https://scttx.com/node/50517
- Kelley Blue Book, recall repetido de luces traseras (28/02/2025): https://www.kbb.com/car-news/ford-maverick-recalled-again-for-failing-tail-lights

Dudas:
- **Recall de rótulas en Argentina**: Infonegocios no da años ni rangos de chasis, y el titular dice «recomienda no usar las unidades afectadas» pero el cuerpo no; la indicación de no usarla quedó solo para EE.UU. (Ford 26S36). No encontré el aviso oficial de Ford Argentina.
- **Recall de marzo de 2026**: la nota no dice qué falla tiene la Maverick; la guía solo pide consultar campañas.
- **Caja de la híbrida 2023**: Autotest dice e-CVT y Autoweb (misma fecha) dice automática de ocho marchas; usé e-CVT. La potencia de la híbrida 2025 difiere entre fuentes (196 CV en Autocosmos); no la puse.
- **Tracción de la XLT 2022**: Autoweb dice delantera y Parabrisas dice trasera; la guía dice «tracción simple».
- **Garantía del sistema híbrido** (8 años o 160.000 km): solo la encontré para el modelo 2025.
- No encontré el plan de mantenimiento oficial de Ford Argentina ni fallas mecánicas reportadas en Argentina.
- No hubo una XL ni una Tremor antes de 2025 en Argentina según las fuentes.

Correcciones tras el chequeo de fuentes (11/2026):
- Pregunta de services: el «por qué» ya no dice que hacerlos en concesionario mantiene la garantía (ninguna fuente lo dice); ahora es para saber si se siguió el plan y consultar la garantía.
- Recalls de EE.UU. (rótulas, tablero, luces traseras) marcados como otros mercados; el del tablero cita que Ford no había reportado la falla en Argentina.
- Lariat FX4: el contenido del paquete sale de Parabrisas, que no dice en qué versión iba; Autoweb lo ubica en la Lariat.
- No se quitó ninguna fuente: las 9 cargan y respaldan algo de la guía.

## Honda City quinta generación (2009–2015)

Fuentes:
- Autocosmos, «Honda City a la venta en Argentina» (18/11/2009): https://noticias.autocosmos.com.ar/2009/11/18/honda-city-a-la-venta-en-argentina
- Autocosmos, «Honda City, ahora made in Argentina y con rediseño» (04/06/2012): https://noticias.autocosmos.com.ar/2012/06/04/honda-city-ahora-made-in-argentina-y-con-rediseno
- Autocosmos, llamado a revisión de Honda (21/02/2018): https://noticias.autocosmos.com.ar/2018/02/21/importante-llamado-a-revision-de-honda-en-argentina
- Autocosmos, recall de Honda Argentina para autos y motos (30/08/2023): https://noticias.autocosmos.com.ar/2023/08/30/recall-de-honda-argentina-para-autos-y-motos
- El Cronista, airbags de 50.000 autos (18/02/2020): https://www.cronista.com/autos/honda-llama-a-revisar-airbags-de-50000-autos-en-argentina-por-los-que-en-brasil-murio-un-conductor
- Autotest, «City y HR-V, un breve paso por Campana» (2020): https://autotest.com.ar/noticias/video-city-y-hr-v-un-breve-paso-por-campana/
- Autoweb, «Tras nueve años, Honda dejó de producir autos en Campana» (2020): https://www.autoweb.com.ar/?p=15437
- Autoweb, «Debuta en Brasil el nuevo Honda City, que no llegará a la Argentina»: https://www.autoweb.com.ar/?p=25819
- Oficina Brasil, «Honda City possui defeitos recorrentes» (04/2014): https://oficinabrasil.com.br/noticia/avaliacao-do-reparador/honda-city-possui-defeitos-recorrentes-mas-principal-reclamacao-sao-as-informacoes-tecnicas

Dudas:
- **Generación**: el encargo sugería la 5ª (2009/2010–2014) y/o la 6ª (2014–2020). Según Autotest y Autoweb, la 6ª y la 7ª se hicieron en Brasil y no se vendieron oficialmente en Argentina; el City argentino es una sola generación, 2009–2015 (importado de Brasil hasta 2011, hecho en Campana desde 2011, rediseño 2012). La búsqueda activa (2010–2016) queda cubierta salvo 2016.
- **Fin**: Autotest dice que la HR-V lo reemplazó en la línea en abril de 2015 y que terminó la venta; Autoweb da la producción 2011–2014. Usé year_to 2015.
- **Versión EX**: el catálogo lista LX, EX y EXL. Las notas que abrí solo nombran LX y EX L/EXL. Un resultado de 16 Válvulas (no abierto, verificación anti-bot) menciona «EX y EXL». La guía lo dice y pide comparar con el equipamiento.
- No encontré el plan de mantenimiento oficial (el PDF del manual de Honda Brasil devolvió «Access Denied»). No afirmo correa ni cadena para el 1.5.
- Regulación de válvulas a los 40.000 km, desgaste de embrague y frenos y barro en el motor salen de un solo mecánico en Oficina Brasil, sobre un City flex 2011 brasileño. Marcados como «reportes en Brasil». Dejé fuera lo de filtro de combustible y bujías porque el mecánico lo vincula sobre todo al uso de etanol.
- Cantidad de marchas de la caja manual: ninguna fuente abierta la da; no la puse.

Correcciones tras el chequeo de fuentes (11/2026):
- `generations`: saqué «la sexta generación (2015, con caja CVT)»: la CVT para el City brasileño sale de resultados de búsqueda que no abrí (la nota de Autocosmos 2013 habla del lanzamiento en India). Ahora dice solo que las dos generaciones posteriores se hicieron en Brasil y no se vendieron acá.
- Saqué «un City 2016 en adelante sería importado por otra vía» (especulación); ahora pide confirmar año y origen en la documentación.
- Llamado Takata: la cifra de pendientes se atribuye a 2023 y a todos los modelos Honda (48.000 de 121.000), no al City.
- ABS: «en 2009 la prensa lo menciona en la EX L» (Autocosmos 2009 no lo lista en la LX) y desde 2012 en ambas versiones.
- No se quitó ninguna fuente: las 9 cargaron y respaldan algo de la guía.

## Honda HR-V segunda generación, Campana y México (2015–2022)

Fuentes:
- Cuyo Motor, «La Honda HR-V se lanza a la venta en junio» (15/04/2015): https://cuyomotor.com.ar/2015/04/15/la-honda-hr-v-se-lanza-a-la-venta-en-junio
- Autotest, prueba HR-V EXL 2015: https://autotest.com.ar/pruebas/honda-hr-v-exl-2015/
- Autocosmos, nueva versión EX (12/02/2016): https://noticias.autocosmos.com.ar/2016/02/12/honda-hr-v-una-nueva-version-se-lanza-en-argentina
- Autocosmos, recall HR-V y Accord (03/12/2018): https://noticias.autocosmos.com.ar/2018/12/03/honda-hr-v-y-accord-a-recall-en-argentina
- Parabrisas, «Honda HR-V: cómo es la línea 2019» (22/01/2019): https://parabrisas.perfil.com/noticias/general/2019-01-22-honda-hr-v-como-es-la-linea-2019.phtml
- Autotest, «Nuevo restyling para la HR-V» (21/01/2019): https://autotest.com.ar/lanzamientos/nuevo-restyling-para-la-hr-v/
- Autoweb, fin de la producción en Campana (2020): https://www.autoweb.com.ar/?p=15437
- Autoweb, «Honda lanza la HR-V mexicana» (05/05/2021): https://www.autoweb.com.ar/?p=21735
- Autoweb, «Honda lanza la nueva HR-V en la Argentina» (31/10/2023): https://www.autoweb.com.ar/?p=40858
- Samarins, Honda HR-V 2016-2022 (reseña norteamericana): https://www.samarins.com/reviews/honda-hr-v-2016.html

Dudas:
- **Nombre de la generación**: el encargo dice «primera generación»; Autoweb (2023) llama a la de Campana «segunda generación» y a la de 2023 «tercera» (cuenta la HR-V japonesa de 1998). Usé «Segunda generación (Campana y México)».
- **year_to 2022**: la mexicana se lanzó en mayo de 2021 y la tercera generación llegó en octubre de 2023. No confirmé hasta cuándo se vendió la mexicana; dejé 2022 como pide el encargo y lo marco como aproximado.
- **EX al lanzamiento**: Cuyo Motor (04/2015) anunciaba LX, EX y EXL «como en Brasil», pero Autocosmos (02/2016) presenta la EX como nueva. La guía toma la fecha de Autocosmos.
- **EXT**: está en el catálogo, pero no encontré ninguna nota que la nombre para Argentina.
- Fallas de CVT, tensor de la correa auxiliar, rodamientos, pérdidas de aceite y extensión de cobertura de la CVT salen de Samarins (EE.UU.). Marcado «reportes en otros mercados»; no hay nada equivalente informado en Argentina. Ojo: la HR-V mexicana importada desde 2021 podría compartir más con la norteamericana, pero no lo confirmé.
- Recalls de bomba de combustible: hubo en EE.UU., México y Brasil, pero no encontré uno de Honda Argentina para la HR-V; no lo incluí.
- El HR-V no figura en el llamado Takata de Honda Argentina (Autocosmos 2023).
- No encontré el plan de mantenimiento oficial argentino. Cadena de distribución: Autotest (prueba 2015). Aceite 0W-20: Samarins (motor norteamericano).

Correcciones tras el chequeo de fuentes (11/2026):
- «La CVT es la pieza cara del auto» pasó a «una pieza cara de reparar» (ninguna fuente la compara con otras piezas).
- El «por qué» de la pregunta del fluido de la CVT ahora atribuye a la reseña norteamericana que el cambio ayuda a que dure.
- Restyling 2019: las llantas de 17 «de nuevo diseño» sin asignarlas a una versión, porque Parabrisas no las detalla por versión.
- Extensión de cobertura de la CVT: aclarado que es para HR-V 2016-2020 del mercado de EE.UU.
- No se quitó ninguna fuente: las 10 cargaron y respaldan algo de la guía.

## Kia K3 primera generación, importado de México (2025–presente)

Fuentes:
- Parabrisas, «Kia ya vende el nuevo K3 en la Argentina» (26/03/2025): https://parabrisas.perfil.com/noticias/novedades/kia-ya-vende-el-nuevo-k3-en-la-argentina.phtml
- Autocosmos, equipamiento por versión (27/03/2025): https://noticias.autocosmos.com.ar/2025/03/27/nuevo-kia-k3-equipamiento-por-version-en-argentina
- Autoweb, «Kia lanza el K3 en Argentina» (26/03/2025): https://www.autoweb.com.ar/2025/03/26/kia-lanza-el-k3-en-argentina/
- Autotest, llamado a revisión del K3 Hatchback por el cinturón (10/2026): https://autotest.com.ar/noticias/kia-llamo-a-revision-a-mas-de-3-400-k3-hatchback-por-una-posible-falla-en-el-cinturon-de-seguridad/
- Autotest, precios y versiones en agosto de 2026: https://autotest.com.ar/noticias/no-aumenta-desde-su-lanzamiento-precios-y-versiones-del-kia-k3-en-agosto-2026/
- Autoblog Uruguay, Latin NCAP cinco estrellas (15/10/2024): https://www.autoblog.com.uy/2024/10/latin-ncap-el-kia-k3-logra-las-primeras.html

Dudas:
- **Años**: el encargo dice 2024–presente; la venta en Argentina empezó en marzo de 2025 (Parabrisas, Autoweb). Usé year_from 2025. Las primeras unidades del hatch del llamado se fabricaron desde 09/2024, así que puede haber autos con año de fabricación 2024.
- **Versiones**: el catálogo lista LX, EX, SX y GT Line; la prensa argentina (2025 y 08/2026) solo nombra EX y GT-Line, en sedán y Cross. La guía lo dice.
- **Equipamiento en conflicto**: Autoweb pone sensor de punto ciego en la EX; Autocosmos lo pone solo en la GT-Line (con alerta de tráfico cruzado y presión de neumáticos). La guía pide comprobarlo en la unidad.
- Torque: 151 Nm (Parabrisas, Autoweb, Autotest) o 157 Nm (Autocosmos). Potencia 121 CV (122 en Autotest 2026).
- No encontré plan de mantenimiento oficial argentino ni condiciones de transferencia de la cobertura de 5 años o 100.000 km.
- El llamado del cinturón: la nota de Autotest (29/10/2026) nombra la «versión BL7m» y no da un modo de consulta por VIN.
- Trayectoria muy corta: no hay fallas conocidas de largo plazo; la guía lo dice explícitamente.

Correcciones tras el chequeo de fuentes (11/2026):
- «La cobertura suele depender de cumplir el plan de services» (sin fuente) pasó a pedir que se confirme qué services pide Kia.
- Pregunta sobre choques: saqué que los sensores «pueden necesitar calibración» (sin fuente); queda que las asistencias usan cámaras y sensores.
- Latin NCAP: se agrega la debilidad que señaló (zona de los pies en el choque frontal) y que el resultado vale para sedán y hatch.
- No se quitó ninguna fuente: las 6 cargaron y respaldan algo de la guía.

## Mercedes-Benz Clase C W204 (2007–2015)

Fuentes:
- Autocosmos, «Llegó la nueva Clase C de Mercedes-Benz» (03/07/2007): https://noticias.autocosmos.com.ar/2007/07/03/llego-la-nueva-clase-c-de-mercedes-benz
- 16 Válvulas, Mercedes BlueEfficiency y CGI en Argentina (16/05/2010): https://www.16valvulas.com.ar/?p=13274
- Autoblog Uruguay, restyling de la Clase C (08/06/2011): https://www.autoblog.com.uy/2011/06/lanzamiento-mercedes-benz-clase-c.html
- Cuyo Motor, C 200 BlueEfficiency Manual City (19/07/2012): https://cuyomotor.com.ar/2012/07/19/nuevo-clase-c-el-modelo-mas-economico-de-mercedes-benz
- 16 Válvulas, W205 a la venta en Argentina (18/05/2015): https://www.16valvulas.com.ar/?p=100244
- Autoweb, restyling del W205 (07/10/2019): https://www.autoweb.com.ar/?p=11730
- Autoweb, recall Takata de Mercedes en Argentina (11/08/2023): https://www.autoweb.com.ar/?p=38955
- Defensa del Consumidor, Clases C y GLK (02/05/2018): https://www.argentina.gob.ar/node/109813
- Auto.ru (Rusia), fiabilidad del W204 restyling (03/06/2021): https://auto.ru/mag/article/merccklassew204restyledurability/
- Kolesa.ru (Rusia), W204 usado: carrocería, interior y electricidad (23/04/2020): https://www.kolesa.ru/article/mercedes-benz-c-klasse-w204-s-probegom-tonkoe-lkp-bednyy-salon-i-kovarnyy-blokirator-rulya
- CarsGuide (Australia), C-Class usado 2007-2013 (2016): https://www.carsguide.com.au/car-reviews/mercedes-benz-c-class-used-review-2007-2013-41790

Dudas:
- **year_to 2015** (el encargo sugería 2014): el W205 recién se vendió en Argentina desde el 18/05/2015 (16 Válvulas), y el recall Takata habla de Clase C 2007 a 2015. Puede haber W204 2015; la guía lo aclara.
- **C180 y C63 AMG**: no encontré fuente argentina del W204; el C 180 figura en Uruguay (2011). No los mencioné.
- **Restyling 2011 en Argentina**: no abrí una nota argentina del lanzamiento. Los cambios y el reemplazo de la automática de cinco por la 7G-Tronic Plus salen de Uruguay; la guía lo marca.
- El llamado de 2018 (argentina.gob.ar) no nombra la serie; Unidiversidad (12/03/2018, no citada) dice «serie W204». Lo puse como «Clase C (serie W204) y GLK» porque la pregunta del VIN lo resuelve.
- Fallas mecánicas (7G-Tronic, cadena M271, M276, dirección, SAM, bloqueo de columna) salen de prensa rusa basada en talleres, marcadas «otros mercados». El intervalo de 40.000 km del aceite de la caja es recomendación de esa nota, no de Mercedes.
- El intervalo de service (25.000 km o un año) es de Australia.
- Parkers y la segunda parte de Kolesa (motores) no cargaron o no se abrieron.

Correcciones tras el chequeo de fuentes (11/2026):
- Saqué «menos de lo que suele figurar en planes de fábrica» del aceite de la 7G-Tronic: ninguna fuente lo dice.
- Arranque en frío: saqué «ruido metálico de cadena»; queda como ruidos metálicos para que los revise un mecánico.
- Cadenas y presión de aceite del V6: `applies_to` aclara que es el M276 del restyling (la nota de Auto.ru es del 2011-2015); los 350 de 2007/2010 no tienen ese motor confirmado.
- 2007: «caja manual de seis en casi todas» pasó a «la manual de seis era de serie salvo en el C 350; la lista también incluía versiones automáticas», como dice Autocosmos.
- Autoweb ?p=11730 resultó ser el restyling del W205 (2019), no el del W204: se usa solo para la etapa W205.
- No se quitó ninguna fuente: las 11 cargan y respaldan algo de la guía.

## Renault Clio II y Clio Mío (2000–2016)

Fuentes:
- Autotest, «Renault Clio II usado: 5 aspectos que tenés que saber» (05/07/2022): https://autotest.com.ar/noticias/usados-renault-clio-segunda-generacion/
- 16Válvulas, «El Renault Clio argentino se despidió después de 20 años» (01/11/2016): https://www.16valvulas.com.ar/el-renault-clio-argentino-se-despidio-despues-de-20-anos/
- Autocosmos, presentación industrial del Clio Mío (15/11/2012): https://noticias.autocosmos.com.ar/2012/11/15/renault-clio-mio-presentacion-industrial
- Autoblog Uruguay, «Prueba: Renault Clio Mío Pack 1.2, parte 1» (05/2013): https://www.autoblog.com.uy/2013/05/prueba-renault-clio-mio-pack-12-parte-1.html
- Autoweb, «Prueba: Renault Clio Mío Expression Pack I» (01/12/2012): https://www.autoweb.com.ar/?p=9838
- 16Válvulas, «Renault Clio Mío, versiones, equipamiento y precios»: https://www.16valvulas.com.ar/renault-clio-mio-versiones-equipamiento-y-precios/
- 16Válvulas, Clio Mío con tres estrellas Latin NCAP (13/01/2014): https://www.16valvulas.com.ar/?p=78050
- Autocosmos, Latin NCAP retira las tres estrellas al Clio (24/06/2015): https://noticias.autocosmos.com.ar/2015/06/24/latin-ncap-retira-las-tres-estrellas-de-seguridad-al-renault-clio
- Parabrisas, «El más equipado» (Clio Mío Dynamique, 14/11/2014): https://parabrisas.perfil.com/noticias/mercado/2014-11-14-el-mas-equipado.phtml

Dudas:
- **Alcance**: la guía trata al Clio Mío como parte del Clio II porque la prensa lo describe como «un Clio II rediseñado» (Autoblog) y 16Válvulas lo cuenta como etapa del mismo Clio argentino. Años 2000–2016 (Clio II desde 2000; fin de producción en 2016). El encargo hablaba de búsquedas 2007–2014.
- **Versiones del catálogo** Pack, Pack Plus, Privilège, Confort, Dynamique, Authentique, Expression: Autotest confirma Authentique/Expression/Privilège (2003) y Dynamique/Confort/Luxe (2006); 16Válvulas y Parabrisas, variantes Pack y Confort Plus/Dynamique del Mío. «Pack Plus» no apareció en ninguna fuente abierta.
- **Airbags y ABS en el Mío**: las pruebas de 2012 (Autoweb, Argentina) y 2013 (Autoblog, Uruguay) dicen que no los tenía; Parabrisas 2014 lista doble airbag y ABS en la Dynamique, y Autocosmos 2015 dice que el doble airbag ya era obligatorio en Argentina. No quedó confirmada la fecha exacta en que pasaron a ser de serie.
- **Correa de distribución** del 1.2 16v (D4F) y demás motores: solo aparecieron blogs de talleres con intervalos que no coinciden entre sí; la guía pide confirmarlo en el manual.
- Las fallas citadas (burletes, contrapuertas, embrague, pomo de la caja, inyección diésel, repuestos caros) salen todas de una sola nota (Autotest 2022), centrada en el Clio II; no está confirmado que valgan igual para el Clio Mío, por eso llevan `applies_to` «Clio II».
- La guía de Mercado Libre sobre óxido en portón y zócalos devolvió 403; no se usó. No encontré llamados a revisión argentinos del Clio II ni del Mío.

Correcciones tras el chequeo de fuentes (11/2026):
- «Los primeros Clio Mío no tenían airbags ni ABS en ninguna versión» pasó a «según las pruebas de 2012 y 2013, los primeros Clio Mío no tenían airbags ni ABS».
- Saqué «en tres y cinco puertas» del renglón del Clio Mío: salía de un resumen de búsqueda, no de una fuente abierta.
- Latin NCAP: se aclara que las tres estrellas son para adultos (2014) y que el cero fue sin airbags (2013).
- El embrague en mantenimiento se presenta como «la prensa señala», con `applies_to` Clio II.
- No se quitó ninguna fuente: las 9 cargan y respaldan algo de la guía.

## Renault Kardian primera generación (2024–)

Fuentes:
- Autoweb, «Renault lanza el Kardian en Argentina» (15/08/2024): https://www.autoweb.com.ar/2024/08/15/renault-lanza-el-kardian-en-argentina/
- Autoweb, «Renault actualiza la gama del Kardian en Argentina» (20/08/2025): https://www.autoweb.com.ar/2025/08/20/renault-actualiza-la-gama-del-kardian-en-argentina/
- Autoweb, «Prueba: Renault Kardian 1.0 Premiere Edition» (01/11/2024): https://www.autoweb.com.ar/2024/11/01/prueba-renault-kardian-1-0-premiere-edition/
- Autotest, test drive del Kardian: https://autotest.com.ar/pruebas/renault-kardian-test-drive/
- 16 Válvulas, plataforma, motor 1.0 TCe y caja EDC: https://www.16valvulas.com.ar/?p=229408
- Vrum (Brasil), recall de Kardian Evolution por bulones traseros (07/2024): https://www.vrum.com.br/noticias/2024/07/6901264-renault-kardian-tem-recall-para-sanar-perda-de-dirigibilidade.html
- Latin NCAP, cinco estrellas para el Kardian (27/11/2025): https://www.latinncap.com/en/media-area/new/8692840c0452cd/kardian-is-renaults-first-five-stars-and-taos-renews-top-safety
- Carro.Blog.Br (Brasil), reclamos de la caja de doble embrague (02/09/2025): https://carro.blog.br/problemas-no-cambio-do-nissan-kicks-2026-e-renault-kardian-preocupam-donos-de-suvs.html

Dudas:
- Poco historial: modelo a la venta desde agosto de 2024. No encontré ningún llamado a revisión en Argentina. El único recall encontrado es brasileño (Evolution fabricados del 15/03 al 03/05/2024, que en Brasil es 1.0 turbo); no hay nada que diga que alcance a unidades argentinas, que empezaron a venderse en agosto de 2024.
- En Argentina existe la Evolution 1.6 manual de 115 CV (Autoweb), que el encargo no listaba. La guía la incluye.
- Garantía e intervalos de service: no abrí ninguna fuente oficial que los confirme (una nota de preventa habla de 3 años o 100.000 km y el manual Latam muestra 10.000 km/12 meses solo como ejemplo de pantalla). No van en la guía; se pide confirmarlos en un concesionario.
- Reclamos de la EDC: solo un blog brasileño que cita Reclame Aqui sin casos concretos del Kardian. Va como «reportes en Brasil» y sin frecuencia.
- Latin NCAP indica control de estabilidad de serie, pero la nota de lanzamiento de Autoweb no lo menciona; no confirmé que todas las unidades 2024 lo traigan (es lo más probable, pero no lo afirmo fuera de la línea de Latin NCAP).
- La caja es húmeda según Autoweb; 16 Válvulas solo lo sugiere y Autotest no lo dice. No lo puse en la guía.

Correcciones tras el chequeo de fuentes (11/2026):
- Fallas eléctricas: acotadas a «la unidad de prensa que probó Autoweb» y a «vidrios y testigos», como dice la nota («nada grave»).
- EDC: lo de Autotest queda en «el avance al maniobrar no es progresivo ni suave»; saqué «tirones» de la prueba argentina (eso es del blog brasileño).
- Recall Brasil: «cambiaba tambores traseros y bulones»; Vrum aclara que la marca no mencionó el riesgo de que se suelte la rueda, así que no lo digo.
- Garantía: saqué «el historial de services es importante para conservar la garantía» (sin fuente); ahora pide confirmar condiciones en un concesionario.
- Pregunta de Latin NCAP: «corresponde a unidades fabricadas desde agosto de 2025».
- Rueda de auxilio: temporal y de 15 en vez de 17 según Autoweb; quedó como «de menor medida».
- No se quitó ninguna fuente: las 8 cargan y respaldan algo de la guía.

## Suzuki Fun (2003–2011)

Fuentes:
- Parabrisas, «Así probábamos el Suzuki Fun» (prueba de julio de 2003, republicada el 13/09/2020): https://parabrisas.perfil.com/noticias/novedades/suzuki-fun-auto-2003-test-prueba-manejo-impresion-argentina-nuevo.phtml
- Just Auto, el Celta va a Argentina como Suzuki (11/06/2003): https://www.just-auto.com/news/exclusive-brazil-german-based-brazilian-chevy-goes-to-argentina-as-a-suzuki/
- Salvat, Autos Inolvidables Argentinos, Suzuki Fun 1.0: https://www.salvat.com/autos-inolvidables-argentinos/suzuki-fun-10-6680
- Autotest, autos vendidos con diferente marca: https://autotest.com.ar/noticias/dia-del-hermano-5-autos-vendieron-diferente-marca-argentina/
- iProfesional, el Fun pasará a llamarse Celta (30/04/2011): https://www.iprofesional.com/actualidad/115295-el-actual-suzuki-fun-pasara-a-llamarse-chevrolet-celta
- La Nación, «Chevrolet lanzó el Celta» (30/04/2011): https://www.lanacion.com.ar/autos/al-volante/chevrolet-lanzo-el-celta-nid1369188
- Wikipedia, Chevrolet Celta: https://en.wikipedia.org/wiki/Chevrolet_Celta
- Vrum (Brasil), «Não compre no escuro» sobre el Celta usado (23/11/2008): https://www.vrum.com.br/noticias/nao-compre-no-escuro-pressao-no-menor-da-gm/
- Los Andes, llamado de Classic y Celta (23/10/2020): https://www.losandes.com.ar/sociedad/fallas-en-autos-chevrolet-classic-y-celta-citan-a-duenos-para-que-los-lleven-al-taller-en-mendoza

Dudas:
- **Origen**: el encargo dice «hecho en Argentina», pero todas las fuentes (Just Auto, Salvat, Autotest, Wikipedia) dicen que era el Celta importado de Gravataí, Brasil. La guía dice Brasil.
- **Plataforma**: Salvat y Wikipedia dicen «plataforma del Opel Corsa B»; Parabrisas dice que el motor 1.0 es el del Corsa. La guía lo dice así.
- **Año de inicio**: Parabrisas lo prueba en julio de 2003 y Just Auto fecha la exportación en junio de 2003; Wikipedia dice 2004–2011. Usé 2003 como el catálogo.
- **1.4 y cinco puertas**: Wikipedia confirma tres y cinco puertas en LS y LT, pero el 1.4 solo aparece en avisos y opiniones de dueños (Opinautos, 403, no citado). No encontré una nota con la fecha del cambio; la guía pide confirmarlo.
- **Potencia del 1.0**: Parabrisas dice 60 CV y Just Auto 70 bhp. No puse cifra.
- **Fallas**: todas salen de una nota brasileña de 2008 sobre el Celta (Vrum), sin años. Marcadas «reportes en Brasil (Celta)». El intervalo de la correa no está confirmado.
- **Recall**: no encontré llamados del Fun. El de Takata de Classic y Celta es para 2013–2016 (posterior al Fun); se menciona solo en `generations`.
- No encontré el manual ni el plan de mantenimiento del Fun.

Correcciones tras el chequeo de fuentes (11/2026):
- Saqué «los repuestos del Celta son fáciles de conseguir y su mantenimiento es simple» (venía de Autoo, que dio 403 y no se cita). Queda lo que dice Parabrisas: el 1.0 es el mismo motor del Corsa.
- Checklist: saqué las pérdidas de líquido de dirección (también venían de Autoo).
- Celta recall: «no alcanza al Fun» pasó a «esos años son posteriores al Fun» (Los Andes no lo dice explícitamente).
- No se quitó ninguna fuente: las 9 cargan y respaldan algo de la guía.

## Suzuki Grand Vitara tercera generación JIII (2008–2018)

Fuentes:
- Autocosmos, Autos clásicos de Argentina: Suzuki o Chevrolet Grand Vitara (18/07/2024): https://noticias.autocosmos.com.ar/2024/07/18/autos-clasicos-de-argentina-suzuki-o-chevrolet-grand-vitara
- 16 Válvulas, Suzuki Grand Vitara JIII (09/08/2007): https://www.16valvulas.com.ar/?p=353
- Diario de Cuyo, «El Grand Vitara JIII llegó renovado» (30/01/2010): https://www.diariodecuyo.com.ar/tendencia/El-Grand-Vitara-JIII-llego-renovado-20100130-0022.html
- 16 Válvulas, New Grand Vitara, lanzamiento en Argentina (10/01/2014): https://www.16valvulas.com.ar/?p=77940
- 16 Válvulas, prueba JLX-L AT (15/04/2014): https://www.16valvulas.com.ar/probamos-la-nueva-suzuki-grand-vitara-5-puertas-jlx-l-at/
- 16 Válvulas, Grand Vitara 3 puertas (08/06/2016): https://www.16valvulas.com.ar/?p=129010
- 16 Válvulas, vuelve la 5 puertas (27/09/2016): https://www.16valvulas.com.ar/?p=132085
- 16 Válvulas, recall del selector de marchas (06/06/2017): https://www.16valvulas.com.ar/?p=139767
- CarComplaints, recall en EE.UU. (19/02/2017): https://carcomplaints.com/news/2017/suzuki-grand-vitara-recall-gear-shifters.shtml
- Marque News (Australia), guía de usados 2005-2017: https://marquenews.com.au/suzuki-grand-vitara-vitara-2005-2017/
- Parabrisas, Suzuki XL7 (01/04/2022; menciona la XL-7 vendida hasta 2008): https://parabrisas.perfil.com/noticias/novedades/suzuki-grand-vitara-xl7-version-siete-asientos-7-nueva-suv-aventurera.phtml

Dudas:
- **year_from 2008**: no encontré la nota del lanzamiento argentino de la JIII. 16 Válvulas (08/2007) la anuncia como próxima a llegar y la segunda generación se fabricó acá hasta 2008 (Autocosmos). Puede haber unidades 2007.
- **year_to 2018**: Autocosmos dice que Indumotora la importó hasta 2018; no encontré la fecha exacta de fin. La guía cubre las dos etapas (GM 2008–2011 e Indumotora 2014–2018) con el hueco 2012–2013 sin ventas oficiales confirmadas.
- **Versiones de la etapa GM**: ninguna fuente abierta nombra terminaciones (JLX, GLX) de 2008–2011; los avisos dicen «JIII». Las versiones JX, JLX y JLX-L son de 2014.
- **Tres puertas sin reductora**: Marque News (Australia) dice que la tres puertas de ese mercado no tiene reductora, pero 16 Válvulas dice que la JX argentina sí («alta y baja», «caja reductora y bloqueo»). No usé el dato australiano.
- **Cadena o correa del 2.4 (J24B)** e intervalos: sin fuente; la guía pide confirmarlo en el manual.
- El recall argentino sale de una sola nota de prensa (16 Válvulas) con rango de chasis; el título dice «Vitara» pero el texto, «Grand Vitara J24B».
- Autoblog Argentina (crítica 2014, «Adiós a la Grand Vitara») dio 403; MotorMagazine dio 503.

Correcciones tras el chequeo de fuentes (11/2026):
- Selector de tracción: saqué el modo «normal» (no quedó claro en la prueba si es un modo de tracción); quedan 4H, 4H con bloqueo y 4L con bloqueo, como «la 4x4 que probó la prensa en 2014».
- `generations` Indumotora: el año sin ventas en 2015 se atribuye a 16 Válvulas, no a Autocosmos.
- Pregunta 4: «la importada desde 2014» pasó a «la que se vendió desde 2014», porque las dos etapas eran importadas.
- No se quitó ninguna fuente: las 11 cargan y respaldan algo de la guía.

## Toyota Hilux séptima generación (2005–2015)

Fuentes:
- Autocosmos, «Nueva Toyota Hilux y SW4 en Argentina» (05/11/2011): https://noticias.autocosmos.com.ar/2011/11/05/nueva-toyota-hilux-y-sw4-en-argentina
- Autoweb, «Prueba: Toyota Hilux 4x4 SRV AT» (07/11/2011): https://www.autoweb.com.ar/?p=9293
- Autotest, Hilux de más de diez años sin uso: https://autotest.com.ar/noticias/toyota-hilux-mas-de-diez-anos-nunca-uso/
- Autotest, «Encuentran una Toyota Hilux como nueva»: https://autotest.com.ar/noticias/encuentran-una-toyota-hilux-como-nueva
- BAE Negocios, recalls 2020 (airbags Corolla, Hilux y Etios 2005–2017): https://www.baenegocios.com/negocios/Recall-10-automotrices-piden-revision-de-sus-autos-vendidos-en-Argentina-por-desperfectos-20201109-0051.html
- 16 Válvulas, revisión gratuita de airbags Hilux 2005–2015 (01/02/2024): https://www.16valvulas.com.ar/?p=224747
- Infozona, lista de autos con airbags a reparar (01/04/2026): https://www.infozona.com.ar/?p=391552
- Ministerio de Economía y Finanzas de Uruguay, alerta Toyota (16/08/2018): https://www.gub.uy/ministerio-economia-finanzas/comunicacion/comunicados/campana-alerta-vehiculos-marca-toyota-varios-modelos
- Unsealed 4X4 (Australia), «D4D Hilux common problems and solutions»: https://unsealed4x4.com.au/d4d-hilux-common-problems-and-solutions/
- El Sol (Mendoza), lanzamiento de la octava generación (26/11/2015): https://www.elsol.com.ar/?p=1015303
- Autoweb, restyling de la Hilux (21/08/2018, octava generación): https://www.autoweb.com.ar/?p=3095

Dudas:
- **Etapas y potencia**: Autocosmos y Autoweb (noviembre de 2011) dicen que con la línea 2012 el 3.0 pasó de 163 a 171 CV y la automática es de cuatro marchas. Autotest («como nueva») ubica el aumento a 171 CV y un cambio de frente en un «segundo restyling de 2013» y dice automática de cinco relaciones. Usé las notas contemporáneas de 2011 y lo aclaré en `generations`.
- **Código de motor**: ninguna fuente abierta confirma que el 3.0 argentino sea el 1KD-FTV (una página de discusión de Wikipedia habla del 1KZ-TE hasta 2005). Todo lo de inyectores, turbo, chupador de aceite, embrague, bomba de agua y correa sale de una revista australiana sobre el 1KD-FTV: marcado como otros mercados y se pide confirmar el código.
- **Correa de distribución**: la fuente australiana menciona el cambio de correa del 1KD-FTV pero no da intervalo. No encontré el manual argentino de la época (solo PDFs en sitios dudosos), así que no hay intervalos de service.
- **Versiones**: las fuentes nombran SR y SRV. DX aparece solo en avisos de usados y SRX es de la octava generación según Autoweb 2018; no las nombré.
- **Takata**: las notas argentinas dan rangos distintos (BAE: 2005–2017 para los tres modelos; 16 Válvulas e Infozona: Hilux 2005–2015). Usé 2005–2015. La descripción del inflador sale del aviso uruguayo.

Correcciones tras el chequeo de fuentes (11/2026):
- Llamado de airbags: «seguía publicándolo como pendiente» pasó a «en 2026 seguía incluyendo esas unidades en las listas de llamados» (Infozona solo las lista).
- Mantenimiento: saqué que embrague, inyectores y turbo «son las reparaciones» a presupuestar; ahora se pide presupuesto si no hay comprobantes.
- Octava generación: «desde el restyling de 2018 usa 2.4 y 2.8» pasó a «en el restyling de 2018 (sin cambios mecánicos) ofrecía 2.4 y 2.8», porque Autoweb dice que no hubo cambios mecánicos.
- Pantalla táctil con cámara de la línea 2012: agregado «según versión» (Autocosmos la lista sin decir en qué versiones).
- Equipamiento de la versión de entrada: queda atribuido a una nota de Autotest sobre una unidad básica estimada de 2012.
- No se quitó ninguna fuente: las 11 cargan y respaldan algo de la guía.

## Toyota RAV4 cuarta generación XA40 (2013–2019)

Fuentes:
- Autocosmos, lanzamiento en Argentina (17/04/2013): https://noticias.autocosmos.com.ar/2013/04/17/toyota-presenta-la-nueva-rav4-en-argentina
- Autocosmos, actualización en Argentina (06/07/2016): https://noticias.autocosmos.com.ar/2016/07/06/la-toyota-rav4-se-actualiza-en-argentina-info-precios-y-mas
- Seminuevos, RAV4 2016 en Argentina (13/07/2016): https://www.seminuevos.com/blog/nueva-toyota-rav4-2016-a-la-altura-de-la-competencia/
- Autoweb, RAV4 híbrida en Argentina (23/05/2019): https://www.autoweb.com.ar/?p=8455
- Parabrisas, quinta generación (23/05/2019): https://parabrisas.perfil.com/noticias/novedades/toyota-presento-al-nuevo-rav4.phtml
- Samarins, RAV4 2013–2018 (Norteamérica): https://www.samarins.com/reviews/rav4-xa40.html
- Haynes, problemas comunes RAV4 2013–2018 (EE.UU.): https://us.haynes.com/blogs/tips-tutorials/toyota-rav4-common-problems-2013-2018
- VehicleFlaws, recall NHTSA 23V734000 (batería, RAV4 2013–2018): https://vehicleflaws.com/recall/23V734000

Dudas:
- **Fallas**: todas salen de fuentes norteamericanas (Samarins, Haynes) y están marcadas como otros mercados. No encontré prensa argentina sobre fallas de esta generación.
- **Motor y caja 2.5**: Autocosmos 2013 lo llama 2.4 en un párrafo y 2.5 en otro (180 CV). No confirmé que sea el 2AR-FE ni que la automática de seis sea la U760 de Norteamérica; lo de cadena, aceite 0W-20, bujías y convertidor de par queda como dato de ese mercado.
- **Llamados en Argentina**: no encontré ninguno de Toyota Argentina para esta generación. Los PDFs de media.toyota.com.ar devolvieron 403. El llamado Takata de Uruguay alcanza RAV4 2004–2005 (otra generación) y el de cinturones traseros de 2016 alcanza 2006–2012; no los incluí.
- **year_to 2019**: es aproximado; la quinta generación se lanzó en mayo de 2019 y ninguna fuente dice cuándo dejó de venderse la cuarta.
- **Origen**: ninguna fuente abierta dice de dónde se importaba; no lo mencioné.
- Seminuevos es un sitio con nombre genérico, pero la nota es sobre el lanzamiento argentino y coincide con Autocosmos.

Correcciones tras el chequeo de fuentes (11/2026):
- Prueba de manejo: saqué «entre 40 y 70 km/h» (ninguna fuente da velocidades; Samarins dice «al acelerar suave»).
- Tercera generación: se aclara que el año de inicio es aproximado (Autoweb solo dice que hubo camadas en 2000, 2005 y 2013).
- La extensión ZH1 se aclara como de Norteamérica, sin decir que aplique acá.
- Recall de baterías: marcado como EE.UU. y se aclara que es para baterías de reemplazo que no calzan.
- No se quitó ninguna fuente: las 8 cargan y respaldan algo de la guía.
