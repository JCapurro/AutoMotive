"""Writing and checking the messages: two `claude -p` roles with different
instructions, and the hard rules (rules.py) in between.

    draft (2 variants each) → rules → review → [one rewrite → rules → review] → chosen | dropped

A prospect whose message does not pass is dropped for today, never sent with
a doubt. Batches of 5 to 10 prospects per call to spare the subscription.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable

from prospector import claude, rules

WRITER_MODEL = "claude-opus-5-5"
REVIEWER_MODEL = "claude-opus-5-5"
HOOK_TYPES = ("oportunidad", "stock_viejo", "precio_vs_zona", "demanda", "dejaron_de_publicarse")

WRITER_SYSTEM = """Escribís mensajes de WhatsApp que Juan manda desde su celular a agencias de autos usados y a personas que compran y venden autos. No lo conocen. Juan armó Ese Auto, una herramienta que lee los avisos nuevos de los portales y avisa cuando aparece un auto publicado por debajo de los parecidos. El objetivo del primer mensaje es UNO: que contesten. Para eso tienen que entender en una lectura qué les ofrecés y para qué les sirve; un dato suelto sin decir qué es Ese Auto genera «no entiendo» o «¿de qué auto me hablás?» (Juan, 16/11/2026). No hablás de precios de Ese Auto, pero sí decís claro qué hace por ellos.

Por cada prospecto recibís un JSON de hechos verificados. Escribí 2 variantes distintas, cada una marcada con su tipo de gancho:
- oportunidad: un auto de los "ganchos" (un particular lo publicó hace poco, en su zona, un X % más barato que N parecidos). Si hay ganchos, las dos variantes son de este tipo: con los dos autos si hay dos, o con el mismo auto y otra forma de explicar Ese Auto si hay uno. Va como EJEMPLO del aviso que les llegaría ("Ejemplo de hoy: …"), nunca como un auto suelto. Si "de_sus_modelos" es false, el auto no es de un modelo que trabajan: sirve igual para mostrar cómo funciona, pero no digas ni des a entender que es de sus modelos ("Para que veas cómo es, uno de hoy en Rosario: …").
- demanda: cuántas búsquedas activas de un modelo suyo hay en Ese Auto cerca (solo si está en los hechos). Úsalo solo si no hay ganchos.
- stock_viejo, precio_vs_zona y dejaron_de_publicarse hablan de SU stock: en el primer mensaje no se usan (ver regla 5).
Las dos variantes tienen que ser realmente distintas (otro auto u otra forma de decirlo), no la misma con otras palabras.
Para decir cuándo apareció el auto del gancho usá el campo "publicado" ("hoy", "ayer", "anteayer"), nunca las horas.
Cada mensaje es para una persona distinta: no arranques todos con la misma fórmula; que suene escrito para ese vendedor (su modelo, su ciudad).

Reglas, todas obligatorias:
1. Castellano rioplatense con voseo ("tenés", "querés", "mirá"), tono de WhatsApp entre personas: frases cortas, nada de lenguaje de folleto, nada de "estimado", "le escribo", "potenciar", "solución", "herramienta innovadora".
2. Máximo 480 caracteres en total, en 3 o 4 párrafos cortos separados por una línea en blanco.
3. El mensaje arranca EXACTAMENTE con el campo "saludo" de los hechos ("Hola, Julio.", "Hola, ¿cómo andan?"), sin cambiarlo y sin agregarle el nombre del negocio. La pregunta del saludo no cuenta: la del final es la única otra.
4. Quien lo lee no conoce a Juan ni a Ese Auto: antes de cualquier dato tiene que entender quién le escribe y qué es la plataforma (Juan, 17/11/2026: «habría que explicar la función de la plataforma para que el usuario entienda quién les habla»). Estructura, en este orden y en párrafos separados:
   (a) el saludo, y Juan se presenta y dice QUÉ ES Ese Auto: una página que revisa todo el día los avisos de autos usados de los portales (Mercado Libre, Facebook y otros, como en "producto");
   (b) QUÉ HACE por ellos, en una frase simple: cuando un particular publica un auto más barato que los parecidos, les llega un aviso en el momento; a una agencia le sirve para comprar stock antes que otro (muchas ya tienen a alguien que les busca autos: es una ayuda para ellos o para quien les busca los autos, nunca algo que lo reemplaza);
   (c) el gancho como EJEMPLO de ese aviso ("Ejemplo de hoy: …"); si no hay ganchos, este párrafo puede faltar o ser un dato de "demanda", nunca el precio de un auto de ellos;
   (d) la pregunta.
   Ejemplo de la forma (no copies el texto ni los números): "Hola, ¿cómo andan? Soy Juan, de Ese Auto. Es una página que revisa todo el día los avisos de autos usados de Mercado Libre, Facebook y otros portales.

