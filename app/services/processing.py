"""Servicio de procesamiento por lotes de facturas (orquestación).

Flujo por factura:
    PDF -> texto embebido -> (OCR local si página escaneada) -> extracción
    -> validación -> InvoiceData

Diseño para la UI:
  * `process_folder` se ejecuta en un HILO aparte (la UI nunca se bloquea).
  * Informa progreso mediante callback `on_progress(evento, datos)`.
  * Un error en una factura NO detiene el lote: se registra y continúa.
"""
from __future__ import annotations

import threading
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional

from app.excel.exporter import DEFAULT_EXCEL_NAME, ExcelExporter
from app.extraction.extractor import InvoiceExtractor
from app.models.invoice import InvoiceData, ProcessingStatus
from app.ocr.base import OcrEngine, OcrNotAvailableError, get_ocr_engine
from app.pdf.reader import IMAGE_EXTENSIONS, PdfContent, PdfReadError, PdfReader, find_pdf_files
from app.utils.logging import get_logger
from app.validation.validator import validate_invoice

log = get_logger("service")

ProgressCallback = Callable[[str, dict], None]


@dataclass
class ProcessingSummary:
    total_pdf: int = 0
    ok: int = 0
    review: int = 0
    errors: int = 0
    invoices: list[InvoiceData] = field(default_factory=list)
    cancelled: bool = False

    def summary_lines(self) -> list[str]:
        return [
            f"{self.total_pdf} facturas encontradas",
            f"{self.ok} procesadas correctamente",
            f"{self.review} necesitan revisión",
            f"{self.errors} errores",
        ]


class ProcessingService:
    def __init__(self, ocr_engine: Optional[OcrEngine] = None):
        self.reader = PdfReader()
        self.extractor = InvoiceExtractor()
        self.exporter = ExcelExporter()
        self._ocr = ocr_engine
        self._cancel = threading.Event()

    # ------------------------------------------------------------------
    @property
    def ocr(self) -> Optional[OcrEngine]:
        if self._ocr is None:
            try:
                self._ocr = get_ocr_engine()
            except OcrNotAvailableError as exc:
                log.warning("OCR no disponible: %s", exc)
                self._ocr = False  # type: ignore[assignment]  # sentinel "no hay OCR"
        return self._ocr or None

    def cancel(self) -> None:
        self._cancel.set()

    # ------------------------------------------------------------------
    def _text_from_pdf(self, path: Path) -> tuple[str, str]:
        """Devuelve (texto, origen). Aplica OCR local solo donde falta texto."""
        content: PdfContent = self.reader.read(path)
        texts = list(content.page_texts)
        is_image = path.suffix.lower() in IMAGE_EXTENSIONS
        origen = "imagen" if is_image else "pdf"
        if content.needs_ocr_pages:
            engine = self.ocr
            if engine is None:
                log.info("%s: páginas escaneadas pero sin motor OCR", path.name)
                origen = "escaneado_sin_ocr"
            else:
                for pageno in content.needs_ocr_pages:
                    png = self.reader.render_page_png(path, pageno, dpi=300)
                    ocr_text = engine.image_to_text(png)
                    if ocr_text and ocr_text.strip():
                        texts[pageno] = ocr_text
                if not is_image and content.has_embedded_text:
                    origen = "mixto"
                elif is_image:
                    origen = "imagen_ocr"
                else:
                    origen = "ocr"
        return "\n".join(texts), origen

    def process_one(self, path: Path) -> InvoiceData:
        inv = InvoiceData(archivo=path.name, ruta_pdf=str(path))
        try:
            text, origen = self._text_from_pdf(path)
            inv.origen_texto = origen
            if origen == "escaneado_sin_ocr":
                inv.add_error("PDF escaneado: instala Tesseract OCR para procesarlo")
                inv.estado = ProcessingStatus.ERROR
                return inv
            if not text.strip():
                inv.add_error("El PDF no contiene texto legible ni imágenes reconocibles")
                inv.estado = ProcessingStatus.ERROR
                return inv
            extracted = self.extractor.extract(text, path.name)
            # copiar campos al objeto ya asociado a la ruta
            for f in ("nif", "proveedor", "numero_factura", "fecha", "base_imponible",
                      "iva", "total", "tipo_iva", "retencion_irpf", "advertencias",
                      "confianza_media"):
                setattr(inv, f, getattr(extracted, f))
            validate_invoice(inv)
        except PdfReadError as exc:
            inv.add_error(str(exc))
            inv.estado = ProcessingStatus.ERROR
        except Exception as exc:  # noqa: BLE001 - una factura fallida no rompe el lote
            log.exception("Error inesperado procesando %s", path.name)
            inv.add_error(f"Error inesperado: {exc}")
            inv.estado = ProcessingStatus.ERROR
        return inv

    # ------------------------------------------------------------------
    def scan_folder(self, folder: str | Path) -> list[Path]:
        return find_pdf_files(folder)

    def process_folder(self, folder: str | Path,
                       on_progress: Optional[ProgressCallback] = None) -> ProcessingSummary:
        self._cancel.clear()
        summary = ProcessingSummary()
        pdfs = self.scan_folder(folder)
        summary.total_pdf = len(pdfs)
        if on_progress:
            on_progress("start", {"total": len(pdfs)})

        for i, pdf in enumerate(pdfs, start=1):
            if self._cancel.is_set():
                summary.cancelled = True
                break
            inv = self.process_one(pdf)
            summary.invoices.append(inv)
            if inv.estado == ProcessingStatus.OK:
                summary.ok += 1
            elif inv.estado == ProcessingStatus.REVIEW:
                summary.review += 1
            else:
                summary.errors += 1
            log.info("Procesado %s -> %s", pdf.name, inv.estado.value)
            if on_progress:
                on_progress("file", {
                    "done": i, "total": len(pdfs), "archivo": pdf.name,
                    "estado": inv.estado.value, "ok": summary.ok,
                    "review": summary.review, "errors": summary.errors,
                    "invoice": inv,
                })

        if on_progress:
            on_progress("finish", {
                "total": summary.total_pdf, "ok": summary.ok,
                "review": summary.review, "errors": summary.errors,
                "cancelled": summary.cancelled,
            })
        return summary

    def export_excel(self, invoices: list[InvoiceData], out_dir: str | Path,
                     filename: str = DEFAULT_EXCEL_NAME) -> Path:
        return self.exporter.export(invoices, Path(out_dir) / filename)
