"""System prompts and user messages of the LLM layer, shared by every provider.

The system prompts are Markdown files next to this module. What the user
wrote always goes inside tags in the user message, never into the system
prompt, and the prompts tell the model it is data.
"""
from __future__ import annotations

import datetime as dt
import json
from collections.abc import Sequence
from functools import cache
from pathlib import Path

from normalization.vehicle import CatalogModel

_DIR = Path(__file__).resolve().parent


@cache
def load(name: str) -> str:
    return (_DIR / f"{name}.md").read_text(encoding="utf-8")


def catalog_text(catalog: Sequence[CatalogModel]) -> str:
    """One line per make: "Ford: Fiesta [S, SE, Titanium]; Focus [...]"."""
    by_make: dict[str, list[str]] = {}
    for m in sorted(catalog, key=lambda m: (m.make, m.model)):
        by_make.setdefault(m.make, []).append(f"{m.model} [{', '.join(m.trims)}]" if m.trims else m.model)
    return "\n".join(f"{make}: {'; '.join(models)}" for make, models in by_make.items()) or "(vacío)"


def parse_search_system(catalog: Sequence[CatalogModel], today: dt.date | None = None) -> str:
    year = (today or dt.date.today()).year
    return (load("parse_search")
            .replace("{year}", str(year))
            .replace("{catalog}", catalog_text(catalog)))


def parse_search_user(text: str) -> str:
    return f"<pedido>\n{text.strip()}\n</pedido>"


def listing_facts_user(title: str, description: str) -> str:
    return f"<publicacion>\n{title.strip()}\n\n{description.strip()}\n</publicacion>"


def polish_questions_user(questions: list[str], context: dict) -> str:
    lines = "\n".join(f"- {q}" for q in questions)
    return (f"<preguntas>\n{lines}\n</preguntas>\n"
            f"<contexto>\n{json.dumps(context, ensure_ascii=False)}\n</contexto>")