Cuando un particular publica un auto más barato que los parecidos, les llega un aviso en el momento. A una agencia le sirve para comprar stock antes que otro.

Ejemplo de hoy: un Gol Power 2012 en CABA a $7.200.000, 19 % más barato que otros 87 Gol parecidos publicados.

¿Quieren probarlo gratis una semana?"
   Los porcentajes, en palabras de todos los días: "19 % más barato que otros 87 Gol parecidos publicados", nunca "19 % abajo de 87 parecidos".
5. No uses datos de SU stock ("vi que tienen 15 autos", "su Ka está entre los más baratos"): confunden y hacen parecer que el mensaje es sobre sus autos. El mensaje es sobre qué es Ese Auto y qué les avisaría.
6. Termina con UNA sola pregunta, fácil de contestar con "sí" o con una palabra, que los lleve a probarlo: "¿Quieren probarlo gratis una semana?", "¿Te lo armo gratis una semana para tus modelos?". Escribí "una semana" en letras, no "7 días". Fuera del saludo, es el único signo de pregunta del mensaje y va al final.
7. Sin links, sin el precio del plan ni ningún precio de Ese Auto, sin la palabra "IA" ni "inteligencia artificial", con 0 o 1 emoji.
8. Nunca "vendido" ni "se vendió": se dice "dejó de publicarse". Nada de prometer ganancias, márgenes ni "negocio seguro". Los precios son "publicados", no de venta.
9. TODO número que escribas (precios, porcentajes, cantidades, días, años, km) sale tal cual del JSON de hechos. No sumes, no restes, no redondees distinto, no inventes. Copiá los precios con el formato del JSON ("$14.500.000", "US$ 12.000"). Para los km usá "km_texto" tal cual ("104.000 km"), nunca el número crudo de "km". Si un dato no está, no lo uses.
10. No digas cómo conseguiste su número. No uses "particular" para hablar de él. A una agencia la tratás en singular (vos, la persona que lee) o en plural con "ustedes"; nunca "usted".

Para "paso": "seguimiento" o "ultimo" (ya le escribiste antes, ver "mensajes_anteriores"): NO preguntes si vio el mensaje ni lo repitas. Recordá en media frase qué hace Ese Auto y traé un gancho NUEVO de "ganchos" (otro auto) como ejemplo, o un dato nuevo de su stock, en 2 párrafos como mucho. En el "ultimo", dejá claro con naturalidad que no le vas a insistir más, sin dramatizar y sin línea de baja.

Si hay "ejemplos_que_obtuvieron_respuesta", tomá de ellos el tono y el largo, no el texto.
Respondé solo con el JSON del esquema."""

REVIEWER_SYSTEM = """Sos el control de calidad de mensajes de WhatsApp que Juan, fundador de Ese Auto, va a mandar a agencias y revendedores de autos que no lo conocen. Otra persona los escribió. Tu trabajo es que no salga ningún mensaje con un dato falso, una regla rota o un tono que haga que no contesten o lo bloqueen.

Por cada prospecto recibís los hechos (JSON verificado) y 2 variantes, cada una con los problemas que ya detectó un control automático (si tiene alguno, esa variante no se puede elegir).

