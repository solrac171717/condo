#!/usr/bin/env python3
"""Genera facturas PDF sintéticas de prueba (con texto embebido y escaneadas).

Uso:
    python scripts/generate_sample_invoices.py [directorio_destino]

Crea en `sample_invoices/` un conjunto de facturas con formatos españoles
diversos (distintos diseños, tramos de IVA, IRPF, importes incorrectos para
probar revisión, y una factura "escaneada" sin texto para probar OCR).
Los NIF/CIF usan checksums válidos generados con el algoritmo de la AEAT.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pymupdf

CONTROL_CIF = "JABCDEFGHI"


# ----------------------------------------------------------------------
def _cif_control_char(digits7: str) -> str:
    total = 0
    for i, d in enumerate(digits7):
        d = int(d)
        if i % 2 == 0:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    c = (10 - total % 10) % 10
    return CONTROL_CIF[c]


def make_cif(prefix: str, digits7: str) -> str:
    """Genera un CIF con el dígito de control CORRECTO según la AEAT.

    Para A/B/G (y J) el control es siempre letra; para el resto puede ser
    dígito. Usamos siempre la letra calculada para que validate_nif() acepte.
    """
    return f"{prefix}{digits7}{_cif_control_char(digits7)}"


def fmt(v: float) -> str:
    """1234.5 -> '1.234,50'"""
    s = f"{v:,.2f}"
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def _text_page(doc_lines: list[tuple[float, str]], font_size: float = 11):
    """Añade una página con líneas de texto simple."""
    page = doc.new_page(width=595, height=842)  # A4 pt
    y = 60.0
    for _, line in doc_lines:
        size = font_size
        bold = line.isupper() and len(line) < 60
        page.insert_text((50, y), line, fontsize=size,
                         fontname="hebo" if bold else "helv")
        y += size + 8
    return page


def build_pdf(path: Path, lines: list[str]) -> None:
    global doc
    doc = pymupdf.open()
    page = doc.new_page(width=595, height=842)
    y = 55.0
    for ln in lines:
        if ln == "":
            y += 10
            continue
        if ln.startswith("~~"):   # salto extra
            y += 14
            ln = ln[2:]
        bold = ln.strip().isupper() and 0 < len(ln.strip()) < 55
        fs = 13 if bold else 10.5
        page.insert_text((45, y), ln, fontsize=fs, fontname="hebo" if bold else "helv")
        y += fs + 7
    doc.save(str(path))
    doc.close()


# ----------------------------------------------------------------------
# Diseños distintos de factura, todos con números válidos y CIF válido
CIF_A = make_cif("A", "1234567")     # EMPRESA EJEMPLO S.L.
CIF_B = make_cif("B", "9876543")     # COMERCIAL ANDALUZ SA
CIF_C = make_cif("B", "6655443")     # SERVICIOS TECNICOS SLU
CIF_D = make_cif("A", "1122334")     # TRANSPENTES IBIZA SC
CLIENT_NIF = "12345678Z"             # cliente persona física (checksum correcto)


def invoice_classic(pn: str, fecha: str, base: float, rate: float,
                    nif=CIF_A, nombre="EMPRESA EJEMPLO S.L.") -> list[str]:
    cuota = round(base * rate / 100, 2)
    total = round(base + cuota, 2)
    return [
        "FACTURA", "",
        nombre, "C/ Mayor 15, 28013 Madrid", f"CIF: {nif}", "",
        "Cliente: Cliente Sugerido SL", f"NIF: {CLIENT_NIF}", "",
        f"Factura Nº: {pn}", f"Fecha: {fecha}", "",
        "Descripción                 Importe",
        "Servicios profesionales",
        "",
        f"Base imponible ......... {fmt(base)} €",
        f"IVA ({rate:g}%) ............ {fmt(cuota)} €",
        f"TOTAL FACTURA .......... {fmt(total)} €", "",
        "Forma de pago: Transferencia bancaria",
    ]


def invoice_modern(pn: str, fecha: str, items: list[tuple[float, float]],
                   nif=CIF_B, nombre="Comercial Andaluz S.A.",
                   irpf_rate: float | None = None) -> list[str]:
    """Diseño distinto: tabla de líneas con varios tipos de IVA."""
    lines = [nombre, f"CIF {nif}", "Avda. de la Constitución 40 - Sevilla", "",
             "FACTURA SIMPLIFICADA", f"Nº {pn} — {fecha}", "Facturar a: Grupo Delta SL", "",
             "Concepto            Base      IVA   Cuota"]
    bases: dict[float, float] = {}
    for importe, rate in items:
        bases[rate] = round(bases.get(rate, 0) + importe, 2)
    cuota_total = 0.0
    for rate, b in sorted(bases.items()):
        cuota = round(b * rate / 100, 2)
        cuota_total += cuota
        lines.append(f"Tipo {rate:g}%          {fmt(b)}   {fmt(round(b*rate/100,2))}")
    base_total = round(sum(bases.values()), 2)
    total = round(base_total + cuota_total, 2)
    if irpf_rate:
        irpf = round(base_total * irpf_rate / 100, 2)
        total = round(total - irpf, 2)
        lines += ["", f"Retención IRPF ({irpf_rate:g}%) ... {fmt(irpf)} €"]
    lines += ["", f"Suman Base Imponible: {fmt(base_total)} €",
              f"Total Cuota Repercutida: {fmt(cuota_total)} €",
              f"IMPORTE TOTAL: {fmt(total)} €"]
    return lines


def main(out_dir: Path) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)

    # 1-2: clásicas 21% y 10%
    build_pdf(out_dir / "factura_001.pdf", invoice_classic("F2026-0001", "05/01/2026", 1000.00, 21))
    build_pdf(out_dir / "factura_002.pdf", invoice_classic("F2026-0002", "12/01/2026", 2500.50, 10,
                                                           nif=CIF_C, nombre="SERVICIOS TECNICOS SLU"))
    # 3: multi-IVA + IRPF, diseño distinto
    build_pdf(out_dir / "factura_003.pdf", invoice_modern(
        "2026/033", "20/01/2026", [(1000.00, 21), (500.00, 10), (200.00, 4)], irpf_rate=15))
    # 4: importes que NO cuadran (debe quedar REVISAR por diferencia)
    bad = invoice_classic("F2026-0004", "25/01/2026", 1000.00, 21)
    bad[-1] = ""
    bad = [ln.replace(fmt(1210.00), fmt(1215.00)) for ln in bad]  # total falseado
    build_pdf(out_dir / "factura_004.pdf", bad)
    # 5: sin NIF visible (debe quedar REVISAR: NIF no detectado)
    no_nif = [ln for ln in invoice_classic("F2026-0005", "30/01/2026", 300.00, 21)
              if not ln.startswith("CIF:")]
    build_pdf(out_dir / "factura_005.pdf", no_nif)
    # 6: archivo corrupto deliberadamente (debe ser ERROR sin romper el lote)
    (out_dir / "factura_corrupta.pdf").write_bytes(b"%PDF-1.7 esto no es un pdf valido \x00\x01")

    print(f"Facturas de ejemplo generadas en: {out_dir}")
    for f in sorted(out_dir.glob("*.pdf")):
        print("  -", f.name)


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parent.parent / "sample_invoices"
    main(target)
