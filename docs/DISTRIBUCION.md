# Distribución: cadena o correa

`vehicle_catalog.timing_belt` dice cómo mueve el motor los árboles de levas:
`true` correa (seca o en aceite), `false` cadena, `null` desconocido o depende
del motor. Se usa en dos lugares:

- **Bandera roja `no_timing_belt`** (sección 6.5): solo `true` la levanta.
- **Búsqueda asistida** (`worker/normalization/drafts.py`): «cadenero», «con
  cadena», «sin correa» llegan como `timing: "chain"` (y «con correa» como
  `"belt"`). Con modelo, una nota avisa si el catálogo lo conoce al revés («El
  Gol usa correa de distribución») o no lo sabe. Sin modelo, el borrador se
  abre en un modelo por cada fila con `timing_belt = false` compatible con la
  carrocería y los años pedidos, hasta `MAX_VEHICLES`, y la web deja elegir
  cuál activar (ModelChoice). Si no hay ninguno, queda la búsqueda por
  carrocería con una nota.

## Orden de los modelos propuestos

`db/repos/catalog.load_market` lee, cada 10 minutos como el catálogo, las
publicaciones activas vistas en los últimos 30 días por (marca, modelo, año):
cuántas y el percentil 25 de `price_usd`, más la última cotización de
`fx_rates` (para un tope en pesos). Unos 30 ms sobre ~10.000 publicaciones.

- Con `price_max`, se proponen solo los modelos que tienen **algún año del
  rango pedido cuyo percentil 25 entra en el tope** («precio típico de
  entrada»). Si ninguno entra, se proponen igual, con una nota por modelo.
- Se ordenan por **cantidad de publicaciones en los años pedidos**, y a igual
  cantidad por marca y modelo. Sin datos de mercado (tests, `record_llm`), por
  marca y modelo, y la nota no dice «los más publicados».

## Por qué un modelo queda en null

El dato es del motor, no del modelo: un Hilux 3.0 (1KD, 2005–2015) tiene
correa y un 2.8 (1GD, 2016+) cadena. El catálogo tiene una sola fila por
modelo (`trim is null`); las filas por versión no tienen años ni motor, así
que no sirven para partir el dato. Por eso un modelo se marca solo si **todos
los motores que tuvo en Argentina** en los años de su fila y de sus
publicaciones coinciden, con fuente. Si varía, queda `null`: no levanta la
bandera ni entra en una búsqueda «cadenero», que es el lado seguro de ambas.
Las notas igual piden confirmarlo con el vendedor.

Si se quiere recuperar Corolla, Hilux o Civic para «cadenero», el camino es
partir el dato por año (p. ej. una columna `chain_from_year`), no marcar el
modelo entero.

## Tabla (migración 20261107130000_timing_chain_catalog.sql, sin aplicar)