Revisá cada variante, en este orden:
1. Cotejá CADA número y CADA afirmación contra los hechos: precios (formato y valor exacto), km (con el formato de "km_texto"; "104000 km" sin el punto es error), porcentajes, cantidades de comparables, días, años, modelos, versiones, lugar, fuente, que el gancho sea de un particular y de las últimas horas. Un gancho a más de 60 km del vendedor ("distancia_km" mayor a 60) es un error: no está en su zona. Un gancho que no es de sus modelos ("de_sus_modelos": false) está permitido como ejemplo de cómo funciona; el error es decir o dar a entender que es de un modelo que trabajan. Una afirmación que los hechos no sostienen ("está muy barato", "se va a vender rápido", "tus autos están caros" sin el dato) es un error.
2. Reglas: voseo rioplatense; máximo 500 caracteres y 3 o 4 párrafos; arranca exactamente con el "saludo" de los hechos (su pregunta no cuenta); Juan se presenta ("Soy Juan") y dice QUÉ ES Ese Auto (una página que revisa los avisos de los portales) antes de cualquier dato; dice QUÉ HACE por ellos (cuando un particular publica un auto más barato que los parecidos, les llega un aviso en el momento, para comprar stock antes que otro); el gancho va después, como ejemplo de ese aviso; no usa datos del stock de ellos ("vi que tienen 15 autos", "su Ka está entre los más baratos": es error); una sola pregunta, al final, fácil de contestar, que invite a probarlo; sin links, sin precio del plan, sin "IA", 0 o 1 emoji; nunca "vendido" (se dice "dejó de publicarse"); nada de prometer ganancias.
3. Claridad, lo más importante: leelo como un agenciero que no conoce a Juan. ¿Entiende en una lectura qué le ofrecen y para qué le sirve? Si podría contestar "no entiendo", "¿de qué auto me hablás?" o "¿quién sos?", es error (pasó con mensajes que solo traían el auto). Un porcentaje dicho como "19 % abajo de 87 parecidos" en vez de "19 % más barato que otros 87 … parecidos" es error de claridad.
4. Tono: ¿lo escribiría una persona en WhatsApp? ¿Suena a spam, a folleto o a robot? ¿Es respetuoso sin ser servil? ¿El gancho es interesante para ESTE vendedor?

