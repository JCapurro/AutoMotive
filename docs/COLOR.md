# Filtro de color — Fase 0: medición

Fecha: 2026-11-12. Plan completo en [PLAN_FILTRO_COLOR.md](PLAN_FILTRO_COLOR.md). Nada de esto toca producción: la base se leyó en modo solo lectura y las fotos se bajaron a una carpeta temporal del VPS, ya borrada.

## Qué se midió

- **Muestra**: 337 avisos activos.
  - 288 de fuentes que declaran el color en la ficha: Mercado Libre 170, Autocosmos 60, Kavak 42 y Randazzo 16. Para estos, la «verdad» es el color declarado.
  - 49 de fuentes sin color (Facebook 20, deRuedas 15, Rosario Garage 14), etiquetados a mano mirando las fotos sin ver la respuesta de la IA. Se descartaron 4 que no eran un auto (una maqueta, uno con solo fotos del interior, repuestos) y 3 de color dudoso.
  - Los colores raros (verde, beige, otro) están sobrerrepresentados a propósito, para poder medirlos. Las cifras «ponderadas» corrigen eso con la mezcla real de colores de los avisos.
- **Métodos**:
  - **píxeles**: el color promedio del centro de la foto, sin IA;
  - **foto1**: la IA (gpt-6-luna) mira la primera foto;
  - **mosaico3**: la IA mira las 3 primeras fotos juntas en una imagen;
  - **multi3**: como mosaico3, pero la IA devuelve una lista de colores posibles con probabilidad;
  - **multi3b**: como multi3, con un prompt que pide incluir siempre el grupo vecino en los colores intermedios. Ejemplos: gris verdoso pasa a gris + verde; plateado cálido, a gris + beige; crema, a beige + blanco.

## Resultados

| Método | Acierto contra color declarado | Ponderado por la mezcla real | Acierto contra etiqueta a mano | Costo cada mil avisos | Latencia p50 |
|---|---|---|---|---|---|
| píxeles | 28,8 % | — | 31 % | 0 | — |
| foto1 | 74,7 % | — | 95,1 % | US$ 0,07 | 1,2 s |
| mosaico3 | 73,1 % | 86,0 % | 97,6 % | US$ 0,08 | 1,2 s |
| multi3b, color en la lista (umbral 30 %) | 80,2 % | 89,8 % | 100 % | US$ 0,11 | 1,4 s |
| multi3b, color en la lista (umbral 20 %) | 86,2 % | 92,0 % | 100 % | US$ 0,11 | 1,4 s |

La medición entera costó US$ 0,12. Los 1.348 pedidos a la IA salieron sin errores.

### Dónde se equivoca

- **Blanco, negro, gris y rojo**: la IA acierta entre 85 % y 100 %.
- **Los errores se juntan en los colores intermedios**:
  - «verde» declarado: casi siempre es un gris verdoso metalizado (Gol, 207, Kwid, Tiguan), y la IA dice gris;
  - «beige»: suele ser un plateado cálido o champagne, y la IA dice gris;
  - «azul»: suele ser un azul grisáceo o muy oscuro, y la IA dice gris o negro.

  Mirando las fotos, muchos de estos son discutibles: una persona también dudaría.
- **El color declarado tampoco es perfecto.** En las hojas de errores aparecen fichas mal cargadas:
  - un «Blanco Oxford» que es rojo;
  - «gris» y «Plata Sirius» que se ven blancos;
  - «blanco» que se ven plateados;
  - un «beige» que es un Golf plateado.

  Por eso el acierto contra lo declarado es un piso: parte de los «errores» son de la ficha, no de la IA.
- **Píxeles no sirve**: sin saber dónde está el auto, mide el fondo y las sombras.

### La lista de colores posibles (idea de Juan)

Con el prompt original la IA casi nunca daba más de un color: 1,05 por aviso. El prompt multi3b la obliga a nombrar el vecino en los colores intermedios.

Ponderado por la mezcla real de colores. «Encuentra» es qué parte de los autos de ese color aparecen al filtrar por él; «limpio» es qué parte de lo que trae el filtro es de ese color.

| Color buscado | Un solo color (mosaico3): encuentra / limpio | Lista, umbral 30 %: encuentra / limpio | Lista, umbral 20 %: encuentra / limpio |
|---|---|---|---|
| blanco | 91 % / 92 % | 91 % / 90 % | 91 % / 80 % |
| negro | 85 % / 93 % | 88 % / 85 % | 88 % / 60 % |
| gris | 89 % / 83 % | 93 % / 77 % | 95 % / 70 % |
| azul | 64 % / 91 % | 83 % / 56 % | 92 % / 37 % |
| rojo | 100 % / 89 % | 100 % / 89 % | 100 % / 89 % |
| verde | 12 % / 14 % | 36 % / 100 % | 56 % / 42 % |
| beige | 39 % / 37 % | 54 % / 35 % | 82 % / 20 % |

