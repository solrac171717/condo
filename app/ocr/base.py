"""Capa OCR local con motor intercambiable (patrón Strategy).

`OcrEngine` es una interfaz abstracta: hoy usamos Tesseract vía pytesseract,
pero se puede sustituir por otro motor local (PaddleOCR, Pimms, un modelo
propio...) sin tocar el resto de la aplicación: basta registrar otra clase
en `get_ocr_engine()`.

IMPORTANTE (privacidad): todos los motores deben ejecutarse 100% en local.
Ningún motor debe implementar envíos de imágenes a servicios remotos.
"""
from __future__ import annotations

import abc
import shutil
from functools import lru_cache


class OcrNotAvailableError(RuntimeError):
    """No hay ningún motor OCR utilizable en este equipo."""


class OcrEngine(abc.ABC):
    """Interfaz mínima de un motor OCR local."""

    name: str = "base"

    @abc.abstractmethod
    def is_available(self) -> bool:
        """True si el motor puede ejecutarse en este equipo."""

    @abc.abstractmethod
    def image_to_text(self, png_bytes: bytes) -> str:
        """Devuelve el texto reconocido de una imagen PNG."""


class TesseractOcrEngine(OcrEngine):
    """OCR local basado en Tesseract + pytesseract (idioma español)."""

    name = "tesseract"

    def __init__(self, lang: str = "spa+eng"):
        self.lang = lang

    @staticmethod
    def tesseract_binary() -> str | None:
        return shutil.which("tesseract")

    def is_available(self) -> bool:
        if not self.tesseract_binary():
            return False
        try:
            import pytesseract  # noqa: F401
            return True
        except ImportError:
            return False

    def image_to_text(self, png_bytes: bytes) -> str:
        import io

        import pytesseract
        from PIL import Image, ImageOps

        img = Image.open(io.BytesIO(png_bytes))
        # Preprocesamiento local para mejorar fotos/escaneos:
        # escala mínima + convertida a grayscale. El autocontraste ayuda con
        # fotos oscuras o con sombras hechas con el móvil.
        try:
            if img.mode not in ("L", "RGB"):
                img = img.convert("RGB")
            if min(img.size) < 1400:
                ratio = 1400 / min(img.size)
                img = img.resize((int(img.width * ratio), int(img.height * ratio)),
                                 Image.LANCZOS)
            gray = ImageOps.autocontrast(img.convert("L"), cutoff=1)
            text = pytesseract.image_to_string(gray, lang=self.lang)
            if text and text.strip():
                return text
        except Exception:  # noqa: BLE001 - si el preprocesado falla, probamos sin él
            pass
        return pytesseract.image_to_string(img, lang=self.lang)


@lru_cache(maxsize=1)
def get_ocr_engine() -> OcrEngine:
    """Selecciona el mejor motor OCR disponible. Punto único de sustitución."""
    candidates: list[OcrEngine] = [
        TesseractOcrEngine(),
        # Futuros motores locales se añadirían aquí, p.ej.:
        # PaddleOcrEngine(), RapidOcrEngine(),
    ]
    for engine in candidates:
        if engine.is_available():
            return engine
    raise OcrNotAvailableError(
        "No hay motor OCR disponible. Instala Tesseract para Windows "
        "(https://github.com/UB-Mannheim/tesseract/wiki) y reintenta."
    )
