# Comparación de modelos para búsqueda asistida

Fecha de verificación: 4 de octubre de 2026. Investigación de documentación oficial y una prueba real de integración con Luna; todavía no se realizó un benchmark comparativo de calidad, costo y latencia sobre los pedidos de AutoMotive.

**Decisión del usuario:** usar GPT-6 Luna por el momento. La integración y el
`.env` local están preparados y el worker ya fue activado con Luna. Una prueba
real pasó el primer caso golden; la evaluación completa de calidad sigue pendiente.
Ver [activación de Luna](LUNA.md). Los demás modelos quedan como comparación.

**Recomendación preliminar:** para resolver el pedido completo con poca complejidad, comparar GPT-6 Luna y DeepSeek Flash contra Haiku como referencia. Para clasificación, incluir Jev y GLiClass multilingüe; para extracción local, priorizar GLiNER2.5 Multi y NuExtract3. Qwen3.5 2B/4B y Gemma 4 E2B aportan controles generativos locales. Kimi K2.6, DeepSeek R1 destilado y Moonlight representan las familias solicitadas, con sus costos y límites propios. Esta selección expresa adecuación a la tarea y al hardware; no es un ranking de calidad ya medido.

## Objetivo y criterio de comparación

El trabajo a resolver combina extracción de campos, normalización y separación de pedidos de vehículos. Un modelo generativo con JSON Schema puede representar ese resultado completo; un clasificador de etiquetas necesita otras piezas para producirlo. La decisión debe basarse en exactitud sobre los casos del proyecto, omisiones/alucinaciones, JSON válido, latencia y costo por pedido resuelto, incluyendo reintentos.

## APIs: precios comparables

Escenario de cálculo, no medición: **1.000 pedidos**, cada uno con **5.000 tokens de entrada y 500 tokens de salida facturable total**, sin caché, reintentos, Batch, herramientas ni impuestos. Costo = `5 × precio_input_por_M + 0,5 × precio_output_por_M`. Los distintos tokenizadores pueden producir cantidades diferentes para el mismo texto. Si un modelo genera razonamiento adicional, los 500 tokens deben incluirlo; 500 tokens de JSON más razonamiento tendrán un costo mayor.

