#!/usr/bin/env python3
"""FacturaPro — punto de entrada.

Modo gráfico (por defecto):   python main.py
Modo consola (para pruebas):   python main.py --cli <carpeta> [salida.xlsx]
"""
from __future__ import annotations

import sys


def cli(argv: list[str]) -> int:
    from pathlib import Path

    from app.services.processing import ProcessingService

    folder = Path(argv[0])
    out = Path(argv[1]) if len(argv) > 1 else folder / "facturas_procesadas.xlsx"
    service = ProcessingService()

    def progress(kind: str, data: dict) -> None:
        if kind == "file":
            print(f"[{data['done']}/{data['total']}] {data['archivo']} -> {data['estado']}")

    summary = service.process_folder(folder, on_progress=progress)
    for line in summary.summary_lines():
        print(line)
    path = service.exporter.export(summary.invoices, out)
    print("Excel generado en:", path)
    return 0


def gui() -> None:
    from app.ui.main_window import run_app
    run_app()


if __name__ == "__main__":
    args = sys.argv[1:]
    if args and args[0] == "--cli":
        raise SystemExit(cli(args[1:]))
    gui()
