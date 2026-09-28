"""Arquitectura preparada para licencias (NO implementada aún a propósito).

Decisiones de diseño:
  * `LicenseProvider` es la interfaz que consumirá la app. Hoy se devuelve
    `PerpetualLocalLicense` (sin restricciones) para que el producto funcione
    sin conexión ni registro.
  * Cuando llegue el momento, se añadirá `OnlineLicenseProvider` que:
      - SOLO enviará el identificador de licencia y un hash del equipo.
      - NUNCA transmitirá PDFs, NIFs, nombres ni importes (privacidad).
      - Guardará en local (clave de Windows / archivo cifrado) el último
        estado válido para permitir funcionamiento offline temporal.
  * Ningún otro módulo de la aplicación importa este archivo salvo la UI
    (para mostrar el estado) y, en el futuro, el límite de facturas/mes.
"""
from __future__ import annotations

import abc
from dataclasses import dataclass, field
from datetime import date


@dataclass
class LicenseInfo:
    kind: str                 # "trial" | "mensual" | "anual" | "perpetua_local"
    holder: str = ""          # razón social de la gestoría
    machine_bound: bool = False
    valid_until: date | None = None
    features: list[str] = field(default_factory=lambda: ["extraction", "excel_export"])

    def is_active(self) -> bool:
        return self.valid_until is None or date.today() <= self.valid_until


class LicenseProvider(abc.ABC):
    @abc.abstractmethod
    def current_license(self) -> LicenseInfo: ...

    @abc.abstractmethod
    def activate(self, key: str) -> bool: ...


class PerpetualLocalLicense(LicenseProvider):
    """Licencia local ilimitada: comportamiento actual del MVP."""

    def current_license(self) -> LicenseInfo:
        return LicenseInfo(kind="perpetua_local", holder="Sin registrar")

    def activate(self, key: str) -> bool:  # pragma: no cover - placeholder
        return True


def get_license_provider() -> LicenseProvider:
    """Punto único de sustitución cuando exista backend de licencias."""
    return PerpetualLocalLicense()