| Modelo / ID de API | Entrada sin caché USD/M | Lectura de caché USD/M | Salida USD/M | USD / 1.000 pedidos | Papel en la evaluación | Fuente oficial de precio |
|---|---:|---:|---:|---:|---|---|
| Jev 1.13 `jev-1.13.0` | 0,042 | No incluida | 0 | **0,21** | Clasificación; requiere extracción y normalización adicionales | [TypeSafe](https://docs.typesafe.ai/models) |
| GPT-6 Luna `gpt-6-luna` | 0,10 | 0,01 | 0,50 | **0,75** | Candidato económico principal | [OpenAI](https://developers.openai.com/api/docs/models/gpt-6-luna) |
| DeepSeek V4.1 Flash `deepseek-flash`, fuera de pico | 0,15 | 0,003 | 0,60 | **1,05** | Candidato económico principal | [DeepSeek](https://api-docs.deepseek.com/quick_start/pricing/) |
| DeepSeek V4.1 Flash `deepseek-flash`, pico | 0,30 | 0,006 | 1,20 | **2,10** | Mismo modelo; presupuesto sin depender del horario | [DeepSeek](https://api-docs.deepseek.com/quick_start/pricing/) |
| Gemini 3.5 Flash-Lite `gemini-3.5-flash-lite` | 0,30 | 0,03 | 2,50 | **2,75** | Candidato económico principal | [Google](https://ai.google.dev/gemini-api/docs/pricing) |
| DeepSeek V4 Pro `deepseek-v4-pro`, fuera de pico | 0,66 | 0,022 | 1,98 | 4,29 | Referencia de capacidad; segunda ronda | [DeepSeek](https://api-docs.deepseek.com/quick_start/pricing/) |
| Kimi K2.6 `kimi-k2.6` | 0,95 | 0,16 | 4,00 | **6,75** | Candidato Kimi con razonamiento desactivable | [Kimi](https://platform.kimi.ai/) |
| Kimi K2.7 Code `kimi-k2.7-code` | 0,95 | 0,19 | 4,00 | 6,75 | Control Kimi para cumplimiento del esquema | [Kimi](https://platform.kimi.ai/) |
| Claude Haiku 4.5 `claude-haiku-4-5-20251001` | 1,00 | 0,10 | 5,00 | **7,50** | Referencia del proveedor actual del proyecto | [Anthropic](https://platform.claude.com/docs/en/models/haiku-4-5/overview) |
| DeepSeek V4 Pro `deepseek-v4-pro`, pico | 1,32 | 0,044 | 3,96 | 8,58 | Referencia de capacidad; segunda ronda | [DeepSeek](https://api-docs.deepseek.com/quick_start/pricing/) |
| Kimi K3 `kimi-k3` | 3,00 | 0,30 | 15,00 | 22,50 | Referencia superior de Kimi; baja prioridad por costo | [Kimi](https://platform.kimi.ai/) |

DeepSeek aplica pico de lunes a viernes, **01:00–04:00 y 06:00–10:00 UTC**, excepto feriados públicos chinos; fines de semana y demás horas son fuera de pico. Los alias anteriores `deepseek-v4-flash` y `deepseek-v4-flash-vision-exp` se sirven con V4.1 Flash; para nuevas integraciones usar `deepseek-flash`. [Tarifas y alias oficiales](https://api-docs.deepseek.com/quick_start/pricing/).

La columna de caché muestra lectura; los cargos de escritura o almacenamiento que aplique cada proveedor quedan excluidos del escenario sin caché. [OpenAI](https://developers.openai.com/api/docs/models/gpt-6-luna), [Kimi](https://platform.kimi.ai/docs/pricing/chat), [Google](https://ai.google.dev/gemini-api/docs/pricing).

El proyecto está configurado con `claude_cli` y modelo `haiku`. La fila de Haiku muestra precio de API Anthropic para comparar, no una medición del costo de la suscripción o del uso mediante CLI.

Gemini 2.5 Flash-Lite conserva un precio de 0,10/0,40 USD/M, que daría **USD 0,70 por 1.000 pedidos**, pero Google restringe actualmente los modelos 2.5 a usuarios que ya los usaban. Su inclusión debe depender del acceso real de la cuenta; Google recomienda 3.5 Flash-Lite o 3.8 Flash para proyectos nuevos. [Tarifas](https://ai.google.dev/gemini-api/docs/pricing), [disponibilidad y ciclo de vida](https://ai.google.dev/gemini-api/docs/deprecations).

## APIs: estructura de salida y razonamiento

| Modelo | Salida estructurada documentada | Configuración inicial para evaluar extracción | Límite o particularidad |
|---|---|---|---|
| GPT-6 Luna | Structured Outputs | `reasoning.effort=none` | En Chat Completions, function calling requiere `reasoning_effort=none`; considerar Responses para la integración. [Modelo](https://developers.openai.com/api/docs/models/gpt-6-luna) |
| DeepSeek V4.1 Flash / V4 Pro | Chat Completions: `json_object`; Responses: `text.format` con `json_schema`; herramientas con `strict` Beta | `thinking.type=disabled` o `reasoning_effort=none` | Pensamiento activado por defecto; comprobar compatibilidad del schema real y el endpoint seleccionado. [JSON](https://api-docs.deepseek.com/guides/json_mode/), [Responses](https://api-docs.deepseek.com/api/create-response/), [strict tools](https://api-docs.deepseek.com/guides/tool_calls/), [thinking](https://api-docs.deepseek.com/guides/thinking_mode/) |
| Gemini 3.5 Flash-Lite | JSON Schema con un subconjunto admitido | `thinking_level=minimal` | Pensamiento mínimo por defecto; el límite de salida incluye tokens de pensamiento. [Estructura](https://ai.google.dev/gemini-api/docs/structured-output), [thinking](https://ai.google.dev/gemini-api/docs/thinking) |
| Kimi K2.6 | `response_format.json_schema`, `strict:true` | `thinking.type=disabled` | La documentación reconoce inestabilidad con schemas complejos: evitar `$ref`/`oneOf` innecesarios y validar después. [Schema](https://platform.kimi.ai/docs/guide/response_format), [modo instantáneo](https://platform.kimi.ai/docs/guide/kimi-k2-6-quickstart) |
| Kimi K2.7 Code | `json_schema`, `strict:true`; el fabricante lo describe como más estable en schemas complejos | Ajustar el razonamiento según controles admitidos por el endpoint | Razonamiento obligatorio; desactivarlo devuelve error. [Schema](https://platform.kimi.ai/docs/guide/response_format), [modelo](https://platform.kimi.ai/docs/guide/kimi-k2-7-code-quickstart) |
| Kimi K3 | `json_schema`, `strict:true` | `reasoning_effort=low` | Razonamiento siempre activo; default `max`. [Schema](https://platform.kimi.ai/docs/guide/response_format), [modelo](https://platform.kimi.ai/docs/guide/kimi-k3-quickstart) |
| Claude Haiku 4.5 | Structured Outputs y herramientas `strict:true` | Sin activar extended thinking | Sirve para conservar una referencia del comportamiento actual. [Estructura](https://platform.claude.com/docs/en/build-with-claude/structured-outputs), [modelo](https://platform.claude.com/docs/en/models/haiku-4-5/overview) |

JSON válido y cumplimiento estructural no demuestran que la marca, moneda, año o relación entre vehículos sea correcta. Esa exactitud se debe medir en el contrato de AutoMotive. DeepSeek además documenta contenido vacío ocasional en JSON mode; evitar limitar tanto la salida que se trunque el objeto. [Advertencias oficiales de JSON mode](https://api-docs.deepseek.com/guides/json_mode/).

DeepSeek strict tools usa el endpoint Beta, requiere `additionalProperties:false` y todas las propiedades obligatorias. No admite `minItems`/`maxItems`; por tanto el límite de cinco búsquedas debe verificarse en código. La API documenta `anyOf`, pero el schema nullable específico necesita una prueba real de compatibilidad. [Restricciones oficiales](https://api-docs.deepseek.com/guides/tool_calls/).

**Selección preliminar, no ranking de calidad medido:** primera ronda con Luna, DeepSeek Flash sin thinking, Gemini 3.5 Flash-Lite mínimo y Haiku como referencia; sumar Kimi K2.6 sin thinking y K2.7 Code para comparar las dos alternativas actuales de esa familia. K3 y DeepSeek Pro pueden entrar como referencias superiores si los candidatos económicos fallan casos relevantes. Los resultados del proyecto pueden cambiar esa prioridad.

Kimi K2.5 fue discontinuado en la API oficial el **31 de agosto de 2026** y la serie K2 el **25 de mayo de 2026**. Sus pesos publicados pueden seguir usándose localmente, pero no conviene presupuestar una nueva integración API con esos IDs. [Listado oficial y modelos retirados](https://platform.kimi.ai/docs/models).

## DeepSeek y Kimi locales

Para un MoE, los parámetros **activos** estiman parte del cómputo de cada token; no representan todos los pesos que se deben almacenar. La tabla distingue ambos. El piso Q4 es un cálculo idealizado `parámetros_totales × 4 / 8`, convertido a GiB, **no un requisito oficial ni una medición**. Faltan escalas, tensores que mantengan más precisión, caché KV, buffers y sistema operativo. Cuantizar no garantiza conservar la calidad.

| Modelo abierto | Parámetros totales / activos | Piso de pesos a 4 bits, cálculo propio | Licencia declarada | Prioridad local preliminar y fuente primaria |
|---|---|---:|---|---|
| DeepSeek R1-0528-Qwen3-8B | 8B / 8B, denso | 3,7 GiB | MIT | Control secundario razonador; medir RAM total y latencia del checkpoint cuantizado. No es V4.1 Flash pequeño. [Card oficial](https://huggingface.co/deepseek-ai/DeepSeek-R1-0528-Qwen3-8B) |
| Moonlight-16B-A3B-Instruct | 16B / 3B | 7,5 GiB | MIT | Alternativa local de Moonshot; contexto **8K**: verificar que prompt, catálogo y respuesta entren. RAM total, español argentino y agrupación de vehículos no medidos. [Card oficial](https://huggingface.co/moonshotai/Moonlight-16B-A3B-Instruct) |
| Kimi-Linear-48B-A3B-Instruct | 48B / 3B | 22,4 GiB | MIT | Ronda posterior: memoria disponible, cuantización y runtime compatibles condicionan viabilidad. El ejemplo oficial usa vLLM y kernels FLA; no se verificó en esta PC. [Card oficial](https://huggingface.co/moonshotai/Kimi-Linear-48B-A3B-Instruct) |
| DeepSeek V4.1 Flash completo | 552B backbone + 196B Engram; 8B activos en prefill / 16B en decode | ≈348 GiB para esos 748B, aproximación incompleta | MIT | Requiere infraestructura de otra escala; no es un modelo de 16B para laptop. El conteo de tensores del Hub es mayor al resumen backbone + Engram. [Card oficial](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash) |
| Kimi K2.6 completo | 1T / 32B | ≈466 GiB | Modified MIT | No adecuado para esta categoría de PC; dispone de INT4 nativo y despliegue en vLLM/SGLang/KTransformers. [Card oficial](https://huggingface.co/moonshotai/Kimi-K2.6) |
| Kimi K3 completo | 2,8T / 104B | ≈1.304 GiB | Kimi K3 License | Infraestructura de servidor; publica pesos MXFP4 y activaciones MXFP8. [Resumen oficial](https://github.com/MoonshotAI/Kimi-K3) |

R1-0528-Qwen3-8B fue destilado a partir del razonamiento de R1-0528 sobre Qwen3-8B. Es un candidato para comparar, pero su especialización en razonamiento no constituye evidencia de mejor extracción ni menor latencia. Usar el tokenizer/configuración del repositorio de DeepSeek; la card advierte que difieren del Qwen3 base. [Card oficial](https://huggingface.co/deepseek-ai/DeepSeek-R1-0528-Qwen3-8B).

Moonlight y Kimi Linear son modelos propios distintos de K2.6/K3; no heredan automáticamente su capacidad. Los benchmarks de matemática, código o contexto largo no prueban el contrato de búsqueda asistida. Su inclusión aporta una comparación local de la familia Moonshot, condicionada a compatibilidad del motor y cuantización.

Las licencias locales de Kimi no son uniformes. K2.6 declara Modified MIT; K3 usa licencia propia con condiciones para determinados servicios comerciales de modelos y productos de gran escala. Revisar la licencia del checkpoint exacto al elegirlo; la tabla no equivale a una aprobación legal. [Licencia K2.6](https://huggingface.co/moonshotai/Kimi-K2.6/blob/main/LICENSE), [licencia K3](https://github.com/MoonshotAI/Kimi-K3/blob/main/LICENSE).

## Hardware local y otros modelos abiertos

Inventario leído en esta sesión con CIM y la API local de Ollama:

| Elemento | Resultado observado |
|---|---|
| Equipo | Lenovo 82TV |
| CPU | AMD Ryzen 7 5825U, 8 núcleos / 16 hilos |
| RAM física | 37,8 GiB |
| RAM libre al inspeccionar | Aproximadamente 11,8 GiB; cambia con los procesos concurrentes |
| GPU | AMD Radeon integrada; aceleración de inferencia sin verificar |
| Ollama | Instalado y API accesible; cero modelos descargados y cero modelos cargados |

El valor de `AdapterRAM` informado por Windows no prueba memoria dedicada utilizable para inferencia. La documentación de Ollama distingue soporte AMD mediante HIP y Vulkan; hace falta verificar qué backend usa este equipo y cuánto trabajo queda en CPU. Que los pesos entren en RAM permite intentar una prueba, pero no demuestra respuesta interactiva. [Compatibilidad oficial de GPU](https://docs.ollama.com/gpu).

| Modelo local | Tamaño publicado / artefacto inicial | Papel propuesto | Observación y fuente |
|---|---|---|---|
| Qwen3.5-2B | Tag Ollama `qwen3.5:2b`: descarga **3,1 GB**, pesos Q8_0 | Control pequeño para latencia y extracción completa | Comparar también precisión equivalente: el tag 2B usa distinta cuantización al 4B. [Ollama](https://ollama.com/library/qwen3.5:2b) |
| Qwen3.5-4B | Tag `qwen3.5:4b`: descarga **4,0 GB**, pesos Q4_K_M | Candidato generativo local principal | Multilingüe; comenzar sin thinking y con salida restringida al schema. [Qwen](https://huggingface.co/Qwen/Qwen3.5-4B), [Ollama](https://ollama.com/library/qwen3.5:4b) |
| NuExtract3 | Familia nominal 4B, especializada en extracción; GGUF oficial Q4_K_M | Candidato local principal para JSON | Entrada de texto + plantilla JSON + instrucciones; probar agrupación de vehículos y jerga argentina. [Modelo](https://huggingface.co/numind/NuExtract3), [GGUF](https://huggingface.co/numind/NuExtract3-GGUF) |
| Gemma 4 E2B | Tag `gemma4:e2b`: descarga desde **4,6 GB** | Alternativa local pequeña | E2B indica 2,3B efectivos; 5,1B con embeddings. [Google](https://ai.google.dev/gemma/docs/core/model_card_4), [Ollama](https://ollama.com/library/gemma4) |
| Gemma 4 E4B | Tag `gemma4:e4b`: descarga desde **6,6 GB** | Segunda ronda si mejora exactitud | 4,5B efectivos; 8B con embeddings. Mayor tamaño no asegura mejor resultado en el contrato. [Google](https://ai.google.dev/gemma/docs/core/model_card_4), [Ollama](https://ollama.com/library/gemma4) |
| Qwen3.8-27B | 27B densos; piso Q4 calculado ≈12,6 GiB antes de buffers | Control de capacidad para otro entorno o una ronda posterior | Supera la RAM libre observada sólo con ese piso; su latencia en CPU no está medida. [Modelo oficial](https://huggingface.co/Qwen/Qwen3.8-27B) |

Las descargas se expresan en GB según el distribuidor; la RAM en GiB según el inventario. **Tamaño de descarga y consumo máximo de memoria son medidas distintas.** Los componentes multimodales y las diferencias de cuantización también alteran el artefacto. Para este caso se evalúa sólo texto.

Qwen3.5 y Gemma 4 declaran Apache 2.0. En Qwen3.5 se controla el razonamiento con `enable_thinking`; Gemma 4 usa su formato específico. El motor debe aplicar correctamente esas plantillas. [Qwen](https://huggingface.co/Qwen/Qwen3.5-4B), [Gemma](https://ai.google.dev/gemma/docs/core/model_card_4).

NuExtract3 declara Apache 2.0 y admite modo sin razonamiento; su autor recomienda empezar con éste. Emplea una plantilla de extracción propia, con conversión disponible desde JSON Schema/Pydantic. Eso exige adaptar y validar la plantilla de `SearchDrafts`, incluyendo campos opcionales. La versión GGUF publica uso con llama.cpp y Ollama; la compatibilidad real de plantilla/runtime en esta PC queda pendiente. Sus benchmarks de documentos no prueban exactitud en búsquedas de autos. [Card](https://huggingface.co/numind/NuExtract3), [distribución GGUF](https://huggingface.co/numind/NuExtract3-GGUF).

Ollama admite un JSON Schema en `format`: restringir la forma de salida ayuda a validar el contrato, pero una moneda o precio equivocados siguen siendo posibles. [Structured Outputs](https://docs.ollama.com/capabilities/structured-outputs).

El costo por token de una API externa es cero al ejecutar localmente; el costo total incluye electricidad, disponibilidad del equipo, integración y mantenimiento. En el código actual, `worker/llm/local.py` es un stub que falla con `LLMError`: ninguno de estos modelos está integrado todavía.

## Jev y modelos de clasificación y extracción

| Candidato | Ejecución / tamaño | Función que aporta | Lo que requiere para completar una búsqueda |
|---|---|---|---|
| **Jev 1.13 de TypeSafe**, `jev-1.13.0` | API; USD **0,042/M tokens de entrada**, salida gratis | Elegir etiquetas/opciones, puntuar criterios y devolver confianza | Extraer candidatos numéricos y nombres, asociarlos a cada vehículo y normalizarlos en código. Mejor rendimiento documentado en inglés; español requiere evaluación. [Modelos](https://docs.typesafe.ai/models) |
| **GLiClass Multilang Mini** | Local, ≈288M; Apache 2.0 | Clasificación de intención, transmisión, combustible o vendedor sin entrenar una cabeza nueva | Extractor de entidades/cantidades y reglas de asociación. Multilingüe, incluye español. [Card](https://huggingface.co/knowledgator/gliclass-multilang-mini) |
| **GLiClass Multilang Ultra / Edge** | Local, ≈1.720M / ≈140M; Apache 2.0 | Controles de calidad y de consumo de clasificación | Mismos límites de tarea que Mini; medir el intercambio entre calidad y latencia. [Ultra](https://huggingface.co/knowledgator/gliclass-multilang-ultra), [Edge](https://huggingface.co/knowledgator/gliclass-multilang-edge) |
| **GLiNER2.5 Multi**, `fastino/gliner2.5-multi-v1` | Local, **287M**, Apache 2.0 | Entidades, etiquetas, relaciones y registros estructurados | Normalización numérica/catálogo y comprobación de relaciones entre vehículos y filtros. [Card](https://huggingface.co/fastino/gliner2.5-multi-v1) |
| **SetFit + MiniLM multilingüe** | Local; encoder + clasificador entrenado con ejemplos etiquetados | Clasificación especializada con las categorías de AutoMotive | Dataset de entrenamiento separado del test y extractor adicional. El encoder solo devuelve embeddings. [SetFit](https://github.com/huggingface/setfit), [encoder](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2) |
| **mDeBERTa-v3-base-mnli-xnli** | Local, clasificador NLI multilingüe | Referencia de clasificación zero-shot sin entrenamiento específico | Extractor adicional; evaluar costo de cada par texto/etiqueta. Referencia, no primera elección por ser más antiguo. [Card del autor](https://huggingface.co/MoritzLaurer/mDeBERTa-v3-base-mnli-xnli) |

### Jev aplicado al contrato

Jev está documentado como API alojada; no se encontró una distribución oficial de pesos para correrlo localmente. En el escenario de 5.000 tokens por pedido, **1.000 pedidos de clasificación cuestan USD 0,21**. El precio contempla entrada, no implica que el flujo completo consuma exactamente esos tokens. [Modelos y facturación](https://docs.typesafe.ai/models).

Por ejemplo, para «Fiesta o Polo, automático, hasta 15 palos y 80 mil km», el código detectaría nombres y candidatos numéricos. Jev elegiría qué candidato representa precio, kilometraje o transmisión; el código convertiría unidades y produciría los drafts. TypeSafe publica justamente ese patrón de extracción previa + selección de opciones, que evita inventar un número fuera de los candidatos, pero no corrige candidatos omitidos por el extractor. [Cookbook oficial](https://docs.typesafe.ai/cookbooks/pre_parsed_value_extraction_cookbook).

`Choice` admite hasta **255 opciones** por pregunta, con opción explícita de ausencia/desconocido. Se pueden combinar preguntas en una llamada; cada una debe formularse con precisión para evitar copiar filtros a otro vehículo. [Choice](https://docs.typesafe.ai/primitives/choice).

La confianza ayuda a derivar casos ambiguos a un LLM, pero los umbrales deben calibrarse en el conjunto de validación. Fijar versión durante la evaluación. TypeSafe documenta debilidades de precisión numérica, comparaciones y algunos razonamientos; conservar la aritmética y las validaciones en código. [Limitaciones de Jev 1.13](https://docs.typesafe.ai/model-jaggedness/jev-1.13), [routing por confianza](https://docs.typesafe.ai/patterns/confidence-routing).

### Qué aportan los especialistas locales

GLiClass Mini merece comparar contra Jev para las decisiones categóricas. Los benchmarks del fabricante favorecen Ultra para exactitud agregada y Mini para menor tamaño; las velocidades publicadas usan una RTX PRO 6000 Blackwell, por lo que no se trasladan a este Ryzen. Tampoco permiten ordenar Jev, GLiClass y GLiNER2.5 en AutoMotive: son evaluaciones distintas, y la comparación de GLiClass con GLiNER usa checkpoints anteriores a 2.5. [Evaluación del fabricante](https://huggingface.co/knowledgator/gliclass-multilang-mini).

GLiNER2.5 Multi es la opción local más directamente alineada con entidades y relaciones de esta selección. Admite CPU sin API externa; sus pesos publicados rondan 594 MB, sin incluir el consumo de ejecución. Usar `AutoExtractor`, no el loader anterior. Su ventana codificada es finita, y la extracción independiente de relaciones no impone automáticamente todas las restricciones entre campos: validar agrupación, catálogo y resultados inviables. [Modelo](https://huggingface.co/fastino/gliner2.5-multi-v1), [biblioteca](https://github.com/fastino-ai/GLiNER2).

SetFit gana interés cuando haya suficientes pedidos reales etiquetados para entrenar y evaluar por separado. No lo elegiría como reemplazo inicial del parser: resuelve categorías definidas, mientras que cantidades, múltiples vehículos y relaciones requieren otras piezas. [Proyecto oficial](https://github.com/huggingface/setfit).

## Protocolo de evaluación y decisión

El resultado comparable es **la búsqueda normalizada completa** que puede editar y guardar el usuario. Medir sólo F1 de etiquetas o JSON válido dejaría afuera errores de precio, moneda y asociación de filtros.

El proyecto ya tiene **21 frases golden** en `worker/tests/fixtures/llm/parse_search_golden.json`, evaluadas por `worker/tests/test_llm_contract.py` y normalizadas contra el catálogo. Cubren pesos argentinos, varios vehículos, precio ideal/máximo, errores de escritura, versión estricta, vehículo desconocido, inyección de instrucciones y «tope de gama». Las pruebas con respuestas grabadas verifican el contrato existente; **no miden un modelo nuevo**.

1. **Primera ronda de adecuación:** pasar las mismas 21 frases por Luna, DeepSeek Flash, Kimi K2.6, Jev + extracción previa, GLiNER2.5 + reglas, NuExtract3, Qwen3.5-2B/4B y Gemma 4 E2B. Haiku es la referencia. GLiClass Mini se compara en los campos categóricos y como parte de un flujo completo con el mismo extractor; R1-0528-Qwen3-8B y Moonlight añaden controles locales de las familias pedidas cuando su runtime esté preparado.
2. **Elegir finalistas:** descartar variantes que fallen campos críticos o no logren latencia útil en este hardware. No descargar a la vez todos los checkpoints grandes ni concluir calidad a partir de su número de parámetros.
3. **Prueba ciega:** extender a 100–200 pedidos representativos, sin usarlos como ejemplos del prompt ni para ajustar los umbrales. Incluir negaciones («no automático»), filtros compartidos e individuales, abreviaturas locales, precios sin moneda explícita, años relativos, versiones y entradas ajenas a una búsqueda. Definir respuestas aceptables antes de consultar modelos. Mantener un conjunto separado para ajustes.

Métricas que deciden la selección:

| Métrica | Qué comprobar |
|---|---|
| Exactitud de pedido completo | Cantidad de vehículos, identidad y todos los filtros solicitados correctos después de normalizar |
| Errores críticos | Precio/moneda, mínimos vs máximos, negaciones y filtros asignados a otro vehículo; no diluirlos en un promedio de campos |
| Ausencias e invenciones | No agregar versiones, valores ni vehículos sin evidencia; respetar los defaults del contrato |
| Cobertura | Porcentaje resuelto sin segunda llamada; rechazos, timeouts y necesidad de corrección manual |
| Latencia | p50 y p95 de extremo a extremo; separar arranque en frío y modelo cargado |
| Costo real | Tokens facturables, preguntas, razonamiento, reintentos y fallback; USD por 1.000 pedidos correctos |
| Recursos locales | RAM pico, residencia real en CPU/GPU, contexto, hilos, consumo y comportamiento con otras tareas activas |
| Estabilidad | Repetir una muestra de casos ambiguos; registrar versión, cuantización, prompt, catálogo y parámetros |

Para las fechas relativas, congelar la fecha igual que el contrato actual. Medir el efecto de la cuantización en exactitud; un tag Q8 y otro Q4 no constituyen una comparación controlada de tamaño. Empezar sin razonamiento donde se admita y con un contexto que alcance para prompt + catálogo + respuesta; no reservar 128K por defecto para un pedido corto.

«Tope de gama» requiere datos fiables de versiones y años. El catálogo actual enumera versiones, pero no aporta toda esa jerarquía temporal; enriquecer o limitar esa regla puede mejorar todos los modelos. Un benchmark debe distinguir falta de evidencia del catálogo de fallos de extracción.

### Decisión económica provisional

Con el escenario indicado, Luna cuesta USD 0,75 por 1.000 pedidos completos y Jev USD 0,21 por 1.000 llamadas de clasificación. Son tarifas calculadas; **no son costos medidos por pedido correcto**. A volumen pequeño, una API generativa económica evita implementar y mantener un parser híbrido antes de saber si ahorra lo suficiente.

Si el flujo especializado alcanza la exactitud y latencia requeridas, evaluar **GLiNER2.5 + normalización determinista + fallback a Luna/DeepSeek** o **Jev + candidatos + fallback**. Como ejemplo puramente aritmético, Jev a USD 0,21 más Luna en el 20% de los pedidos a la tarifa del escenario sería USD 0,36/1.000, antes de otros costos y suponiendo esa cobertura. El porcentaje real y los tokens deben medirse; un clasificador adicional que deriva casi todo aumenta el costo.

La decisión final debe minimizar costo entre los candidatos que alcancen una calidad y latencia aceptables. Prioridad actual: **Luna/DeepSeek Flash para simplicidad; Jev/GLiClass para clasificación; GLiNER2.5/NuExtract3 para extracción local**. Kimi K3, DeepSeek completo y Kimi completo quedan como referencias de capacidad o infraestructura, no como primera inversión para este equipo.

## Estado del trabajo en el proyecto

La nueva búsqueda ya tiene `defaultValue="assisted"` en `web/app/app/searches/new/page.tsx`; las pruebas e2e fueron adaptadas. Cambio local, sin publicación. Tras elegir Luna, se integró el proveedor OpenAI y se preparó el `.env` con `LLM_PROVIDER=openai` y `OPENAI_MODEL=gpt-6-luna`. La API key se completa manualmente en ese archivo. Después de completar la clave, una llamada real pasó el primer caso golden y el supervisor reinició el worker con Luna. No se descargaron modelos. Las pruebas HTTP simuladas verifican el adaptador; la prueba real confirma una búsqueda, mientras que el benchmark completo propuesto sigue pendiente.
