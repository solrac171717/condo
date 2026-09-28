"""Detección heurística del nombre del proveedor (quien emite la factura).

Heurísticas combinadas (no dependemos de una posición fija):
  * Líneas cercanas a "NIF/CIF:" suelen preceder o seguir al nombre fiscal.
  * Palabras societarias españolas: S.L., S.A., S.L.U., S.A.U., S.C., C.B., SL...
  * Descartamos líneas que contengan datos del cliente ("Cliente", "Facturar a"),
    direcciones postales, teléfonos, IBANs o cabeceras obvias de documento.
"""
from __future__ import annotations

import re

LEGAL_FORMS = re.compile(
    r"\b(?:S\.?\s?L\.?\s?U?\.?|S\.?\s?A\.?\s?U?\.?|S\.?C\.?|C\.?B\.?|"
    r"S\.?A\.?D\.?|COOPERATIVA|COMUNIDAD\s+DE\s+BIENES|"
    r"SOCIEDAD\s+LIMITADA|SOCIEDAD\s+ANONIMA)\b",
    re.IGNORECASE,
)
CLIENT_HINTS = re.compile(
    r"\b(cliente|facturar\s+a|emitida\s+para|senor(es)?\b|a\s+atenci[oó]n|"
    r"destinatario|comprador|adquirente)\b", re.IGNORECASE)
NOISE = re.compile(
    r"\b(www\.|@|telf|tel\.|tfno|fax|iban|es\d{4}|cp\b|\bc.p|calle|avenida|"
    r"avda|p\.?l\.?a|pol[ií]gono|nave|carretera|camino|ronda|pasaje|edificio|"
    r"c[oó]digo|postal|provincia|pol[ií]|CIF$|NIF$|VAT$)", re.IGNORECASE)
DATE_MONEY = re.compile(r"\d{1,2}[/.-]\d{1,2}[/.-]\d{2,4}|[€]|\bEUR\b", re.IGNORECASE)


def _clean(line: str) -> str:
    s = re.sub(r"^(NIF|CIF|N\.I\.F|C\.I\.F|VAT)[:\s]*([A-Z]\d{7}\w|\d{8}\w)\s*-?\s*",
               "", line.strip(), flags=re.IGNORECASE)
    s = re.sub(r"\s{2,}", " ", s).strip(" .,-–—:;")
    return s


def extract_supplier(lines: list[str], nif_pos_hint: int | None = None) -> tuple[str | None, float]:
    """Devuelve (nombre_proveedor, confianza 0..1). None si no hay candidato fiable."""
    candidates: list[tuple[str, float]] = []
    for i, raw in enumerate(lines):
        line = _clean(raw)
        if not (3 <= len(line) <= 60):
            continue
        if CLIENT_HINTS.search(line) or NOISE.search(line) or DATE_MONEY.search(line):
            continue
        if not re.search(r"[A-Za-zÁÉÍÓÚÑáéíóúñ]", line):
            continue
        score = 0.0
        has_legal = bool(LEGAL_FORMS.search(line))
        letters = sum(c.isalpha() for c in line)
        words = len(line.split())
        if has_legal:
            score += 0.55
        if 2 <= words <= 6:
            score += 0.15
        if letters / max(len(line), 1) > 0.6:
            score += 0.1
        if nif_pos_hint is not None and abs(i - nif_pos_hint) <= 3:
            score += 0.2
        elif nif_pos_hint is None and i <= 12:      # encabezado superior
            score += 0.1
        if score >= 0.45:
            candidates.append((line.upper() if has_legal and line == line.upper() else line, min(score, 1.0)))
    if not candidates:
        return None, 0.0
    candidates.sort(key=lambda c: -c[1])
    best, conf = candidates[0]
    if not LEGAL_FORMS.search(best):
        conf *= 0.75   # sin forma societaria: menos confianza
    return best, round(conf, 2)
