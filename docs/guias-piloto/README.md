# Guías piloto (PAR-04)

Cinco guías escritas a mano para cargar con `admin_save_model_guide(p_id => null, p_values => <json>, ...)` (migración `20261205120000_par04_model_guides.sql` de la rama `claude/par04-guias`). Cada archivo es el `p_values` completo: `make, model, generation_label, year_from, year_to, slug_make, slug_model, body, questions, sources`.

- Marca y modelo con la grafía de `vehicle_catalog` (`supabase/seed.sql`): Ford Focus, Ford Fiesta, Volkswagen Gol Trend, Fiat Argo, Toyota Corolla. Los slugs coinciden con `slugify()` de `web/lib/guides.ts`.
- Validadas con `python -m json.tool` y con un test temporal de vitest (ya borrado) que corrió `GuideValuesInput` (zod), `lintGuide` (términos prohibidos y cifras de dinero) y `publishProblem` de `web/lib/guides.ts`: las cinco pasan.
- No hay montos de dinero. «Mantenimiento y costos típicos» describe qué presupuestar e intervalos en km o años.
- Todas las fuentes tienen `verified: true`: las abrí en esta sesión y respaldan lo que la guía dice. Igual, quien publique tiene que marcar «La revisé» después de leerlas.
- No se escribió nada en la base ni se hizo commit.

| Archivo | Guía | Años | Fuentes |
|---|---|---|---|
| `ford-focus.json` | Ford Focus, Focus III | 2013–2019 | 9 |
| `ford-fiesta.json` | Ford Fiesta, Kinetic Design | 2011–2019 | 12 |
| `volkswagen-gol-trend.json` | Volkswagen Gol Trend | 2008–2023 | 9 |
| `fiat-argo.json` | Fiat Argo, primera generación | 2017– (year_to null) | 7 |
| `toyota-corolla.json` | Toyota Corolla, XI (E170) | 2014–2019 | 4 |

## Ford Focus III (2013–2019)

Fuentes:
- Parabrisas, «¿Qué pasa con la caja Powershift de Ford?» (02/06/2017): https://parabrisas.perfil.com/noticias/general/2017-06-02-que-pasa-con-la-caja-powershift-de-ford.phtml
- Motor Show (Brasil), reparación gratuita PowerShift (26/01/2016): https://motorshow.com.br/ford-fara-reparo-gratuito-em-ecosport-fiesta-e-focus-com-cambio-powershift
- CarComplaints, extensión de cobertura DPS6 en EE.UU. y Canadá (2019): https://www.carcomplaints.com/news/2019/ford-powershift-transmission-warranty-extension.shtml
- Ford Argentina, «Ford Focus Garantía y Mantenimiento» (PDF publicado por el concesionario Forcor): https://www.forcor.com.ar/wp-content/uploads/2019/09/Focus_Garantia.pdf
- Autoblog Uruguay, presentación del Focus III en Buenos Aires (06/2013): https://www.autoblog.com.uy/2013/06/ford-presento-en-buenos-aires-al-nuevo.html
- Autoblog Uruguay, Focus 2016 en el Salón de Buenos Aires 2015: https://www.autoblog.com.uy/2015/06/salon-de-buenos-aires-2015-ford-focus.html
- Monkey Motor, Focus 2017 (12/07/2016): https://www.monkeymotor.net/2016/07/ford-focus-my2017.html
- Autoweb, Ford deja de producir autos en Argentina (06/05/2019): https://www.autoweb.com.ar/2019/05/06/ford-deja-de-producir-autos-en-la-argentina-luego-de-57-anos/
- Diario de Cuyo, fin del Fiesta y salida del Focus de Pacheco en mayo de 2019 (20/02/2019): https://www.diariodecuyo.com.ar/tecnologia/Ford-deja-de-fabricar-el-Fiesta-hasta-cuando-habra-stock-en-Argentina-20190220-0027.html

Dudas:
- Intervalos de correa de distribución y correa auxiliar del 1.6 (8 años o 120.000 km): los saqué de la tabla del PDF convertida a texto. La tabla está en columnas y el orden de las filas indica eso, pero conviene mirar la página 25 del PDF original.
- No encontré ninguna extensión oficial de garantía de Ford **Argentina** para la PowerShift. La guía cita Brasil y EE.UU./Canadá y aclara que no se aplican solas acá.
- En EE.UU. hubo llamados por la válvula del canister del Focus 2012–2018 (NHTSA 18V735, 19V515 y 26V369). No los incluí: no confirmé que alcancen a autos argentinos y no abrí la página de NHTSA.
- Que la PowerShift esté en SE Plus y Titanium sale de Monkey Motor (2016). Lo que había antes del restyling no quedó confirmado.

## Ford Fiesta Kinetic Design (2011–2019)

