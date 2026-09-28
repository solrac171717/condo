"""Generación del archivo Excel profesional con openpyxl.

Columnas: Archivo | NIF/CIF | Proveedor | Número factura | Fecha |
Base imponible | IVA | Total | Tipo IVA | IRPF | Origen texto |
Confianza | Estado | Advertencias
Formato: cabeceras fijas con filtros, congelación de fila 1, moneda € y
resaltado de filas REVISAR/ERROR.
"""
from __future__ import annotations

from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter
from openpyxl.worksheet.table import Table, TableStyleInfo

from app.models.invoice import InvoiceData, ProcessingStatus

DEFAULT_EXCEL_NAME = "facturas_procesadas.xlsx"

HEADERS = [
    ("Archivo", 28), ("NIF/CIF", 14), ("Proveedor", 32), ("Número factura", 15),
    ("Fecha", 12), ("Base imponible", 15), ("IVA", 12), ("Total", 14),
    ("Tipo IVA", 10), ("IRPF", 10), ("Origen texto", 12), ("Confianza", 10),
    ("Estado", 10), ("Advertencias", 60),
]
MONEY_COLS = {6, 7, 8, 10}          # Base, IVA, Total, IRPF
MONEY_FMT = '#,##0.00\\ "€"'

_HEADER_FILL = PatternFill("solid", fgColor="1F4E79")
_HEADER_FONT = Font(color="FFFFFF", bold=True)
_REVIEW_FILL = PatternFill("solid", fgColor="FFF2CC")     # ámbar suave
_ERROR_FILL = PatternFill("solid", fgColor="F8CBAD")      # rojo suave
_THIN = Side(style="thin", color="BFBFBF")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)


class ExcelExporter:
    def export(self, invoices: list[InvoiceData], out_path: str | Path) -> Path:
        out = Path(out_path)
        wb = Workbook()
        ws = wb.active
        ws.title = "Facturas"

        # Cabeceras
        for col, (title, width) in enumerate(HEADERS, start=1):
            c = ws.cell(row=1, column=col, value=title)
            c.fill = _HEADER_FILL
            c.font = _HEADER_FONT
            c.alignment = Alignment(horizontal="center", vertical="center")
            c.border = _BORDER
            ws.column_dimensions[get_column_letter(col)].width = width

        # Filas
        for r, inv in enumerate(invoices, start=2):
            row = inv.to_row()
            for col, (title, _) in enumerate(HEADERS, start=1):
                val = row.get(title, "")
                cell = ws.cell(row=r, column=col, value=val)
                cell.border = _BORDER
                if col in MONEY_COLS and isinstance(val, (int, float)):
                    cell.number_format = MONEY_FMT
                elif title == "Confianza" and isinstance(val, (int, float)):
                    cell.number_format = "0%"
                if title == "Estado":
                    cell.alignment = Alignment(horizontal="center")
                    if inv.estado == ProcessingStatus.REVIEW:
                        cell.fill = _REVIEW_FILL
                    elif inv.estado == ProcessingStatus.ERROR:
                        cell.fill = _ERROR_FILL
            ws.cell(row=r, column=len(HEADERS)).alignment = Alignment(wrap_text=False)

        n = len(invoices) + 1
        if n >= 2:
            ref = f"A1:{get_column_letter(len(HEADERS))}{n}"
            table = Table(displayName="Facturas", ref=ref)
            table.tableStyleInfo = TableStyleInfo(
                name="TableStyleMedium2", showRowStripes=True)
            ws.add_table(table)
        else:
            ws.auto_filter.ref = f"A1:{get_column_letter(len(HEADERS))}{max(n,1)}"

        ws.freeze_panes = "A2"          # congelar cabecera
        ws.sheet_view.zoomScale = 100

        out.parent.mkdir(parents=True, exist_ok=True)
        wb.save(str(out))
        return out
