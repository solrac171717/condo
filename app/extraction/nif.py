"""Detección y validación de NIF/CIF españoles.

Formatos válidos:
  * CIF (empresas):        letra organizativa + 7 dígitos + 1 control
                           letras: A B G J U (entidades), P Q S K N D (otros)
  * NIF persona física:    8 dígitos + letra de control
  * NIE:                 X/Y/Z + 7 dígitos + letra
Validación del dígito/letra de control según algoritmo oficial de la AEAT.
"""
from __future__ import annotations

import re

_LETROS_CIF = set("ABGJPQSKND")          # organizativas + entidades especiales
_CONTROL_CIF = "JABCDEFGHI"               # tabla de control para CIF
_NIF_RE = re.compile(r"\b(\d{8})\s*([TRWMEYFGHJBZNLSXV])\b", re.IGNORECASE)
_CIF_RE = re.compile(r"\b([ABGJPQSKND])[\s-]?(\d{7})[\s-]?([A-Z0-9])\b")
_NIE_RE = re.compile(r"\b([XYZ])(\d{7})[\s-]?([TRWMEYFGHJBZNLSXV])\b", re.IGNORECASE)

# Etiquetas típicas junto al número identificador en facturas españolas
NIF_LABELS = ("NIF", "N.I.F", "CIF", "C.I.F", "NIE", "N.I.E",
              "VAT", "ES VAT", "CIF/NIF", "NIF-CIF")

# Contexto que indica que el NIF cercano pertenece al CLIENTE (no al proveedor).
# En una factura, quien emite (proveedor) aparece en el encabezado; los datos
# del cliente aparecen bajo estas etiquetas.
CLIENT_CONTEXT_RE = re.compile(
    r"\b(cliente|facturar\s+a|emitida\s+para|a\s+atenci[oó]n|destinatario|"
    r"comprador|adquirente)\b", re.IGNORECASE)


def _lds_char(digits: str) -> str:
    """Letra de control DNI: resto módulo 23."""
    return "TRWAGMYFPDXBNJZSQVHLCKE"[int(digits) % 23]


def _cif_control(organizational: str, digits7: str, control: str) -> bool:
    total = 0
    for i, d in enumerate(digits7):
        d = int(d)
        if i % 2 == 0:            # posiciones pares (índice impar desde 1): doble
            d = d * 2
            if d > 9:
                d -= 9
        total += d
    c = (10 - total % 10) % 10
    expected_letter = _CONTROL_CIF[c]
    ctrl = control.upper()
    if organizational in "ABG":   # siempre letra... salvo sociedades civiles (c digit)
        return ctrl == expected_letter or (ctrl.isdigit() and int(ctrl) == c)
    if organizational in "PQS":   # personas físicas: letra de control por módulo 23
        num = {"P": "0", "Q": "1", "S": "2"}[organizational] + digits7[:6]
        return _lds_char(num) == ctrl
    # K S N D etc.: aceptamos letra o dígito de control
    return ctrl == expected_letter or (ctrl.isdigit() and int(ctrl) == c)


def validate_nif(candidate: str) -> bool:
    """Comprueba el formato Y el checksum del identificador."""
    s = candidate.upper().replace(" ", "").replace(".", "").replace("-", "")
    m = re.fullmatch(r"(\d{8})([A-Z])", s)
    if m:
        return _lds_char(m.group(1)) == m.group(2)
    m = re.fullmatch(r"([XYZ])(\d{7})([A-Z])", s)
    if m:
        num = {"X": "0", "Y": "1", "Z": "2"}[m.group(1)] + m.group(2)
        return _lds_char(num) == m.group(3)
    m = re.fullmatch(r"([ABGJPQSKND])(\d{7})([A-Z0-9])", s)
    if m:
        return _cif_control(m.group(1), m.group(2), m.group(3))
    return False


def find_nifs(text: str) -> list[tuple[str, float]]:
    """Busca identificadores fiscales en un texto. Devuelve [(nif_normalizado, confianza)]."""
    found: dict[str, float] = {}
    up = text.upper()

    def add(raw: str, conf: float, labeled: bool, pos: int):
        norm = raw.upper().replace(" ", "").replace(".", "").replace("-", "")
        if not validate_nif(norm):
            conf *= 0.45     # con formato plausible pero checksum inválido
        if labeled:
            conf = min(1.0, conf + 0.25)
        # Penalizar fuertemente los NIF que aparecen bajo etiquetas de cliente:
        # nos interesa el CIF/NIF del EMISOR (proveedor), no del destinatario.
        window = text[max(0, pos - 160):pos]
        client_hit = CLIENT_CONTEXT_RE.search(window)
        if client_hit:
            conf *= 0.3
            # Si además la etiqueta NIF/CIF va justo antes del número y está
            # dentro del bloque "Cliente:" (sin otro encabezado de sección en
            # medio), es con seguridad el NIF del CLIENTE: descartarlo.
            between = window[client_hit.end():]
            if re.search(r"(N[II]\.?\s*F|C[IÍ]\.?\s*F)\s*[:.]?\s*$", between, re.IGNORECASE) \
                    and not re.search(r"\b(proveedor|emisor|expedidor|empresa)\b", between, re.IGNORECASE):
                conf = 0.0
        prev = found.get(norm, 0.0)
        if conf > prev:
            found[norm] = round(conf, 2)

    for m in _CIF_RE.finditer(up):
        add(m.group(0), 0.9, _is_labeled(text, m.start()), m.start())
    for m in _NIE_RE.finditer(up):
        add(m.group(0), 0.85, _is_labeled(text, m.start()), m.start())
    for m in _NIF_RE.finditer(up):
        # evitar falsos positivos puros de 8 dígitos sin contexto
        labeled = _is_labeled(text, m.start())
        near_invoice_ctx = _has_number_context(text, m.start())
        if labeled or near_invoice_ctx:
            add(m.group(0), 0.8, labeled, m.start())
    return sorted(found.items(), key=lambda kv: -kv[1])


def _is_labeled(text: str, pos: int) -> bool:
    window = text[max(0, pos - 25):pos].upper()
    return any(lbl.replace(".", "") in window.replace(".", "") or lbl in window
               for lbl in NIF_LABELS)


def _has_number_context(text: str, pos: int) -> bool:
    window = text[max(0, pos - 60):min(len(text), pos + 60)].upper()
    return any(k in window for k in ("FACTURA", "IVA", "BASE", "TOTAL", "EUR", "€"))
