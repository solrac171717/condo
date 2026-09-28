"""Sistema de logs local de FacturaPro.

Escribe en <directorio_app>/logs/facturapro.log (rotativo).
POLÍTICA DE PRIVACIDAD: los logs NUNCA deben contener el texto completo
de las facturas ni importes sensibles; solo nombres de archivo, estados
y mensajes técnicos.
"""
from __future__ import annotations

import logging
import logging.handlers
import os
import sys
from pathlib import Path

_LOGGER_NAME = "facturapro"
_configured = False


def app_dir() -> Path:
    """Directorio base de la aplicación (soporta PyInstaller --onefile)."""
    if getattr(sys, "frozen", False):  # Ejecutable generado con PyInstaller
        return Path(os.path.dirname(sys.executable))
    return Path(__file__).resolve().parent.parent.parent


def log_dir() -> Path:
    d = app_dir() / "logs"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_logger(name: str | None = None) -> logging.Logger:
    global _configured
    logger = logging.getLogger(_LOGGER_NAME)
    if not _configured:
        logger.setLevel(logging.DEBUG)
        fmt = logging.Formatter(
            "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
        fh = logging.handlers.RotatingFileHandler(
            log_dir() / "facturapro.log", maxBytes=2_000_000, backupCount=5,
            encoding="utf-8",
        )
        fh.setFormatter(fmt)
        fh.setLevel(logging.INFO)
        logger.addHandler(fh)

        sh = logging.StreamHandler()
        sh.setFormatter(fmt)
        sh.setLevel(logging.DEBUG if os.environ.get("FACTURAPRO_DEBUG") else logging.WARNING)
        logger.addHandler(sh)
        _configured = True
    if name:
        return logger.getChild(name)
    return logger
