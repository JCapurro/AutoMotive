"""Agencias, fase 1: a stock list read by the LLM, as the spreadsheet table the
panel already knows how to preview (web/lib/dealer-sheet.ts SheetTable).

The model's rows become a table with fixed Spanish headers, so the web's
guessColumns() maps them and the same editable preview, catalog check and
«Cargar N autos» run as for a CSV. Pure. Cleaned on the way: out-of-range
years and prices go blank (the preview then asks for them), text is trimmed,
and anything that looks like an Argentine plate is dropped from every text
field (the prompt already forbids them; this is the second lock).
"""
from __future__ import annotations

import re
from typing import Any

from llm.schemas import STOCK_SHEET_MAX_ROWS, StockSheetRead

HEADERS = ["Marca", "Modelo", "Versión", "Año", "Km", "Precio", "Moneda", "Color"]
# AAA 123 (until 2016) and AA 123 BB (Mercosur), with or without spaces or dashes.
_PLATE = re.compile(r"\b(?:[A-Z]{3}[\s-]?\d{3}|[A-Z]{2}[\s-]?\d{3}[\s-]?[A-Z]{2})\b", re.I)
# In a trim «THP 165» or «HDi 110» is the engine: there only the forms no trim
# has (AAA123 and AA123BB written together; «GL 150 CV» stays).
_PLATE_IN_TRIM = re.compile(r"\b(?:[A-Z]{3}\d{3}|[A-Z]{2}\d{3}[A-Z]{2})\b", re.I)


def _text(value: Any, limit: int, plate: re.Pattern[str] = _PLATE) -> str:
    if not isinstance(value, str):
        return ""
    clean = plate.sub("", value)
    return " ".join(clean.split())[:limit]


def _whole(value: Any, lo: int, hi: int) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return ""
    n = int(round(value))
    return str(n) if lo <= n <= hi else ""


def to_table(answer: StockSheetRead, *, max_year: int) -> dict[str, Any]:
    """{"readable", "headers", "rows", "rows_read", "truncated"}; rows with
    neither make nor model nor price are left out."""
    rows: list[list[str]] = []
    for r in answer.rows:
        price = ""
        if isinstance(r.price, (int, float)) and not isinstance(r.price, bool) and 0 < r.price < 1e12:
            price = str(int(round(r.price))) if float(r.price).is_integer() or r.price >= 1000 else str(r.price)
        row = [_text(r.make, 60), _text(r.model, 60), _text(r.trim, 80, _PLATE_IN_TRIM), _whole(r.year, 1950, max_year),
               _whole(r.mileage_km, 0, 2_000_000), price, r.currency or "", _text(r.color, 40)]
        if not (row[0] or row[1] or row[5]):
            continue
        rows.append(row)
    return {
        "readable": bool(answer.readable and rows),
        "headers": list(HEADERS),
        "rows": rows[:STOCK_SHEET_MAX_ROWS],
        "rows_read": len(rows),
        "truncated": len(rows) > STOCK_SHEET_MAX_ROWS,
    }