Decisión por prospecto:
- "elegir": al menos una variante pasa todo. Elegí la que tenga más chances de respuesta (índice 0 o 1) y decí en una línea por qué.
- "reescribir": ninguna pasa pero se puede arreglar. Escribí instrucciones concretas para quien redacta (qué cambiar y por qué), sin escribir vos el mensaje.
- "descartar": los hechos no alcanzan para un mensaje bueno, o ya se reescribió y sigue mal.
Si en el pedido dice "ultima_revision": true, no podés pedir "reescribir": elegís o descartás.
Respondé solo con el JSON del esquema."""

DRAFT_SCHEMA = {
    "type": "object",
    "properties": {"mensajes": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "prospecto": {"type": "string"},
            "variantes": {"type": "array", "minItems": 2, "maxItems": 2, "items": {
                "type": "object",
                "properties": {"tipo_gancho": {"type": "string", "enum": list(HOOK_TYPES)},
                               "texto": {"type": "string"}},
                "required": ["tipo_gancho", "texto"], "additionalProperties": False}},
        },
        "required": ["prospecto", "variantes"], "additionalProperties": False}}},
    "required": ["mensajes"], "additionalProperties": False,
}

REVIEW_SCHEMA = {
    "type": "object",
    "properties": {"revisiones": {"type": "array", "items": {
        "type": "object",
        "properties": {
            "prospecto": {"type": "string"},
            "decision": {"type": "string", "enum": ["elegir", "reescribir", "descartar"]},
            "variante_elegida": {"type": ["integer", "null"], "minimum": 0, "maximum": 1},
            "problemas": {"type": "array", "items": {"type": "string"}},
            "instrucciones": {"type": "string"},
            "por_que": {"type": "string"},
        },
        "required": ["prospecto", "decision", "variante_elegida", "problemas", "instrucciones", "por_que"],
        "additionalProperties": False}}},
    "required": ["revisiones"], "additionalProperties": False,
}

FALLBACK_EXAMPLE = {
    "nota": "Ilustración del tono y del largo, con datos inventados: no copies el texto ni los números.",
    "texto": ("Hola, Martín. Soy Juan, de Ese Auto. Es una página que revisa todo el día los avisos de autos "
              "usados de Mercado Libre, Facebook y otros portales.\n\nCuando un particular publica un auto más "
              "barato que los parecidos, te llega un aviso en el momento: te sirve para comprar stock antes que "
              "otro.\n\nEjemplo de hoy: un Corolla XEI 2017 en Funes a $19.800.000, 12 % más barato que otros 31 "
              "Corolla parecidos publicados.\n\n¿Te lo armo gratis una semana con tus modelos?"),
}


def _spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text or "")


def hook_used(text: str | None, hooks: list[dict[str, Any]]) -> dict[str, Any] | None:
    """The hook car a message offers: the one whose published price is in the text.
    The writer may use any of the hooks, not only the first. None when it offers no car."""
    body = _spaces(text or "")
    return next((h for h in hooks if h.get("precio_publicado") and _spaces(h["precio_publicado"]) in body), None)


@dataclass
class Job:
    """One prospect's message being written today."""
    pid: str                         # stable id inside the run ("p1", "p2"...)
    facts: dict[str, Any]
    variants: list[dict[str, Any]] = field(default_factory=list)
    review: dict[str, Any] = field(default_factory=dict)
    history: list[dict[str, Any]] = field(default_factory=list)
    chosen: int | None = None
    dropped: str | None = None

    @property
    def text(self) -> str | None:
        return self.variants[self.chosen]["texto"] if self.chosen is not None else None

    @property
    def hook_type(self) -> str | None:
        return self.variants[self.chosen]["tipo_gancho"] if self.chosen is not None else None

    @property
    def hook(self) -> dict[str, Any] | None:
        return hook_used(self.text, self.facts.get("ganchos") or [])


def _facts_for_model(facts: dict[str, Any]) -> dict[str, Any]:
    """The facts without what the writer must never echo (URLs, ids)."""
    def strip(value: Any) -> Any:
        if isinstance(value, dict):
            return {k: strip(v) for k, v in value.items() if k not in ("url", "listing_id", "verificado")}
        if isinstance(value, list):
            return [strip(v) for v in value]
        return value
    return strip(facts)


def _checked(job: Job) -> None:
    for v in job.variants:
        v["problemas_automaticos"] = rules.check(v.get("texto", ""), job.facts)


def draft(jobs: list[Job], *, examples: list[dict[str, Any]], call: Callable[[claude.Call], dict],
          feedback: dict[str, str] | None = None) -> None:
    payload = {
        "ejemplos_que_obtuvieron_respuesta": examples or [FALLBACK_EXAMPLE],
        "prospectos": [{"prospecto": j.pid, "hechos": _facts_for_model(j.facts),
                        **({"version_anterior": [{"tipo_gancho": v["tipo_gancho"], "texto": v["texto"]}
                                                 for v in j.variants],
                            "pedido_de_correccion": feedback[j.pid]} if feedback and j.pid in feedback else {})}
                       for j in jobs],
    }
    out = call(claude.Call(system=WRITER_SYSTEM, user=json.dumps(payload, ensure_ascii=False, default=str),
                           schema=DRAFT_SCHEMA, model=WRITER_MODEL, effort="high"))
    by = {m.get("prospecto"): m for m in out.get("mensajes", [])}
    for j in jobs:
        m = by.get(j.pid)
        if j.variants:
            j.history.append({"variantes": j.variants, "revision": j.review})
        j.variants = [{"tipo_gancho": v["tipo_gancho"], "texto": v["texto"].strip()}
                      for v in (m or {}).get("variantes", [])][:2]
        if len(j.variants) < 2:
            j.dropped = "la redacción no devolvió dos variantes"
        _checked(j)


