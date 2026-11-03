"""Planilla compartida del monitor de stock (Prueba A). Uso: python monitor_xlsx.py salida.xlsx ["Agencia"]"""
import sys
from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.worksheet.datavalidation import DataValidation

out = sys.argv[1]
agency = sys.argv[2] if len(sys.argv) > 2 else "tu agencia"
HEAD = PatternFill("solid", fgColor="1F5F8B")
WHITE = Font(bold=True, color="FFFFFF")
wb = Workbook()

info = wb.active
info.title = "Cómo funciona"
lines = [
    (f"Monitor de stock · {agency}", True),
    ("Prueba gratuita de 2 semanas de Ese Auto.", False),
    ("", False),
    ("1. En la hoja «Mi stock» cargá los autos que tenés a la venta: una fila por auto.", False),
    ("2. Si vendés uno, marcalo como «Vendido» en la columna Estado. Si sumás uno, agregá una fila.", False),
    ("3. Dos veces por semana (martes y viernes) completamos la hoja «Comparación».", False),
    ("", False),
    ("Qué te decimos de cada auto:", True),
    ("• Cuántos avisos parecidos hay hoy en tu zona (misma marca y modelo, año ±1, km ±25 %).", False),
    ("• El precio mediano de esos avisos y si el tuyo está por encima, en línea o entre los más baratos.", False),
    ("• Si en los últimos días apareció uno parecido más barato que el tuyo, con el link al aviso.", False),
    ("", False),
    ("Son precios publicados en portales, no precios de venta. Con menos de 5 avisos parecidos no damos lectura.", False),
    ("Solo usamos esta planilla para hacerte la comparación. No la compartimos con nadie.", False),
]
for i, (t, b) in enumerate(lines, 1):
    info.cell(row=i, column=1, value=t).font = Font(bold=b, size=13 if i == 1 else 11)
info.column_dimensions["A"].width = 110

st = wb.create_sheet("Mi stock")
cols = ["#", "Marca", "Modelo", "Versión", "Año", "Km", "Precio", "Moneda", "Link del aviso (opcional)", "Estado", "Actualizado el"]
widths = [5, 14, 16, 22, 8, 10, 12, 9, 40, 12, 14]
for j, (c, w) in enumerate(zip(cols, widths), 1):
    cell = st.cell(row=1, column=j, value=c)
    cell.fill, cell.font = HEAD, WHITE
    st.column_dimensions[cell.column_letter].width = w
for i in range(2, 62):
    st.cell(row=i, column=1, value=i - 1)
dv_m = DataValidation(type="list", formula1='"USD,ARS"', allow_blank=True)
dv_e = DataValidation(type="list", formula1='"A la venta,Vendido,Reservado"', allow_blank=True)
st.add_data_validation(dv_m); st.add_data_validation(dv_e)
dv_m.add("H2:H61"); dv_e.add("J2:J61")
st.freeze_panes = "A2"

cmp_ = wb.create_sheet("Comparación")
cols = ["Fecha", "# en Mi stock", "Auto", "Tu precio (US$)", "Avisos parecidos", "Precio mediano (US$)",
        "Diferencia vs. mediana", "Lectura", "Apareció uno más barato", "Link", "Comentario"]
widths = [11, 10, 30, 13, 11, 15, 13, 24, 30, 40, 40]
for j, (c, w) in enumerate(zip(cols, widths), 1):
    cell = cmp_.cell(row=1, column=j, value=c)
    cell.fill, cell.font = HEAD, WHITE
    cell.alignment = Alignment(wrap_text=True, vertical="center")
    cmp_.column_dimensions[cell.column_letter].width = w
cmp_.freeze_panes = "A2"
wb.save(out)
print(out)
