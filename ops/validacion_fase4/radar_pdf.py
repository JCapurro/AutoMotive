"""Radar semanal en PDF de 1 página (Prueba A, Validación comercial Fase 4).

Uso: python radar_pdf.py <datos.json> <zona> <semana YYYY-MM-DD> <salida.pdf> ["Nombre de la agencia"]
<datos.json> = salida de radar.sql (lista de {zone, rows}).
"""
import json
import sys
from datetime import date, timedelta

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ZONES = {"amba": "AMBA", "cordoba": "Córdoba", "litoral": "Litoral (Rosario, Santa Fe y Entre Ríos)"}
FIX = {"Ecosport": "EcoSport", "Gol Trend": "Gol Trend", "Hilux": "Hilux"}
INK, MUTED, LINE, ACCENT, SOFT = (colors.HexColor(c) for c in ("#1d1d1b", "#6b6b66", "#d9d7d0", "#1f5f8b", "#eef4f8"))


def nice(make: str, model: str) -> str:
    name = f"{make.title()} {model.title()}"
    for a, b in FIX.items():
        name = name.replace(a, b)
    return name


def usd(v) -> str:
    return "—" if v is None else "US$ " + f"{int(round(v)):,}".replace(",", ".")


def dept(r) -> str:
    d, med = r.get("cheapest_dept"), r.get("cheapest_dept_med")
    # Solo si de verdad está por debajo de la mediana de la zona (3 % o más).
    if not d or med is None or r["median_usd"] is None or med > r["median_usd"] * 0.97:
        return "—"
    if d.startswith("Comuna"):
        d = "CABA" if d == "Comuna 1" else f"CABA ({d})"
    return f"{d}: {usd(med)} ({r['cheapest_dept_n']} avisos)"


def build(rows, zone: str, week: str, out: str, agency: str | None) -> None:
    wk = date.fromisoformat(week)
    styles = {
        "h": ParagraphStyle("h", fontName="Helvetica-Bold", fontSize=16, textColor=INK, leading=19),
        "s": ParagraphStyle("s", fontName="Helvetica", fontSize=9.5, textColor=MUTED, leading=12),
        "c": ParagraphStyle("c", fontName="Helvetica", fontSize=8.5, textColor=INK, leading=10.5),
        "ch": ParagraphStyle("ch", fontName="Helvetica-Bold", fontSize=8, textColor=colors.white, leading=10),
        "n": ParagraphStyle("n", fontName="Helvetica", fontSize=7.5, textColor=MUTED, leading=9.5),
    }
    doc = SimpleDocTemplate(out, pagesize=landscape(A4), leftMargin=14 * mm, rightMargin=14 * mm,
                            topMargin=12 * mm, bottomMargin=10 * mm, title=f"Radar semanal {ZONES[zone]}")
    head = f"Radar semanal · {ZONES[zone]}"
    sub = (f"Semana del {wk:%d/%m} al {wk + timedelta(days=6):%d/%m/%Y}"
           + (f" · preparado para {agency}" if agency else "")
           + " · los 10 modelos que más dejaron de publicarse y dónde están más baratos")
    hdr = ["#", "Modelo", "Años", "Publicados", "Nuevos en la semana", "Dejaron de publicarse",
           "Días publicados (mediana)", "Precio mediano", "El 25 % más barato, hasta", "Dónde está más barato"]
    data = [[Paragraph(h, styles["ch"]) for h in hdr]]
    for r in rows:
        days = "—" if r.get("median_days") is None else f"{r['median_days']:.0f}".replace(".", ",")
        gone = str(r["gone"]) if r["has_days"] else f"{r['gone']} *"
        data.append([Paragraph(str(x), styles["c"]) for x in (
            r["rk"], nice(r["make"], r["model"]), f"{r['year_from']}–{r['year_from'] + 1}", r["active"], r["new"],
            gone, days, usd(r["median_usd"]), usd(r["p25_usd"]), dept(r))])
    widths = [8, 38, 20, 20, 22, 26, 24, 26, 28, 57]
    t = Table(data, colWidths=[w * mm for w in widths], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), ACCENT),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, SOFT]),
        ("LINEBELOW", (0, 1), (-1, -1), 0.4, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 4), ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
    ]))
    notes = [
        "Cómo leerlo. «Dejaron de publicarse»: avisos que en la semana ya no aparecían en los portales que revisamos completos. "
        "No sabemos si se vendieron: es una señal de qué se mueve, no una cifra de ventas. "
        "«Días publicados»: cuánto estuvieron publicados esos avisos hasta que dejaron de verse (mediana; «—» si hay menos de 5 casos).",
        "Precios: avisos activos publicados en dólares o convertidos a dólares, sin anticipos ni cuotas. «Dónde está más barato» compara "
        "la mediana de cada partido o departamento con al menos 3 avisos contra la de toda la zona; «—» si ninguno está claramente por debajo.",
        "* Menos de 3 casos de días en la semana: el modelo entra por cantidad de avisos publicados. "
        "Fuente: Ese Auto, con avisos públicos de portales de clasificados. Son precios publicados, no precios de venta.",
    ]
    story = [Paragraph(head, styles["h"]), Paragraph(sub, styles["s"]), Spacer(1, 5 * mm), t, Spacer(1, 4 * mm)]
    story += [Paragraph(n, styles["n"]) for n in notes]
    doc.build(story)


if __name__ == "__main__":
    src, zone, week, out = sys.argv[1:5]
    agency = sys.argv[5] if len(sys.argv) > 5 else None
    blob = {z["zone"]: z["rows"] for z in json.load(open(src, encoding="utf-8"))}
    build(blob[zone], zone, week, out, agency)
    print(out)
