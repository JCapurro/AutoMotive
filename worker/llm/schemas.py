"""What the LLM may answer (sección 8.1).

Each Pydantic model is used twice: its JSON Schema goes to the provider as the
structured-output contract (`claude -p --json-schema`, a local server's JSON
mode) and the answer is validated against the same model. Every field is
required but nullable, the strict structured-output shape: the model says
"not mentioned" with null instead of leaving keys out.

Only types are checked here. Ranges (a year in the future, a negative price)
are the deterministic normalization's job (normalization/drafts.py), which
fixes or drops the value and tells the user why, instead of failing the job.
"""
from __future__ import annotations

import copy
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

# The web form's vocabulary (web/lib/copy.ts).
Currency = Literal["USD", "ARS"]
Transmission = Literal["manual", "automatic"]
Fuel = Literal["nafta", "diesel", "gnc", "hibrido", "electrico"]
SellerType = Literal["private", "dealer"]

MAX_VEHICLES = 5


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SearchDraft(_Strict):
    """One vehicle the user is looking for: a proposed Search Profile (sección 4.3)."""

    make: str | None = Field(description="Marca, p. ej. «Ford». null si no se dice y el modelo no la implica.")
    model: str | None = Field(description="Modelo sin la versión, p. ej. «Fiesta», «Gol Trend», «Corolla Cross».")
    trim: str | None = Field(description="Versión o nivel de equipamiento, p. ej. «Titanium», «Highline».")
    trim_strict: bool = Field(description="true solo si pide exclusivamente esa versión («solo Highline»).")
    year_min: int | None = Field(description="Año modelo mínimo.")
    year_max: int | None = Field(description="Año modelo máximo.")
    price_max: float | None = Field(description="Precio máximo, en unidades de `currency` (sin abreviar).")
    price_target: float | None = Field(description="Precio ideal si lo distingue del máximo.")
    currency: Currency | None = Field(description="Moneda de los precios.")
    km_max: int | None = Field(description="Kilometraje máximo, en km.")
    km_target: int | None = Field(description="Kilometraje ideal si lo distingue del máximo.")
    transmission: Transmission | None
    fuel: Fuel | None
    seller_type: SellerType | None = Field(description="private = particular / dueño directo; dealer = agencia.")
    location: str | None = Field(description="Zona o ciudad tal como la dice el usuario, p. ej. «zona norte».")
    radius_km: int | None = Field(description="Radio en km alrededor de la zona, si lo dice.")


class SearchDrafts(_Strict):
    vehicles: list[SearchDraft] = Field(
        max_length=MAX_VEHICLES,
        description="Un elemento por cada vehículo distinto que busca. Vacío si el texto no pide ningún auto.",
    )


class ListingFacts(_Strict):
    """Facts a listing's text states that the structured fields miss (optional, sección 8.1)."""

    transmission: Transmission | None
    fuel: Fuel | None
    single_owner: bool | None = Field(description="true si dice «único dueño».")
    service_history: bool | None = Field(description="true si dice que tiene los services al día / en concesionaria.")
    timing_belt_changed: bool | None = Field(description="true si dice que la distribución/correa está hecha.")
    accepts_trade_in: bool | None = Field(description="true si acepta permuta.")
    financing: bool | None = Field(description="true si ofrece financiación o anticipo + cuotas.")
    damage_mentioned: bool | None = Field(description="true si menciona choques, granizo, detalles de chapa.")


class PolishedQuestions(_Strict):
    text: str = Field(description="El mensaje para el vendedor, listo para copiar.")


def json_schema(model: type[BaseModel]) -> dict[str, Any]:
    """The model's JSON Schema, self-contained: `$defs` inlined and titles dropped.

    Structured-output implementations differ in how much of JSON Schema they
    follow; a flat schema without `$ref` is the common denominator.
    """
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def inline(node: Any) -> Any:
        if isinstance(node, dict):
            if "$ref" in node:
                return inline(copy.deepcopy(defs[node["$ref"].rsplit("/", 1)[-1]]))
            out = {}
            for key, value in node.items():
                if key == "title":
                    continue
                if key == "properties":  # property names, not keywords: keep them all
                    out[key] = {name: inline(sub) for name, sub in value.items()}
                else:
                    out[key] = inline(value)
            return out
        if isinstance(node, list):
            return [inline(v) for v in node]
        return node

    return inline(schema)
