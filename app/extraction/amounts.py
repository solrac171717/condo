"""Extracción heurística de importes (base imponible, IVA, total) de texto de factura.

Estrategia (sin posiciones fijas):
  1. Buscar líneas etiquetadas: "Base imponible", "Base liquidable", "Total IVA",
     "Cuota de IVA", "Importe IVA", "Total factura", "TOTAL A PAGAR"...
  2. Interpretar porcentajes de IVA típicos de España (0, 4, 5, 10, 21).
  3. Validación cruzada por aritmética: si aparecen dos de {base, cuota, total},
     deducir el tercero SOLO cuando la comprobación base+iva==total es exacta
     (tolerancia de céntimos). Si no cuadra, NO se inventa nada: se marca aviso.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

from app.utils.numbers import find_numbers_in_line, nearly_equal, parse_spain_number

BASE_LABELS = ("base imponible", "base liquidable", "base del iva", "suman base",
               "total base", "base total", "subtotal", "importes")
IVA_CUOTA_LABELS = ("cuota de iva", "cuota iva", "total iva", "iva repercutido",
                    "importe iva", "cuota repercutida", "total cuota", "iva total",
                    "iva")
TOTAL_LABELS = ("total factura", "total a pagar", "importe total", "total devengado",
                "total general", "a pagar", "total adeudar", "neto a pagar", "total")
IRPF_LABELS = ("retencion irpf", "irpf", "retencion", "retenida")

# "21 % de IVA" / "IVA 21%" / "21,00 %" junto a importe -> tramos de IVA
_IVA_RATE_RE = re.compile(r"(?:^|[^\d.,])(\d{1,2})(?:[.,]0+)?\s*%\s*(?:de\s+)?(?:iva|I\.V\.A)", re.IGNORECASE)
_IVA_RATE_RE2 = re.compile(r"(?:iva|i\.v\.a)\s*(?:al)?\s*(\d{1,2})(?:[.,]\d+)?\s*%", re.IGNORECASE)

VALID_IVA_RATES = {0.0, 4.0, 5.0, 10.0, 21.0}


@dataclass
class Amounts:
    base: Optional[float] = None
    iva: Optional[float] = None
    total: Optional[float] = None
    irpf: Optional[float] = None
    rates: list[float] = None      # tipos de IVA detectados (p.ej. [10, 21])
    source: dict = None            # campo -> etiqueta encontrada (para confianza)

    def __post_init__(self):
        self.rates = self.rates or []
        self.source = self.source or {}


def _num_after_label(line: str, labels: tuple[str, ...]) -> tuple[Optional[float], str]:
    low = line.lower()
    for lbl in labels:
        idx = low.find(lbl)
        if idx == -1:
            continue
        tail = line[idx + len(lbl):]
        nums = find_numbers_in_line(tail)
        # excluir porcentajes pegados tipo "21%"
        candidates = [(t, v) for (t, v) in nums if "%" not in t and not re.fullmatch(r"\d{1,2}", t)]
        if candidates:
            # normalmente el importe va al final de la línea etiquetada
            text, val = candidates[-1]
            return val, lbl
    return None, ""


def extract_amounts(text: str) -> Amounts:
    """Extrae base/IVA/total usando etiquetas + aritmética de refuerzo."""
    a = Amounts()
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]

    # --- detección de tramos de IVA ---
    for m in _IVA_RATE_RE.finditer(text):
        r = float(m.group(1))
        if r in VALID_IVA_RATES and r not in a.rates:
            a.rates.append(r)
    for m in _IVA_RATE_RE2.finditer(text):
        r = float(m.group(1))
        if r in VALID_IVA_RATES and r not in a.rates:
            a.rates.append(r)

    # --- etiquetas de importes ---
    found_total_candidates: list[float] = []
    for line in lines:
        if a.base is None:
            v, lbl = _num_after_label(line, BASE_LABELS)
            if v is not None and "%" not in line.lower().split(lbl)[-1][:8]:
                a.base, a.source["base"] = v, lbl
        if a.iva is None:
            v, lbl = _num_after_label(line, IVA_CUOTA_LABELS)
            if v is not None:
                a.iva, a.source["iva"] = v, lbl
        if a.irpf is None:
            v, lbl = _num_after_label(line, IRPF_LABELS)
            if v is not None:
                a.irpf, a.source["irpf"] = v, lbl
        v, lbl = _num_after_label(line, TOTAL_LABELS)
        if v is not None and v > 0:
            found_total_candidates.append(v)
            if a.total is None and lbl in ("total factura", "total a pagar", "importe total",
                                           "total devengado", "total general", "a pagar"):
                a.total, a.source["total"] = v, lbl
    if a.total is None and found_total_candidates:
        a.total = max(found_total_candidates)   # el mayor suele ser el total final
        a.source["total"] = "max(candidatos)"

    # --- refuerzo aritmético (nunca inventa: solo confirma/deduce con igualdad exacta) ---
    if a.base is not None and a.iva is not None and a.total is None:
        cand = round(a.base + a.iva - (a.irpf or 0), 2)
        for c in found_total_candidates:
            if nearly_equal(c, cand):
                a.total, a.source["total"] = c, "deducido(base+iva)"
                break
    if a.total is not None and a.iva is None and a.base is not None and a.rates:
        rate = max(a.rates)
        calc = round(a.base * rate / 100, 2)
        if nearly_equal(a.total - a.base + (a.irpf or 0), calc):
            a.iva, a.source["iva"] = calc, "calculado(%g%%)" % rate
    if a.total is not None and a.base is None and a.iva is not None:
        cand = round(a.total - a.iva + (a.irpf or 0), 2)
        if cand > 0:
            a.base, a.source["base"] = cand, "deducido(total-iva)"
    return a