Fuentes: Parabrisas PowerShift, Motor Show (Brasil) y CarComplaints (las mismas de arriba), más:
- Ford Argentina, Manual del propietario Fiesta, edición 11/2013 (PDF publicado por Forcor; mensajes de la PowerShift): https://www.forcor.com.ar/wp-content/uploads/2014/09/Nuevo-Fiesta-B299MCA-Manual.pdf
- Ford Focus Garantía y Mantenimiento (PDF de Forcor; correa del 1.6 Sigma Ti-VCT): https://www.forcor.com.ar/wp-content/uploads/2019/09/Focus_Garantia.pdf
- La Nación, lanzamiento del Fiesta Kinetic Design: https://www.lanacion.com.ar/autos/al-volante/se-lanzo-el-ford-fiesta-kinetic-design-nid1322026/
- Autotest, «Usado: Ford Fiesta Kinetic»: https://autotest.com.ar/noticias/usado-ford-fiesta-kinetic-que-saber/
- Autotest, repaso de generaciones del Fiesta: https://autotest.com.ar/noticias/adios-ford-fiesta-repaso-generaciones-argentina
- Cuyo Motor, Fiesta KD 2014 (29/08/2013): https://cuyomotor.com.ar/2013/08/29/el-nuevo-ford-fiesta-kd
- Autocosmos, actualización de diciembre de 2017: https://noticias.autocosmos.com.ar/2017/12/11/nuevo-ford-fiesta-se-lanza-en-argentina
- BAE Negocios, recalls 2020 (cerraduras del Fiesta 2014): https://www.baenegocios.com/negocios/Recall-10-automotrices-piden-revision-de-sus-autos-vendidos-en-Argentina-por-desperfectos-20201109-0051.html
- Diario de Cuyo (la de arriba): fin de la producción en Brasil y stock hasta 2020.

Dudas:
- **Años**: el modelo se lanzó en Argentina el 6/11/2010 (La Nación). Dejé `year_from = 2011` como pide el encargo y la primera generación de la guía lo aclara en el texto.
- El intervalo de la correa sale del plan del **Focus** con el mismo motor 1.6 Sigma Ti-VCT. La guía lo dice y pide confirmarlo en el libro del Fiesta, que no encontré.
- Los años de las etapas en `generations` son aproximados: el rediseño de 2013 corresponde al año modelo 2014 y la actualización de diciembre de 2017, al 2018. Una fuente (Autotest) dice que la producción en la región terminó en 2018 y otra (Diario de Cuyo, 02/2019) que terminaba durante 2019. Usé la segunda.
- La extensión de EE.UU. cubre Fiesta 2014–2015 hechos en México para Norteamérica. Los sedanes argentinos también venían de México, pero no hay nada que diga que esa cobertura se aplica acá.
- Lo de los siete airbags de serie sale de Autotest y Cuyo Motor; la nota de 2017 no dice si los traen todas las versiones.

## Volkswagen Gol Trend (2008–2023)

Fuentes:
- Autotest, usados Gol Trend 2008–2012: https://autotest.com.ar/noticias/usados-volkswagen-gol-trend-2008-2012/
- La Nación, restyling Gol Trend y Voyage (22/12/2012): https://www.lanacion.com.ar/autos/al-volante/los-nuevos-vw-gol-trend-y-voyage-nid1539059
- Autoweb, las 11 trompas del Gol: https://www.autoweb.com.ar/?p=32806
- Parabrisas, diez datos del Gol 2019: https://parabrisas.perfil.com/noticias/noticias/diez-datos-a-tener-en-cuenta-sobre-el-volkswagen-gol-2019.phtml
- Autoweb, Gol automático Tiptronic (17/07/2019): https://www.autoweb.com.ar/?p=9427
- El Economista, llamado de VW por airbags 2006–2018 (18/12/2023): https://eleconomista.com.ar/autos/si-sos-dueno-volkswagen-fabricado-2006-2018-marca-te-esta-buscando-n69427
- Parabrisas, VW llama a revisión por airbags (14/12/2023): https://parabrisas.perfil.com/noticias/noticias/volkswagen-llama-a-revision-a-sus-propietarios-por-fallas-en-los-airbags.phtml
- Vrum (Brasil), cajas automáticas con problemas (I-Motion): https://www.vrum.com.br/aceleradas/2024/12/7008662-alem-do-powershift-carros-automaticos-famosos-por-darem-problemas-no-cambio.html
- El Cronista, el Gol dejó de venderse 0 km: https://www.cronista.com/autos/el-volkswagen-gol-el-auto-mas-amado-por-los-argentinos-dejo-de-venderse-aca-pero-lo-siguen-comprando-usado

Dudas:
- **Correa de distribución del 1.6**: ninguna fuente que abrí lo confirma, porque la nota de Mercado Libre devolvió 403 y las de talleres no sirven como fuente. Coincide con `vehicle_catalog.timing_belt = true` del seed. La guía no da intervalo y remite al manual.
- **Llamado por airbags**: las notas nombran «Gol» (2006–2018), no «Gol Trend». La guía lo dice y pide consultar el VIN.
- **year_to 2023**: El Cronista dice que dejó de venderse 0 km en Argentina en 2022. Dejé 2023 por el catálogo y el encargo, y el texto lo aclara. Desde 2016 la prensa lo llama simplemente «Gol».
- Los airbags en la primera etapa: Autotest los menciona solo en la Pack III y no aclara las demás versiones. La guía pide confirmarlo en la unidad.
- Lo del GNC (oblea, controles periódicos) es conocimiento general argentino, sin una fuente abierta en esta sesión.
- La lista de síntomas de la I-Motion (tirones, embrague que patina, pérdidas del actuador) sale de una nota brasileña (Vrum). Autotest solo dice que «dio varios dolores de cabeza».

