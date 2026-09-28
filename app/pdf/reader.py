"""Lectura de archivos PDF e imágenes (extracción de texto embebido y detección de escaneos).

Usa PyMuPDF. No depende de la red: todo se procesa en local.
La capa OCR se invoca desde app/ocr a través del servicio, no aquí.

También admite fotos de facturas (JPG/PNG/TIFF/BMP/WEBP): se envuelven en un
PDF en memoria para reutilizar el mismo pipeline (renderizado + OCR local).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import pymupdf

from app.utils.logging import get_logger

log = get_logger("pdf")

# Umbral: si una página tiene menos de este número de caracteres de texto
# embebido, se considera "página escaneada" y necesitará OCR.
MIN_TEXT_CHARS_PER_PAGE = 20

# Extensiones de imagen admitidas (fotos de facturas hechas con el móvil)
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".webp"}


@dataclass
class PdfContent:
    """Contenido textual de un PDF, página a página."""

    path: str
    page_texts: list[str] = field(default_factory=list)
    needs_ocr_pages: list[int] = field(default_factory=list)  # índices de páginas sin texto

    @property
    def has_embedded_text(self) -> bool:
        return any(len(t.strip()) >= MIN_TEXT_CHARS_PER_PAGE for t in self.page_texts)

    @property
    def all_pages_scanned(self) -> bool:
        return not self.has_embedded_text

    @property
    def full_text(self) -> str:
        return "\n".join(self.page_texts)


class PdfReadError(Exception):
    """El PDF no puede abrirse o está corrupto."""


class PdfReader:
    """Lee PDFs (e imágenes de facturas) y devuelve su texto embebido,
    marcando las páginas que requieren OCR."""

    def read(self, path: str | Path) -> PdfContent:
        p = Path(path)
        if not p.is_file():
            raise PdfReadError(f"El archivo no existe: {p}")
        is_image = p.suffix.lower() in IMAGE_EXTENSIONS
        try:
            doc = self._open(p, as_image=is_image)
        except PdfReadError:
            raise
        except Exception as exc:  # noqa: BLE001 - queremos capturar cualquier fallo de apertura
            log.warning("No se pudo abrir el documento %s: %s", p.name, exc)
            raise PdfReadError(f"No se pudo abrir el documento: {exc}") from exc

        content = PdfContent(path=str(p))
        try:
            if doc.is_encrypted and not doc.authenticate(""):
                raise PdfReadError("El PDF está protegido con contraseña")
            for i, page in enumerate(doc):
                text = "" if is_image else (page.get_text("text") or "")
                content.page_texts.append(text)
                if len(text.strip()) < MIN_TEXT_CHARS_PER_PAGE:
                    content.needs_ocr_pages.append(i)
        finally:
            doc.close()

        log.info(
            "Leído %s: %d páginas, %d requieren OCR",
            p.name, len(content.page_texts), len(content.needs_ocr_pages),
        )
        return content

    @staticmethod
    def _open(p: Path, as_image: bool) -> "pymupdf.Document":
        """Abre un PDF normal o envuelve una imagen en un PDF en memoria."""
        if not as_image:
            return pymupdf.open(str(p))
        img_doc = pymupdf.open()               # PDF vacío en memoria
        pix = pymupdf.Pixmap(str(p))           # carga la foto localmente
        if pix.colorspace and pix.colorspace.n > 3:
            pix = pymupdf.Pixmap(pymupdf.csRGB, pix)
        rect = pymupdf.Rect(0, 0, pix.width, pix.height)
        page = img_doc.new_page(width=rect.width, height=rect.height)
        page.insert_image(rect, pixmap=pix)
        return img_doc

    def render_page_png(self, path: str | Path, page_index: int, dpi: int = 300) -> bytes:
        """Renderiza una página a PNG en memoria (para pasarla al motor OCR)."""
        as_image = Path(path).suffix.lower() in IMAGE_EXTENSIONS
        doc = self._open(Path(path), as_image=as_image)
        try:
            page = doc[page_index]
            zoom = max(dpi / 72.0, 1.0)
            if as_image:
                # En fotos, no reducir por debajo de la resolución original
                pix0 = page.get_pixmap(dpi=72)
                scale = max(zoom, 1.0)
                pix = page.get_pixmap(matrix=pymupdf.Matrix(scale, scale))
                del pix0
            else:
                pix = page.get_pixmap(dpi=dpi)
            return pix.tobytes("png")
        finally:
            doc.close()


def find_pdf_files(folder: str | Path, recursive: bool = True,
                   include_images: bool = True) -> list[Path]:
    """Busca todos los *.pdf (y opcionalmente fotos) de una carpeta."""
    folder = Path(folder)
    if not folder.is_dir():
        return []
    it = folder.rglob("*") if recursive else folder.glob("*")
    exts = {".pdf"} | (IMAGE_EXTENSIONS if include_images else set())
    docs = [f for f in it if f.is_file() and f.suffix.lower() in exts]
    return sorted(docs, key=lambda f: str(f).lower())
