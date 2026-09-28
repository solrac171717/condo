"""Ventana principal de FacturaPro.

Diseñada para personal de gestoría sin conocimientos técnicos:
  1. Seleccionar carpeta -> 2. Procesar -> 3. Ver resumen -> 4. Exportar Excel.
El procesamiento ocurre en un hilo de trabajo; la UI se actualiza mediante
una cola de eventos para no bloquearse nunca.
"""
from __future__ import annotations

import queue
import subprocess
import sys
import threading
from pathlib import Path

import customtkinter as ctk

APP_TITLE = "FacturaPro"
ACCENT = "#1f6aa5"
OK_GREEN = "#2e8b57"
WARN_AMBER = "#b8860b"
ERR_RED = "#c0392b"


class MainWindow(ctk.CTk):
    def __init__(self, service=None):
        super().__init__()
        from app.services.processing import ProcessingService
        self.service = service or ProcessingService()

        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")
        self.title(f"{APP_TITLE} — Extracción automática de facturas")
        self.geometry("760x680")
        self.minsize(640, 560)

        self._folder: Path | None = None
        self._summary = None
        self._events: queue.Queue = queue.Queue()
        self._worker: threading.Thread | None = None

        self._build_ui()
        self.after(100, self._poll_events)

    # ------------------------------------------------------------------
    def _build_ui(self):
        pad = dict(padx=20, pady=8)

        header = ctk.CTkFrame(self, fg_color=ACCENT, corner_radius=0)
        header.pack(fill="x")
        ctk.CTkLabel(header, text="FACTURAPRO", font=ctk.CTkFont(size=26, weight="bold"),
                     text_color="white").pack(pady=(14, 0))
        ctk.CTkLabel(header, text="Extracción automática de facturas · 100% local, sin nube",
                     font=ctk.CTkFont(size=13), text_color="#dbe9f5").pack(pady=(2, 14))

        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True)

        # --- Carpeta ---
        folder_frame = ctk.CTkFrame(body)
        folder_frame.pack(fill="x", **pad)
        ctk.CTkLabel(folder_frame, text="Carpeta de facturas",
                     font=ctk.CTkFont(size=14, weight="bold")).pack(anchor="w", padx=14, pady=(10, 2))
        row = ctk.CTkFrame(folder_frame, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(0, 12))
        self.folder_entry = ctk.CTkEntry(row, placeholder_text="Selecciona una carpeta con archivos PDF…")
        self.folder_entry.pack(side="left", fill="x", expand=True, padx=(0, 10))
        ctk.CTkButton(row, text="📁  Seleccionar carpeta", width=170,
                      command=self._choose_folder).pack(side="right")

        # --- Botón procesar ---
        btns = ctk.CTkFrame(body, fg_color="transparent")
        btns.pack(fill="x", **pad)
        self.process_btn = ctk.CTkButton(btns, text="PROCESAR FACTURAS", height=44,
                                         font=ctk.CTkFont(size=16, weight="bold"),
                                         command=self._start_processing)
        self.process_btn.pack(fill="x")
        self.cancel_btn = ctk.CTkButton(btns, text="Cancelar", height=30, width=110,
                                        fg_color="#888", hover_color="#666",
                                        state="disabled", command=self.service.cancel)
        self.cancel_btn.pack(side="right")

        # --- Progreso ---
        prog = ctk.CTkFrame(body)
        prog.pack(fill="x", **pad)
        ctk.CTkLabel(prog, text="Progreso", font=ctk.CTkFont(size=14, weight="bold")
                     ).pack(anchor="w", padx=14, pady=(10, 2))
        self.progress = ctk.CTkProgressBar(prog, height=18)
        self.progress.set(0)
        self.progress.pack(fill="x", padx=14, pady=(0, 4))
        self.status_label = ctk.CTkLabel(prog, text="Listo.", anchor="w")
        self.status_label.pack(fill="x", padx=14, pady=(0, 10))

        # --- Contadores + exportar ---
        stats = ctk.CTkFrame(body)
        stats.pack(fill="x", **pad)
        self.count_vars = {}
        grid = ctk.CTkFrame(stats, fg_color="transparent")
        grid.pack(fill="x", padx=14, pady=12)
        for i, (key, label, color) in enumerate((
                ("ok", "Correctas", OK_GREEN), ("review", "A revisar", WARN_AMBER),
                ("errors", "Errores", ERR_RED))):
            f = ctk.CTkFrame(grid, fg_color="transparent")
            f.grid(row=0, column=i, padx=8)
            v = ctk.StringVar(value="0")
            self.count_vars[key] = v
            ctk.CTkLabel(f, textvariable=v, font=ctk.CTkFont(size=28, weight="bold"),
                         text_color=color).pack()
            ctk.CTkLabel(f, text=label).pack()
        self.export_btn = ctk.CTkButton(stats, text="EXPORTAR A EXCEL", height=40,
                                        font=ctk.CTkFont(size=15, weight="bold"),
                                        fg_color=OK_GREEN, hover_color="#256e47",
                                        state="disabled", command=self._export_excel)
        self.export_btn.pack(fill="x", padx=14, pady=(0, 12))

        # --- Tabla de resultados ---
        results = ctk.CTkFrame(body)
        results.pack(fill="both", expand=True, **pad)
        ctk.CTkLabel(results, text="Resultados", font=ctk.CTkFont(size=14, weight="bold")
                     ).pack(anchor="w", padx=14, pady=(10, 2))
        cols = ["Archivo", "NIF/CIF", "Proveedor", "Base", "IVA", "Total", "Estado"]
        try:
            from tkinter import ttk
            style_name = "clam"
            table_frame = ctk.CTkFrame(results, fg_color="white")
            table_frame.pack(fill="both", expand=True, padx=14, pady=(0, 12))
            self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", height=8)
            try:
                self.tree.style.configure("Treeview", font=("Segoe UI", 10), rowheight=24)
                self.tree.style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))
            except Exception:
                pass
            widths = [150, 110, 170, 90, 80, 90, 70]
            for c, w in zip(cols, widths):
                self.tree.heading(c, text=c)
                self.tree.column(c, width=w, anchor="w")
            vsb = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
            self.tree.configure(yscrollcommand=vsb.set)
            self.tree.pack(side="left", fill="both", expand=True)
            vsb.pack(side="right", fill="y")
            self.tree.tag_configure("ok", foreground=OK_GREEN)
            self.tree.tag_configure("review", background="#fff6dd")
            self.tree.tag_configure("error", background="#fbe4de")
        except Exception:
            self.tree = None

    # ------------------------------------------------------------------
    def _choose_folder(self):
        from tkinter import filedialog
        path = filedialog.askdirectory(title="Selecciona la carpeta de facturas")
        if path:
            self._folder = Path(path)
            self.folder_entry.delete(0, "end")
            self.folder_entry.insert(0, str(self._folder))

    def _start_processing(self):
        if not self._folder or not self._folder.is_dir():
            from tkinter import messagebox
            messagebox.showwarning(APP_TITLE, "Selecciona primero una carpeta válida.")
            return
        self.process_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.export_btn.configure(state="disabled")
        if self.tree is not None:
            self.tree.delete(*self.tree.get_children())
        for v in self.count_vars.values():
            v.set("0")
        self.progress.set(0)
        self._worker = threading.Thread(
            target=self._run_in_thread, args=(self._folder,), daemon=True)
        self._worker.start()

    def _run_in_thread(self, folder: Path):
        try:
            summary = self.service.process_folder(folder, on_progress=self._on_service_event)
            self._events.put(("done", summary))
        except Exception as exc:  # noqa: BLE001
            self._events.put(("fatal", str(exc)))

    def _on_service_event(self, kind: str, data: dict):
        self._events.put((kind, data))

    def _poll_events(self):
        try:
            while True:
                kind, data = self._events.get_nowait()
                if kind == "start":
                    self.status_label.configure(
                        text=f"{data['total']} facturas encontradas. Iniciando…")
                elif kind == "file":
                    frac = data["done"] / max(data["total"], 1)
                    self.progress.set(frac)
                    self.status_label.configure(
                        text=f"Procesando {data['done']} / {data['total']}  —  {data['archivo']}")
                    self.count_vars["ok"].set(str(data["ok"]))
                    self.count_vars["review"].set(str(data["review"]))
                    self.count_vars["errors"].set(str(data["errors"]))
                    self._add_row(data.get("invoice"))
                elif kind == "invoice":
                    self._add_row(data)
                elif kind == "fatal":
                    self._finish_ui()
                    from tkinter import messagebox
                    messagebox.showerror(APP_TITLE, f"Error fatal: {data}")
                elif kind == "done":
                    self._summary = data
                    self._finish_ui()
                    lines = data.summary_lines()
                    self.status_label.configure(text="  |  ".join(lines))
                    self.progress.set(1.0 if not data.cancelled else self.progress.get())
                    if data.invoices:
                        self.export_btn.configure(state="normal")
                    from tkinter import messagebox
                    messagebox.showinfo(APP_TITLE, "\n".join(lines))
        except queue.Empty:
            pass
        self.after(100, self._poll_events)

    def _add_row(self, inv):
        """Añade una fila a la tabla de resultados con colores por estado."""
        if self.tree is None or inv is None:
            return
        from app.utils.numbers import format_es

        def money(fv):
            return format_es(fv.value) + " €" if fv.is_present() else "—"

        tag = {"OK": "ok", "REVISAR": "review", "ERROR": "error"}.get(inv.estado.value, "")
        self.tree.insert("", "end", values=(
            inv.archivo,
            inv.nif.value if inv.nif.is_present() else "NO DETECTADO",
            inv.proveedor.value if inv.proveedor.is_present() else "NO DETECTADO",
            money(inv.base_imponible), money(inv.iva), money(inv.total),
            inv.estado.value,
        ), tags=(tag,))

    def _finish_ui(self):
        self.process_btn.configure(state="normal")
        self.cancel_btn.configure(state="disabled")

    def _export_excel(self):
        if not self._summary or not self._summary.invoices:
            return
        from tkinter import filedialog, messagebox
        default_name = "facturas_procesadas.xlsx"
        path = filedialog.asksaveasfilename(
            title="Guardar Excel", defaultextension=".xlsx", initialfile=default_name,
            filetypes=[("Excel", "*.xlsx")])
        if not path:
            return
        out = self.service.exporter.export(self._summary.invoices, Path(path))
        msg = f"Excel generado:\n{out}"
        try:
            if sys.platform.startswith("win"):
                subprocess.Popen(["explorer", "/select,", str(out)])
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-R", str(out)])
            else:
                subprocess.Popen(["xdg-open", str(out.parent)])
        except Exception:
            pass
        messagebox.showinfo(APP_TITLE, msg)


def run_app() -> None:
    app = MainWindow()
    app.mainloop()
