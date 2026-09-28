"""Manejo robusto de números en formato español/europeo.

Reglas:
  * El punto es separador de miles:      "1.234,56" -> 1234.56
  * La coma es separador decimal:         "1210,00"  -> 1210.00
  * También se aceptan formatos anglosajones habituales en software
    de facturación:                      "1,234.56"  -> 1234.56
  * Símbolos de moneda y espacios se ignoran.
  * Nunca se redondea silenciosamente: parse_spain_number devuelve None
    si el texto no es un número válido (no se inventan valores).
"""
from __future__ import annotations

import re
from typing import Optional

# Un "número con separadores": grupos de dígitos alternando . o ,
_NUM_RE = re.compile(
    r"^\s*(?P<sign>-|\+)?\s*"
    r"(?P<body>\d{1,3}(?:[.,]\d{3})*(?:[.,]\d{1,2})?|\d+(?:[.,]\d{1,2})?)\s*"
    r"(?:€|EUR|euros)?\s*$",
    re.IGNORECASE,
)

_CURRENCY_STRIP_RE = re.compile(r"[€$]|\b(?:EUR|USD|euros?)\b", re.IGNORECASE)


def parse_spain_number(text: str) -> Optional[float]:
    """Convierte '1.234,56 €' -> 1234.56. Devuelve None si no es un número."""
    if text is None:
        return None
    s = _CURRENCY_STRIP_RE.sub("", str(text)).strip()
    if not s:
        return None
    m = _NUM_RE.match(s)
    if not m:
        return None
    sign = -1.0 if m.group("sign") == "-" else 1.0
    body = m.group("body")

    if "," in body and "." in body:
        # El separador DECIMAL es el que aparece en la última posición
        last_comma = body.rfind(",")
        last_dot = body.rfind(".")
        if last_comma > last_dot:
            # español: 1.234,56
            body = body.replace(".", "").replace(",", ".")
        else:
            # anglosajón: 1,234.56
            body = body.replace(",", "")
    elif "," in body:
        parts = body.split(",")
        if len(parts) == 2 and len(parts[1]) == 3 and len(parts[0]) <= 3 and parts[0].isdigit():
            # ambiguo: "1,234" puede ser miles (anglosajón) o decimales (español)
            # En contexto español interpretamos coma decimal SIEMPRE que no haya
            # más grupos; pero "1,234" con 3 decimales es improbable en euros:
            # lo tratamos como miles únicamente si hay un grupo previo de 1-3 cifras
            # y el valor sin coma es entero razonable. Regla conservadora:coma = decimal.
            body = body.replace(",", ".")
        else:
            # "1234,5" o "12,50" -> coma decimal
            body = body.replace(",", ".")
    elif "." in body:
        parts = body.split(".")
        if len(parts) > 1 and len(parts[-1]) == 3 and all(len(p) <= 3 for p in parts[:-1]):
            # "1.234" -> separador de miles español
            body = body.replace(".", "")
        # en otro caso ("12.34") ya es decimal anglosajón, se deja igual

    try:
        return round(sign * float(body), 2)
    except ValueError:
        return None


def find_numbers_in_line(line: str) -> list[tuple[str, float]]:
    """Devuelve todos los números embebidos en una línea como (texto, valor)."""
    results: list[tuple[str, float]] = []
    token_re = re.compile(r"[-+]?\d[\d.,]*\d|\d")
    for m in token_re.finditer(line):
        val = parse_spain_number(m.group(0))
        if val is not None:
            results.append((m.group(0), val))
    return results


def format_es(value: float, decimals: int = 2) -> str:
    """Formatea 1234.5 -> '1.234,50' (para mostrar por pantalla)."""
    s = f"{value:,.{decimals}f}"
    return s.replace(",", "\x00").replace(".", ",").replace("\x00", ".")


def nearly_equal(a: float, b: float, tol: float = 0.02) -> bool:
    """Comparación con tolerancia para redondeos de factura (céntimos)."""
    return abs(a - b) <= tol
