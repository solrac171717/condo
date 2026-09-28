"""Extractor principal: convierte el texto de una factura en `InvoiceData`.

Combina los módulos especializados (nif, supplier, amounts) y añade
extracción ligera de número de factura y fecha. Aquí NO se valida:
la validación matemática y de coherencia vive en app/validation.
"""
from __future__ import annotations

import re
from datetime import date
from typing import Optional

from app.extraction.amounts import extract_amounts
from app.extraction.nif import find_nifs
from app.extraction.supplier import extract_supplier
from app.models.invoice import FieldValue, InvoiceData

_NUM_FACTURA_RE = re.compile(
    r"\b(?:n[ºo\.]?\s*(?:de\s*)?(?:factura|documento)|factura\s*(?:n[ºo\.]|number|#)?|"
    r"invoice\s*(?:no\.?|n[ºo]|#)?|num\.?\s*factura)\s*[:#]?\s*"
    r"([A-Z]{0,4}[\-/]?\d[\w\-/]{2,19})",
    re.IGNORECASE,
)
_NUM_FACTURA_SIMPLE_RE = re.compile(r"\b(F[A-Z]{0,3}[\-]?\d{3,12}|\d{2,4}[\-/]\d{3,8})\b")

_DATE_ES_RE = re.compile(
    r"\b(?:fecha\s*(?:de\s*)?(?:emisi[oó]n|factura)?\s*[:#]?\s*)?"
    r"(\d{1,2}[/\-.]\d{1,2}[/\-.](?:20\d{2}|\d{2}))\b", re.IGNORECASE)
_DATE_ISO_RE = re.compile(r"\b((?:20\d{2})-\d{2}-\d{2})\b")


def _parse_date(raw: str) -> Optional[str]:
    """Devuelve la fecha normalizada ISO (YYYY-MM-DD) o None si es inválida."""
    raw = raw.strip().replace(" ", "")
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y", "%d/%m/%y", "%d-%m-%y", "%Y-%m-%d"):
        try:
            from datetime import datetime
            d = datetime.strptime(raw, fmt).date()
            if 1990 <= d.year <= 2100:
                return d.isoformat()
        except ValueError:
            continue
    return None


class InvoiceExtractor:
    """Extrae los campos de una factura a partir del texto completo."""

    def extract(self, text: str, filename: str) -> InvoiceData:
        inv = InvoiceData(archivo=filename)
        lines = [ln for ln in text.splitlines() if ln.strip()]

        # ---------------- NIF/CIF ----------------
        nifs = find_nifs(text)
        ambiguous_nif = False
        if nifs:
            best_nif, conf = nifs[0]
            inv.nif = FieldValue(best_nif, conf)
            if len(nifs) > 1:
                second_conf = nifs[1][1]
                if conf - second_conf < 0.25 and second_conf >= 0.4:
                    # dos identificadores con confianza parecida: no podemos
                    # asegurar cuál es el del proveedor -> exigir revisión
                    ambiguous_nif = True
                    inv.nif_ambiguo = True
                    inv.add_warning(
                        f"Se detectaron {len(nifs)} identificadores fiscales "
                        f"({best_nif} y {nifs[1][0]}) con confianza similar; "
                        "no se puede determinar con seguridad cuál es el del "
                        "proveedor")
                else:
                    inv.add_warning(
                        f"Se detectaron {len(nifs)} identificadores fiscales; "
                        "se usó el de mayor confianza (proveedor vs cliente)")

        # posición de la línea con el NIF del emisor como pista para el proveedor
        nif_line_pos: Optional[int] = None
        if nifs:
            pat = re.compile(re.escape(nifs[0][0]), re.IGNORECASE)
            for i, ln in enumerate(lines):
                if pat.search(ln.replace(" ", "")) or pat.search(ln):
                    nif_line_pos = i
                    break

        # ---------------- Proveedor ----------------
        sup, sup_conf = extract_supplier(lines, nif_line_pos)
        if sup:
            inv.proveedor = FieldValue(sup, sup_conf)

        # ---------------- Importes ----------------
        amounts = extract_amounts(text)
        src_conf = {"label": 0.9, "deducido": 0.75, "calculado": 0.65, "max": 0.55}

        def conf_for(field_src: str, base_conf: float) -> float:
            if not field_src:
                return base_conf
            for k, c in src_conf.items():
                if field_src.startswith(k):
                    return c
            return base_conf

        if amounts.base is not None:
            inv.base_imponible = FieldValue(amounts.base, conf_for(amounts.source.get("base", ""), 0.9))
        if amounts.iva is not None:
            inv.iva = FieldValue(amounts.iva, conf_for(amounts.source.get("iva", ""), 0.9))
        if amounts.total is not None:
            inv.total = FieldValue(amounts.total, conf_for(amounts.source.get("total", ""), 0.9))
        if amounts.irpf is not None:
            inv.retencion_irpf = FieldValue(amounts.irpf, 0.8)
        if amounts.rates:
            inv.tipo_iva = FieldValue(" + ".join(f"{r:g}%" for r in sorted(amounts.rates)), 0.85)

        # ---------------- Número de factura ----------------
        m = _NUM_FACTURA_RE.search(text)
        if m:
            inv.numero_factura = FieldValue(m.group(1).strip("-/ "), 0.85)
        else:
            m2 = _NUM_FACTURA_SIMPLE_RE.search(text)
            if m2:
                inv.numero_factura = FieldValue(m2.group(1), 0.5)

        # ---------------- Fecha ----------------
        for regex in (_DATE_ES_RE, _DATE_ISO_RE):
            md = regex.search(text)
            if md:
                iso = _parse_date(md.group(1))
                if iso:
                    inv.fecha = FieldValue(iso, 0.8)
                    break

        inv.compute_avg_confidence()
        return inv
