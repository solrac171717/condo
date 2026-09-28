"""Modelo de datos central: una factura extraída de un PDF.

Cada campo extraído lleva asociado una puntuación de confianza (0.0-1.0)
para poder marcar revisiones sin inventar datos: si un dato no aparece,
el valor queda None y nunca se rellena automáticamente.
"""
from __future__ import annotations

import enum
from dataclasses import dataclass, field
from typing import Optional


class ProcessingStatus(str, enum.Enum):
    """Estado final del procesamiento de una factura."""

    OK = "OK"                # Todos los campos críticos extraídos y validados
    REVIEW = "REVISAR"       # Faltan campos o hay advertencias: requiere revisión manual
    ERROR = "ERROR"          # El PDF no pudo procesarse (corrupto, ilegible...)


# Campos que deben existir para que una factura se considere completa
CRITICAL_FIELDS = ("nif", "proveedor", "base_imponible", "iva", "total")


@dataclass
class FieldValue:
    """Valor extraído con su nivel de confianza (0..1)."""

    value: Optional[object] = None
    confidence: float = 0.0

    def is_present(self) -> bool:
        return self.value is not None and str(self.value).strip() != ""


@dataclass
class InvoiceData:
    """Resultado de extraer y validar una factura."""

    archivo: str                                  # Nombre del archivo original
    ruta_pdf: str = ""                            # Ruta completa (no se exporta a Excel)

    nif: FieldValue = field(default_factory=FieldValue)
    proveedor: FieldValue = field(default_factory=FieldValue)
    numero_factura: FieldValue = field(default_factory=FieldValue)
    fecha: FieldValue = field(default_factory=FieldValue)
    base_imponible: FieldValue = field(default_factory=FieldValue)
    iva: FieldValue = field(default_factory=FieldValue)
    total: FieldValue = field(default_factory=FieldValue)
    tipo_iva: FieldValue = field(default_factory=FieldValue)     # ej. "21%" / "10% + 21%"
    retencion_irpf: FieldValue = field(default_factory=FieldValue)

    estado: ProcessingStatus = ProcessingStatus.REVIEW
    advertencias: list[str] = field(default_factory=list)
    errores: list[str] = field(default_factory=list)
    origen_texto: str = "pdf"                     # "pdf" | "ocr" | "mixto" | "imagen_ocr"
    confianza_media: float = 0.0
    nif_ambiguo: bool = False                      # no se distingue proveedor de cliente

    # ------------------------------------------------------------------
    def missing_critical_fields(self) -> list[str]:
        return [f for f in CRITICAL_FIELDS if not getattr(self, f).is_present()]

    def add_warning(self, msg: str) -> None:
        if msg not in self.advertencias:
            self.advertencias.append(msg)

    def add_error(self, msg: str) -> None:
        if msg not in self.errores:
            self.errores.append(msg)

    def compute_avg_confidence(self) -> float:
        vals = [getattr(self, f).confidence for f in CRITICAL_FIELDS]
        self.confianza_media = round(sum(vals) / len(vals), 3) if vals else 0.0
        return self.confianza_media

    # ------------------------------------------------------------------
    def to_row(self) -> dict:
        """Fila para el Excel. Los campos no detectados quedan vacíos (nunca inventados)."""
        def v(fv: FieldValue):
            return fv.value if fv.is_present() else ""

        notas = "; ".join(self.advertencias + self.errores)
        return {
            "Archivo": self.archivo,
            "NIF/CIF": v(self.nif),
            "Proveedor": v(self.proveedor),
            "Número factura": v(self.numero_factura),
            "Fecha": v(self.fecha),
            "Base imponible": v(self.base_imponible),
            "IVA": v(self.iva),
            "Total": v(self.total),
            "Tipo IVA": v(self.tipo_iva),
            "IRPF": v(self.retencion_irpf),
            "Origen texto": self.origen_texto,
            "Confianza": self.confianza_media,
            "Estado": self.estado.value,
            "Advertencias": notas,
        }