Fuente principal: [fichacompleta.com.br](https://www.fichacompleta.com.br/carros/),
que transcribe las fichas técnicas de fábrica de Brasil con el campo
«Acionamento do comando» (Corrente/Correia dentada) y el código de motor; los
motores son los mismos del Mercosur. «fc:» abrevia
`https://www.fichacompleta.com.br/carros/`. Investigado el 25/10/2026 sobre los
modelos con más publicaciones activas de los últimos 30 días en producción.

### Se marcan

| Modelo | Valor | Motores en AR | Fuente |
|---|---|---|---|
| Toyota Corolla Cross | cadena | 2.0 M20A, 1.8 híbrido 2ZR | fc: toyota/corolla-cross-altis-hybrid-1-8-2022, toyota/corolla-cross-xrx-hybrid-1-8-2026 |
| Fiat Cronos | cadena | 1.3 Firefly, 1.8 E.torQ | fc: fiat/cronos-drive-s-design-1-3-2023, fiat/cronos-drive-1-8-at-2020 |
| Fiat Argo | cadena | 1.0/1.3 Firefly, 1.8 E.torQ | fc: comparativo/argo-drive-1-3-gsr-2020-vs-argo-hgt-1-8-at-2019-vs-argo-1-0-2020-vs-argo-hgt-1-8-at-2020; [Autopapo](https://autopapo.com.br/noticia/carros-sem-correia-dentada/) |
| Fiat Pulse | cadena | 1.3 Firefly, 1.0 T200, 1.3 T270 | fc: fiat/pulse-drive-1-0-turbo-2022-flex; Autopapo |
| Renault Kwid | cadena | 1.0 SCe B4D | fc: páginas renault/kwid (B4D) |
| Renault Kardian | cadena | 1.0 TCe | [Garagem360](https://garagem360.com.br/?p=314844) (ficha de prensa); Autopapo |
| Nissan Kicks | cadena | 1.6 HR16DE, 1.0T HR10 | fc: nissan/kicks-play-sense-1-6-2025, nissan/kicks-exclusive-1-0-2026 |
| Nissan Versa | cadena | 1.6 HR16DE | Autopapo (toda la gama Nissan salvo el March 1.0 de origen Renault) |
| Nissan Sentra | cadena | 2.0 MR20DE / MR20DD | fc: páginas nissan/sentra |
| Ford Territory | cadena | 1.5 EcoBoost JX4G15 | fc: ford/territory-sel-1-5-turbo-2021, ford/territory-titanium-1-5-turbo-2025; [O Mecânico](https://omecanico.com.br/raio-x-ford-territory-estreia-trem-de-forca-no-brasil/). 2026 sin dato, mismo motor |
| VW Polo | correa | 1.6 8v EA111, 1.9 SDI; 1.6 MSI, 1.0/1.4 TSI | fc: comparativo/polo-1-6-2003-vs-polo-1-6-2006-vs-polo-sportline-1-6-2006; [Gates](https://www.techtips.ie/Gates/vag-timing-system-replacement-intervals.pdf) |
| VW Virtus | correa | 1.6 MSI, 1.0/1.4 TSI (EA211) | fc: volkswagen/virtus-sense-1-6-at-pcd-2020 |
| VW T-Cross | correa | 1.6 MSI, 1.0/1.4 TSI (EA211) | fc: volkswagen/t-cross-highline-1-4-tsi-at-2021 |
| VW Nivus | correa | 1.0 TSI (EA211) | fc: volkswagen/nivus-comfortline-1-0-tsi-2024 |
| VW Taos | correa | 1.4 TSI (EA211) | fc: volkswagen/taos-highline-1-4-tsi-2026 |
| VW Bora | correa | 2.0 EA113, 1.8T, 1.9 TDI | fc: comparativo/bora-2-0-at-2008-vs-jetta-comfortline-2-0-tiptronic-2016; Gates |
| Chevrolet Celta | correa | 1.4 VHC | [Webmotors](https://www.webmotors.com.br/wm1/?p=664407) |
| Fiat Fiorino | correa | 1.4 Fire Evo | [O Mecânico](https://omecanico.com.br/gps-gueparts-lanca-tensionadores-para-fiat-fire-evo/) |

### Correcciones de la lista F2 (vuelven a null)

| Modelo | Antes | Por qué varía | Fuente |
|---|---|---|---|
| Toyota Corolla | cadena | 7A-FE 1998–2002 y diésel 2.0 = correa; 1ZZ en adelante = cadena | fc: toyota/corolla-se-g-1-8-at-1999; [Motordoctor](https://www.motordoctor.es/kit-de-distribucion/toyota/corolla/corolla-wagon-e11/15567-2-0-d-4d-cde110/307) |
| Toyota Hilux | cadena | 1KD/2KD (~2005–2015) = correa; 1GD/2GD y 2TR = cadena | fc: toyota/hilux-srv-3-0-turbo-4x4-cd-2010, toyota/hilux-srx-2-8-turbo-4x4-at-cd-2020 |
| Toyota SW4 | cadena | 3.0 1KD (2006–2015) = correa; 2.8 1GD = cadena | fc: toyota/sw4-srv-3-0-turbo-4x4-at-2012 |
| Honda Civic | cadena | serie D (hasta ~2005) = correa; R18 en adelante = cadena | fc: honda/civic-lxl-1-7-at-2003, es/carros/honda/civic-lxs-1-8-at-2008 |
| Ford Focus | correa | Sigma 1.6 = correa; Duratec 2.0 y EcoBoost = cadena | fc: ford/focus-sedan-glx-1-6-16v-2012, ford/focus-sedan-ghia-2-0-at-2010 |
| Ford EcoSport | correa | Rocam 1.6 y Duratec 2.0 = cadena; Sigma 1.6 y Dragon 1.5 = correa | fc: comparativo/ecosport-xlt-2-0-2008-vs-ecosport-xl-1-6-2006; [InfoAutos](https://infonegocios.info/infoautos/correa-o-cadena-que-traen-los-autos-mas-vendidos-de-argentina) |
| Ford Ka | correa | Rocam 1.0/1.6 = cadena; Sigma y Dragon = correa | Autopapo; InfoAutos |
| Peugeot 208 | correa | 1.5 y 1.6 16v = correa; 1.6 THP y 1.0 T200 = cadena | fc: peugeot/208-griffe-1-6-at-2022, peugeot/208-gt-1-6-turbo-2016 |

Que el Ka, el Focus, la EcoSport y el 208 pasen a null apaga para ellos la
bandera `no_timing_belt`, que hoy también salta en motores de cadena (un Ka
Rocam). Revisar si conviene antes de aplicar.

Confirmados sin cambio: Yaris, Etios, Fit, City y HR-V (cadena; fc:
comparativo/yaris-sedan-xl-1-5-at-2019-vs-etios-sedan-x-1-5-at-2019,
honda/fit-lxl-1-4-8v-2005, honda/city-ex-1-5-at-2016, honda/hr-v-lx-1-8-2017),
Onix (correa, seca en el 1.4 y en aceite en 1.0T/1.2; InfoAutos).

### Quedan en null (varían según el motor)

| Modelo | Detalle |
|---|---|
| VW Golf | EA111/EA113/EA211 y TDI = correa; 2.0 TSI EA888 (GTI) = cadena |
| VW Vento | 2.5 y 2.0 TSI EA888 = cadena; 1.4 TSI y TDI = correa |
| VW Amarok | 2.0 TDI = correa; 3.0 V6 TDI = cadena |
| Ford Ranger | Duratec 2.3/2.5, Power Stroke 3.0 y Puma 2.2/3.2 = cadena; 2.0 Panther y V6 Lion = correa |
| Ford Mondeo | nafta e híbrido = cadena; 2.0 TDCi = correa |
| Chevrolet Cruze | 1.8 = correa; 1.4T = cadena |
| Chevrolet Tracker | 1.8 y 1.2T = correa; 1.4T = cadena |
| Chevrolet S10 | 2.8 Duramax = correa; 2.5 nafta = cadena |
| Fiat Strada | 1.4 Fire = correa; E.torQ, Firefly y T200 = cadena |
| Fiat Toro, Jeep Renegade, Jeep Compass | nafta (E.torQ, T270, Tigershark) = cadena; Multijet diésel = correa |
| Peugeot 2008, Citroën C4 Cactus | 1.6 VTi (EC5) = correa; 1.6 THP y 1.0 T200 = cadena |
| Peugeot 308, 408, 3008; Citroën C4 Lounge | THP = cadena; EW10, EC5 y HDi = correa |
| Renault Captur | 2.0 F4R = correa; 1.6 SCe y 1.3 TCe = cadena |

### Sin confirmar (null; buscar más fuentes)

| Modelo | Qué falta |
|---|---|
| Hyundai Creta | Gamma y Nu = cadena (fc: hyundai/creta-attitude-1-6-2021); el 1.5 Smartstream solo en una ficha de terceros |
| Hyundai HB20 | verificado solo 2025–2026 (Kappa = cadena); la fila no tiene años |
| Renault Koleos | QR25DE = cadena; no cubre una generación nueva con otros motores |
| Nissan Frontier | 2.3 YS23 = cadena; la fila no tiene años y no se verificaron motores anteriores |
| Fiat Mobi | 1.0 Fire Evo = correa; no se confirmó si en Argentina se vendió el 1.0 Firefly (cadena) |
| Fiat Titano | 2.2 Multijet: probablemente correa, sin fuente específica |
