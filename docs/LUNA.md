# GPT-6 Luna en el worker

La búsqueda asistida usa `LLM_PROVIDER=openai`, con `OPENAI_MODEL=gpt-6-luna`.
El proveedor conserva los prompts, schemas y normalización del proyecto.

## Completar la clave

Editar únicamente `OPENAI_API_KEY` en el `.env` de la raíz del proyecto:

```dotenv
LLM_PROVIDER=openai
OPENAI_MODEL=gpt-6-luna
OPENAI_API_KEY=
```

Crear la clave en [OpenAI Platform](https://platform.openai.com/api-keys).
La cuenta de API necesita acceso al modelo y saldo/facturación habilitada;
la integración no verifica esos permisos mientras la clave está vacía.
La clave es un secreto del worker; no necesita una variable en Vercel ni en
`web/.env.local`. El `.env` está excluido de Git.

## Comprobar y arrancar

Desde la raíz del proyecto, una comprobación local sin API ni base de datos:

```powershell
Push-Location worker
python -m tools.check_llm
Pop-Location
```

Debe indicar `openai:gpt-6-luna` y configuración lista. Este comando no consume
tokens ni comprueba que la clave sea válida.

Reiniciar el proceso del worker que ya está corriendo para que relea el `.env`.
Si se ejecuta manualmente, detener su proceso actual y volver a ejecutar
`python main.py` desde `worker/`. Si está instalado mediante las tareas de
`ops/install-tasks.ps1`, reiniciar la tarea `Worker` bajo `\AutoMotive\`.
No iniciar un segundo bot en paralelo.

Después, crear una búsqueda desde la web. Los logs de `logs/worker.log`
deben mostrar `llm_jobs: openai:gpt-6-luna` y contadores de tokens en una
respuesta exitosa. Esa prueba real sí utiliza la API y tiene costo.

## Parámetros y fallos

- API: `POST https://api.openai.com/v1/responses`.
- `reasoning.effort=none`; máximo de salida: 4.096 tokens.
- JSON Schema estricto y validación posterior con Pydantic.
- `store=false`, sin herramientas ni búsqueda web.
- `LLM_TIMEOUT_SECONDS=60`: presupuesto total con un reintento incluido para
  conexión, 429 o 5xx; un timeout no se reintenta.
- Clave ausente: error controlado al pedir un trabajo LLM, sin detener los
  otros bucles del worker. 401 indica clave rechazada; 429 puede indicar
  límite de pedidos o cuota. Los errores guardados no incluyen clave ni texto
  del usuario.

Fuentes: [Luna](https://developers.openai.com/api/docs/models/gpt-6-luna),
[Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs).

## Validación disponible

Las pruebas del adaptador simulan HTTP con las 21 respuestas existentes y
cubren errores, rechazo, salida incompleta, schema, timeout y reintentos.
Esto verifica integración y contrato; no mide la calidad real de Luna.

Verificación real del 4 de octubre de 2026: la API respondió HTTP 200 con
`gpt-6-luna`. El caso golden `fiesta-titanium` pasó el contrato y la
normalización en 4,16 s, con 3.023 tokens de entrada y 96 de salida.
Se reinició el worker existente mediante su supervisor; el log confirmó
`llm_jobs: openai:gpt-6-luna, 1 a la vez`. Había un único proceso del worker
después del reinicio. Esta prueba verifica una búsqueda y la activación;
la evaluación completa de calidad del modelo sigue pendiente.
