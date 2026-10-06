"""Every user-facing string of the intelligence layer (§19, §24, §25).

Kept in one place so the copy lint (tests/test_intelligence_copy.py) can check
it: prices are "publicados" and compared against the "mercado observado" /
"publicaciones comparables"; red flags are "conviene verificar", never a
claim of fraud or a mechanical problem. The words §19 forbids are listed in
FORBIDDEN_TERMS and must not appear in any template.
"""
from __future__ import annotations


# §19: "vale exactamente", "precio real", "tasación oficial" — and their stems.
FORBIDDEN_TERMS = ("vale", "valor real", "precio real", "tasacion", "tasación", "tasado")


def money(amount: float | None, currency: str | None) -> str:
    """USD 10.300 · ARS 12.500.000 (Argentine thousands separator)."""
    if amount is None:
        return "sin precio"
    return f"{currency or ''} {int(round(amount)):,}".replace(",", ".").strip()


def number(value: float | int | None) -> str:
    return "—" if value is None else f"{int(round(value)):,}".replace(",", ".")


def ago(hours: float) -> str:
    minutes = int(hours * 60)
    if minutes < 60:
        return f"{max(minutes, 1)} min"
    if hours < 48:
        return f"{int(hours)} h"
    return f"{int(hours // 24)} días"


# ---------------------------------------------------------------------------
# match_reasons details
# ---------------------------------------------------------------------------

NOT_INFORMED = "la publicación no lo informa"
REASON = {
    "model_other": "es {actual}, se busca {wanted}",
    "year_range": "{year} ∈ {lo}–{hi}",
    "year_out": "{year} fuera de {lo}–{hi}",
    "price_ok": "{shown} ≤ {cap}",
    "price_over": "{shown} > {cap}",
    "price_under": "{shown} < {floor}",
    "price_partial": "el precio publicado parece un anticipo o una cuota",
    "no_fx": "no hay cotización para convertir {currency}",
    "km_ok": "{km} ≤ {cap}",
    "km_over": "{km} > {cap}",
    "km_under": "{km} < {floor}",
    "transmission_other": "es {actual}, se busca {wanted}",
    "fuel_other": "es {actual}, se busca {wanted}",
    "distance": "{place} · {km} km",
    "distance_over": "{place} · {km} km (máximo {radius} km)",
    "no_coords": "no se pudo ubicar la publicación",
    "source_other": "fuente {source} no elegida",
    "trim_preferred": "{trim} (preferida)",
    "trim_other": "{trim}, se prefiere {wanted}",
    "seller_ok": "vendedor {kind}",
    "seller_other": "vendedor {kind}, se prefiere {wanted}",
    "color_ok": "color {color}",
    "color_other": "color {color}, se prefiere {wanted}",
}
TRANSMISSION = {"manual": "manual", "automatic": "automática"}
SELLER = {"private": "particular", "dealer": "concesionaria"}
UNKNOWN_BADGE = "❔ no informado"

# ---------------------------------------------------------------------------
# score_breakdown explanations (sección 6.3)
# ---------------------------------------------------------------------------

EXPLAIN = {
    "price_below": "{pct}% debajo del mercado observado · publicaciones comparables (n={n})",
    "price_above": "{pct}% arriba del mercado observado · publicaciones comparables (n={n})",
    "price_at": "en línea con el mercado observado · publicaciones comparables (n={n})",
    "price_few": "sin comparables suficientes (n={n})",
    "match": "cumple {met}/{total} preferencias",
    "match_none": "sin preferencias adicionales",
    "match_unknown": "{names} no informado",
    "km_less": "{pct}% menos km que publicaciones comparables",
    "km_more": "{pct}% más km que publicaciones comparables",
    "km_same": "km en línea con publicaciones comparables",
    "km_none": "sin datos de km para comparar",
    "trim_preferred": "versión {trim} (preferida)",
    "trim_other": "versión {trim}",
    "trim_unknown": "versión no informada",
    "trim_any": "sin versión preferida",
    "recency_published": "publicado hace {ago}",
    "recency_detected": "detectado por primera vez hace {ago}",
    "recency_unknown": "fecha de publicación no informada; no suma por novedad",
    "completeness": "{have}/{total} datos informados",
}
# Hard-filter names in "transmisión no informada".
FILTER_NAMES = {"model": "modelo", "year": "año", "price": "precio", "km": "km",
                "transmission": "transmisión", "fuel": "combustible", "location": "ubicación",
                "trim": "versión"}

