"""Fixtures compartidas para los tests de FacturaPro."""
from __future__ import annotations

import io
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


@pytest.fixture(scope="session")
def samples_dir() -> Path:
    return ROOT / "sample_invoices"


@pytest.fixture(scope="session")
def pdf_text_bytes(samples_dir: Path) -> bytes:
    """PDF con capa de texto embebida (factura_001)."""
    return (samples_dir / "factura_001.pdf").read_bytes()


@pytest.fixture(scope="session")
def pdf_scanned_bytes() -> bytes:
    """PDF sin texto embebido (solo imagen): factura escaneada sintética."""
    import pymupdf

    src = pymupdf.open(stream=(ROOT / "sample_invoices" / "factura_001.pdf").read_bytes(), filetype="pdf")
    pix = src[0].get_pixmap(dpi=200)
    src.close()
    out = pymupdf.open()
    page = out.new_page(width=pix.width, height=pix.height)
    page.insert_image(pymupdf.Rect(0, 0, pix.width, pix.height), pixmap=pix)
    data = out.tobytes()
    out.close()
    return data


@pytest.fixture(scope="session")
def jpg_photo_bytes(pdf_scanned_bytes: bytes) -> bytes:
    """Una 'foto' JPG de una factura (para probar el pipeline de imágenes)."""
    from PIL import Image

    doc = None
    import pymupdf
    doc = pymupdf.open(stream=pdf_scanned_bytes, filetype="pdf")
    page = doc[0]
    img = Image.open(io.BytesIO(page.get_pixmap(dpi=150).tobytes("png")))
    buf = io.BytesIO()
    img.convert("RGB").save(buf, format="JPEG", quality=85)
    doc.close()
    return buf.getvalue()