def review(jobs: list[Job], *, call: Callable[[claude.Call], dict], last: bool) -> None:
    payload = {
        "ultima_revision": last,
        "prospectos": [{"prospecto": j.pid, "hechos": _facts_for_model(j.facts),
                        "variantes": [{"indice": i, **v} for i, v in enumerate(j.variants)]} for j in jobs],
    }
    out = call(claude.Call(system=REVIEWER_SYSTEM, user=json.dumps(payload, ensure_ascii=False, default=str),
                           schema=REVIEW_SCHEMA, model=REVIEWER_MODEL, effort="high"))
    by = {r.get("prospecto"): r for r in out.get("revisiones", [])}
    for j in jobs:
        r = by.get(j.pid) or {"decision": "descartar", "problemas": ["la revisión no lo devolvió"],
                              "instrucciones": "", "por_que": "", "variante_elegida": None}
        j.review = r
        idx = r.get("variante_elegida")
        if r["decision"] == "elegir" and idx in (0, 1) and idx < len(j.variants) \
                and not j.variants[idx]["problemas_automaticos"]:
            j.chosen = idx
        elif r["decision"] == "elegir":
            # It chose a variant the hard rules reject: that is not a pass.
            r["decision"] = "descartar" if last else "reescribir"
            r["instrucciones"] = (r.get("instrucciones") or "") + " Problemas automáticos: " + "; ".join(
                p for v in j.variants for p in v["problemas_automaticos"])


def write_all(jobs: list[Job], *, examples: list[dict[str, Any]], call: Callable[[claude.Call], dict],
              batch: int = 6, log: Callable[[str], None] = print) -> None:
    """Fills chosen/dropped on every job."""
    for start in range(0, len(jobs), batch):
        part = [j for j in jobs[start:start + batch] if not j.dropped]
        if not part:
            continue
        log(f"  redactando {len(part)} (tanda {start // batch + 1})")
        _guard(lambda: draft(part, examples=examples, call=call), part, "redacción")
        ready = [j for j in part if not j.dropped]
        _guard(lambda: review(ready, call=call, last=False), ready, "revisión")
        again = [j for j in ready if j.chosen is None and not j.dropped and j.review.get("decision") == "reescribir"]
        for j in ready:
            if j.chosen is None and not j.dropped and j.review.get("decision") != "reescribir":
                j.dropped = "la revisión lo descartó: " + "; ".join(j.review.get("problemas") or [])
        if again:
            log(f"  reescribiendo {len(again)}")
            feedback = {j.pid: _feedback(j) for j in again}
            _guard(lambda: draft(again, examples=examples, call=call, feedback=feedback), again, "reescritura")
            ready2 = [j for j in again if not j.dropped]
            _guard(lambda: review(ready2, call=call, last=True), ready2, "segunda revisión")
            for j in ready2:
                if j.chosen is None and not j.dropped:
                    j.dropped = "no pasó la segunda revisión: " + "; ".join(j.review.get("problemas") or [])


def _feedback(job: Job) -> str:
    auto = sorted({p for v in job.variants for p in v.get("problemas_automaticos", [])})
    parts = [job.review.get("instrucciones") or ""]
    if job.review.get("problemas"):
        parts.append("Problemas: " + "; ".join(job.review["problemas"]))
    if auto:
        parts.append("Control automático: " + "; ".join(auto))
    return " ".join(p for p in parts if p).strip()


def _guard(fn: Callable[[], None], jobs: Iterable[Job], stage: str) -> None:
    try:
        fn()
    except claude.ClaudeError as error:
        for j in jobs:
            if not j.dropped and j.chosen is None:
                j.dropped = f"falló la {stage}: {error}"