LEVEL_LABEL = {"high": "🔥 Alta oportunidad", "good": "🟢 Buena coincidencia",
               "match": "🟡 Coincidencia", "low": "⚪ Baja prioridad"}

# ---------------------------------------------------------------------------
# Red flags (§24): "información que conviene verificar"
# ---------------------------------------------------------------------------

RED_FLAG = {
    "damage_mentioned": "El vendedor menciona daños o antecedentes de choques: conviene verificar su alcance.",
    "commercial_use": "El vendedor declara uso comercial: conviene conocer el uso y mantenimiento que tuvo.",
    "service_unavailable": "El vendedor indica que no tiene historial de mantenimiento: conviene pedir más detalles.",
    "timing_pending": "El vendedor indica que la distribución no está hecha: conviene verificar qué trabajo queda pendiente.",
    "vtv_pending": "El vendedor indica que no tiene VTV vigente: conviene verificar qué falta resolver.",
    "no_owners": "No especifica cantidad de dueños: conviene verificar.",
    "no_service": "No informa services: conviene verificar el historial.",
    "no_timing_belt": "No informa la distribución: conviene verificar cuándo se cambió.",
    "much_cheaper": "Publicación {pct}% más barata que publicaciones comparables: conviene verificar por qué.",
    "much_cheaper_anticipo": ("Publicación {pct}% más barata que publicaciones comparables: "
                              "conviene verificar que el precio publicado no sea un anticipo."),
    "short_description": "Descripción muy corta: conviene pedir más información.",
    "low_km_for_age": ("Kilometraje bajo para la antigüedad ({km_per_year} km por año): "
                       "conviene verificar que sea el original."),
    "partial_price_suspect": "Conviene verificar que el precio publicado sea el total y no un anticipo.",
    "repost": "Parece una publicación re-publicada: conviene verificar hace cuánto está a la venta.",
    "price_mismatch": "La descripción menciona otro precio ({price}): conviene verificar cuál está vigente.",
    "year_mismatch": "La descripción dice año {year}, distinto del publicado: conviene verificarlo.",
    "km_mismatch": "La descripción dice {km} km, distinto de lo publicado: conviene verificarlo.",
}

# ---------------------------------------------------------------------------
# Seller questions (§25). The web only copies the text; nobody is contacted.
# ---------------------------------------------------------------------------

QUESTION = {
    "timing_pending": "Sobre la distribución pendiente, ¿qué trabajo necesita? ¿Tenés un presupuesto?",
    "condition_photos": "¿Podés compartir fotos recientes para revisar el estado de chapa y pintura?",
    "maintenance_details": "Si no tenés historial, ¿qué mantenimiento se le hizo y qué trabajos tiene pendientes?",
    "damage_scope": "Sobre los daños que mencionás, ¿me compartís fotos y el detalle de lo reparado o pendiente? ¿Tenés un presupuesto?",
    "commercial_history": "¿Durante cuánto tiempo tuvo uso comercial y qué mantenimiento se le hizo?",
    "service_proof": "¿Tenés los comprobantes del mantenimiento que mencionás?",
    "timing_proof": "¿En qué fecha y kilometraje se hizo la distribución? ¿Tenés el comprobante?",
    "vtv_pending": "¿Qué falta resolver para la VTV?",
    "documentation": "Sobre la documentación que mencionás, ¿me confirmás titularidad, deudas y si está listo para transferir?",
    "cash_offer": "Como mencionás que el precio es conversable, ¿cuál sería tu mejor precio de contado?",
    "greeting": "Hola, ¿cómo estás?",
    "available": "¿Lo seguís teniendo?",
    "holder": "¿Sos titular?",
    "owners": "¿Cuántos dueños tuvo?",
    "timing_belt": "¿Cuándo se hizo la distribución por última vez?",
    "vtv": "¿Tiene VTV vigente?",
    "crashes": "¿Tuvo choques o reparaciones importantes?",
    "services": "¿Tenés historial de services?",
    "km_unknown": "¿Cuántos km tiene?",
    "km_original": "¿El kilometraje es original? ¿Tenés cómo acreditarlo?",
    "transmission": "¿Es manual o automático?",
    "total_price": "¿El precio publicado es el total o es un anticipo?",
    "price_confirm": "¿Me confirmás el precio? En la descripción figura otro.",
    "year_confirm": "¿De qué año es? La publicación y la descripción no coinciden.",
    "km_confirm": "¿Cuántos km tiene? La publicación y la descripción no coinciden.",
    "trim": "¿Qué versión es?",
}