## Fiat Argo (2017–presente)

Fuentes:
- Parabrisas, lanzamiento oficial en Argentina (29/09/2017): https://parabrisas.perfil.com/noticias/noticias/2017-09-29-fiat-argo-lanzamiento-oficial-en-la-argentina.phtml
- Autocosmos, recall de Cronos y Argo 2019 por el eje de dirección (29/01/2019): https://noticias.autocosmos.com.ar/2019/01/29/fiat-argentina-llama-a-revision-los-modelos-cronos-y-argo-2019
- La Voz de San Justo, campaña de relés de Fiat (27/07/2018): https://www.lavozdesanjusto.com.ar/si-tenes-un-fiat-tenes-que-leer-esta-nota-43181
- Autoweb, Fiat deja una sola versión del Argo (12/09/2022): https://www.autoweb.com.ar/?p=31329
- Autocosmos, Argo CVT en Argentina (07/01/2026): https://noticias.autocosmos.com.ar/2026/01/07/el-fiat-argo-cvt-se-lanza-y-ya-tiene-precio-en-argentina
- Motor Show (Brasil), Argo usado: https://motorshow.com.br/carro-usado-fiat-argo-tem-mais-qualidades-do-que-defeitos
- Vrum (Brasil), principales problemas del Argo (03/2025): https://www.vrum.com.br/aceleradas/2025/03/7075516-argo-veja-os-principais-problemas-do-hatch-mais-vendido-da-fiat.html

Dudas:
- Las fallas de dirección, start-stop, bujías y bomba de agua del 1.8 salen de prensa **brasileña**. La guía las marca como «reportes en Brasil» o según el motor.
- **Trekking**: `vehicle_catalog` la lista como versión del Argo, pero no encontré confirmación de que se vendiera oficialmente en Argentina (Parabrisas 2019 decía «¿Llegará a la Argentina?»). No la mencioné.
- La caja «GSR» automatizada aparece en algunos avisos, pero no la confirmé para Argentina y no la mencioné.
- No confirmé si el Argo entra en el recall de airbags Takata de Stellantis en Argentina. No lo incluí.
- No pongo cadena o correa para el Argo porque no abrí ninguna fuente que lo diga. El catálogo interno dice cadena (`timing_belt = false`).
- El intervalo de 50.000 km del fluido de la automática es la recomendación para uso severo de Motor Show (Brasil), no del plan oficial de Fiat Argentina.

## Toyota Corolla XI / E170 (2014–2019)

Fuentes:
- Autoblog Uruguay, presentación del Corolla para el Mercosur (13/03/2014): https://www.autoblog.com.uy/2014/03/bienvenido-al-mercosur-toyota-presento.html
- Parabrisas, restyling 2017 en Argentina (20/04/2017): https://parabrisas.perfil.com/noticias/noticias/2017-04-20-asi-es-el-nuevo-toyota-corolla.phtml
- BAE Negocios, recalls 2020 (airbags de Corolla, Hilux y Etios 2005–2017): https://www.baenegocios.com/negocios/Recall-10-automotrices-piden-revision-de-sus-autos-vendidos-en-Argentina-por-desperfectos-20201109-0051.html
- Samarins, Corolla 2014–2019, problemas comunes: https://www.samarins.com/reviews/corolla.html

Dudas:
- Es la guía con menos fuentes argentinas. Autocosmos (lanzamiento del 10/04/2014) dio timeout dos veces y 16 Válvulas bloquea la lectura automática. El equipamiento de 2014 sale de la nota uruguaya sobre el lanzamiento del Mercosur, que dice que las primeras unidades iban a Brasil y Argentina.
- Fallas menores, mantenimiento y aceite 0W-20 salen de Samarins, una reseña pensada para Norteamérica (motor 2ZR). La guía las marca como «reportes en otros mercados» y pide seguir el manual de la unidad.
- **Potencia**: la nota de 2014 dice 139 CV y Parabrisas 2017 dice 140 CV. Usé «unos 140 CV».
- La fecha exacta del llamado de airbags de Toyota Argentina no está confirmada: la nota de BAE (11/2020) dice que Toyota estaba enviando cartas.
- Toyota Safety Sense: la nota de 2017 no lo menciona, así que no lo incluí. Las notas que lo mencionan son de la generación siguiente.

## Fuentes que no pude usar

- argentina.gob.ar (registro de recalls de Defensa del Consumidor): la búsqueda no devolvió ninguna página del registro para estos modelos, así que todos los recalls citados salen de prensa argentina.
- 16valvulas.com.ar (verificación anti-bot), blog de Mercado Libre (403), toyota.com.br (403), páginas de recall de volkswagen.com.ar (404): no las cité.
