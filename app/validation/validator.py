"""Validación de facturas extraídas. Regla de oro: NUNCA se inventan datos.

Un dato ausente permanece ausente y la factura queda marcada como REVISAR.
Aquí solo se comprueba coherencia y formato; no se corrigen valores salvo
que la aritmética lo confirme de forma exacta.
"""
from __future__ import annotations

from app.extraction.nif import validate_nif
from app.models.invoice import CRITICAL_FIELDS, InvoiceData, ProcessingStatus
from app.utils.numbers import nearly_equal

# Umbral mínimo de confianza por debajo del cual un campo exige revisión
CONFIDENCE_REVIEW_THRESHOLD = 0.55


def validate_invoice(inv: InvoiceData) -> InvoiceData:
    """Aplica todas las validaciones y fija `inv.estado`."""
    base = inv.base_imponible.value if inv.base_imponible.is_present() else None
    iva = inv.iva.value if inv.iva.is_present() else None
    total = inv.total.value if inv.total.is_present() else None
    irpf = inv.retencion_irpf.value if inv.retencion_irpf.is_present() else None

    # --- formato/rangos de los importes ---
    for name, val in (("Base imponible", base), ("IVA", iva), ("Total", total)):
        if val is not None:
            if not isinstance(val, (int, float)):
                inv.add_warning(f"{name} no es un número válido")
            elif val < 0:
                inv.add_warning(f"{name} negativo ({val}); posible abono o error")

    # --- NIF con checksum inválido ---
    if inv.nif.is_present() and not validate_nif(str(inv.nif.value)):
        inv.add_warning("NIF/CIF detectado con formato o dígito de control no válido")

    # --- validación matemática: base + IVA - IRPF == total ---
    math_ok = None
    if base is not None and total is not None:
        if iva is not None:
            expected = round(base + iva - (irpf or 0), 2)
            if nearly_equal(expected, total):
                math_ok = True
            else:
                math_ok = False
                diff = round(total - expected, 2)
                inv.add_warning(
                    f"Diferencia detectada: Base({base}) + IVA({iva})"
                    f"{' - IRPF(' + str(irpf) + ')' if irpf else ''} "
                    f"no coincide con Total({total}); diferencia {diff} €")
        elif irpf is not None and nearly_equal(round(base - irpf, 2), total):
            math_ok = True

    # --- coherencia del tipo de IVA con la cuota ---
    if math_ok and iva is not None and base and inv.tipo_iva.is_present():
        rates = [float(r.strip().rstrip("%")) for r in str(inv.tipo_iva.value).split("+") if r.strip()]
        implied = sorted({round(iva * 100 / b, 1) for b in [base]}) if base else []
        # si hay un único tramo, comprobar que la cuota lo representa razonablemente
        if len(rates) == 1:
            expected_cuota = round(base * rates[0] / 100, 2)
            if not nearly_equal(expected_cuota, iva, tol=max(0.05, abs(iva) * 0.02)):
                alt_rate = round(iva * 100 / base, 2)
                inv.add_warning(
                    f"Cuota de IVA ({iva}) no se corresponde con tipo {rates[0]:g}% "
                    f"(esperado {expected_cuota}); tipo implícito ≈ {alt_rate:g}%")

    # --- campos críticos faltantes ---
    missing = inv.missing_critical_fields()
    for f in missing:
        label = {"nif": "NIF", "proveedor": "Proveedor", "base_imponible": "Base imponible",
                 "iva": "IVA", "total": "Total"}[f]
        inv.add_warning(f"{label}: NO DETECTADO")

    # --- confianza baja en algún campo crítico ---
    low = [f for f in CRITICAL_FIELDS
           if getattr(inv, f).is_present() and getattr(inv, f).confidence < CONFIDENCE_REVIEW_THRESHOLD]
    if low:
        inv.add_warning("Confianza baja en: " + ", ".join(low))

    inv.compute_avg_confidence()

    # --- estado final ---
    if inv.errores:
        inv.estado = ProcessingStatus.ERROR
    elif missing or inv.advertencias or math_ok is False or inv.nif_ambiguo:
        # Regla de seguridad: ante cualquier advertencia, dato ausente,
        # descuadre aritmético o NIF ambiguo, la factura va a REVISIÓN.
        inv.estado = ProcessingStatus.REVIEW
    else:
        inv.estado = ProcessingStatus.OK
    return inv