Los colores por aviso son 1,22 con umbral 30 % y 1,53 con umbral 20 %.

La lista recupera muchos autos que con un solo color se perdían, sobre todo azul, verde y beige. El costo es que, como el gris es el 40 % de los avisos, los grises con tinte se cuelan en las búsquedas de azul o beige. Las cifras de verde y beige salen de pocos avisos (25 y 28), así que son orientativas.

### Todas las fotos en vez de 3 (pedido de Juan)

Se rearmó la muestra: las mismas 288 fichas con color declarado, ahora con hasta 10 fotos por aviso.
- 71 avisos tienen una sola foto guardada (casi todos de Autocosmos), y para ellos no cambia nada.
- En la variante «todas», cada foto va como imagen aparte en detalle bajo. La IA descarta las de interior, motor o papeles y compara la chapa con distintas luces.

Todo ponderado por la mezcla real de colores:

| Variante | Acierto, color principal | Acierto, lista al 30 % | Colores por aviso | Costo cada mil |
|---|---|---|---|---|
| mosaico de 3 fotos (multi3b) | 84,3 % | 88,4 % | 1,23 | US$ 0,11 |
| todas las fotos | **88,6 %** | **91,4 %** | 1,17 | US$ 0,25 |
| solo avisos con 4+ fotos: mosaico de 3 | 85,5 % | 90,2 % | 1,23 | — |
| solo avisos con 4+ fotos: todas | **89,7 %** | **91,8 %** | 1,12 | — |

Con todas las fotos la IA acierta más y además duda menos: la lista sale más corta y más limpia. En la búsqueda de azul con lista, lo que trae que es de verdad azul pasa del 53 % al 63 %, y en negro del 77 % al 81 %. Cuesta 2,3 veces más, pero sigue siendo poco. La demora casi no cambia: 1,4 s.

Las cifras de esta tabla son de una segunda muestra y no se comparan una a una con las de arriba. La parte de Facebook, deRuedas y Rosario Garage cambió (se toman avisos recientes), así que no se volvió a etiquetar a mano. Ahí la IA ya acertaba 97–100 % con 3 fotos.

### ¿Hay un modelo especializado mejor? (consulta del 12/11)

| Opción | Costo cada mil avisos | Comentario |
|---|---|---|
| gpt-6-luna (el que usamos) | US$ 0,25 con todas las fotos; la mitad por la Batch API | Medido acá. |
| Claude Haiku 5.5 | Parecido (mismo precio por token) | Único rival real; habría que medirlo con esta muestra. |
| Gemini Flash-Lite 2.5 / 3.1, Ministral, gpt-5-nano | Parecido o más caro | Sin ventaja clara; gpt-5-nano está por apagarse. |
| APIs de reconocimiento de vehículos (Plate Recognizer, Rekor) | ~US$ 1,5 a 3,75 | Pensadas para cámaras de patentes, no para fotos de avisos. |
| AWS Rekognition (color dominante) | ~US$ 0,75 | Da el color de toda la foto, no del auto: es lo mismo que «píxeles». |
| Clasificador propio (entrenado con el dataset VCoR) en el VPS | ~US$ 0 | ~90–95 % con fotos limpias de dataset. Sus errores típicos son justo los nuestros (plata/gris, beige/tostado). Hay que entrenarlo y sumarle un detector que saque interiores y motores. No hay uno listo para usar. |

Ninguna opción le gana a gpt-6-luna en precio y precisión a la vez. Lo único que ahorra de verdad es mandar la carga inicial y lo que no es urgente por la Batch API, al 50 %.

## Recomendación

1. **Primero el color declarado.** Mercado Libre, Kavak, Randazzo y Autocosmos (una vez que el parser lo lea) lo dan en casi todas las fichas, y no cuesta nada. El color declarado entra como único candidato.
2. **IA con todas las fotos para el resto** (Facebook, deRuedas, Rosario Garage y fichas sin color): hasta 10 fotos, cada una aparte, y lista de candidatos con umbral 30 %. La IA ignora las que no son exteriores.
3. **Al buscar, dos niveles**:
   - si el color principal coincide, el aviso entra normal;
   - si coincide solo un candidato secundario, entra más abajo con la marca «color parecido: puede ser verde».

   Así se aprovecha lo que la lista encuentra sin presentar como seguro lo que no lo es. Sin ningún color, sigue valiendo «sin confirmar», como decidió Juan.
4. **Costo esperado**: US$ 0,25 cada mil avisos, o US$ 0,12 por la Batch API para la carga inicial.
   - Analizar una vez todo lo activo sin color declarado son unos 26.000 avisos: unos US$ 6,5, o unos US$ 3,3 en batch. Al 12/11 eran Rosario Garage 8.971, deRuedas 8.691, Facebook 6.224 y unos 2.000 de las fuentes chicas.
   - Lo nuevo de cada día son centavos.
   - El tope diario en `app_config.color_vision.daily_cap` queda como seguro.
