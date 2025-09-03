# -*- coding: utf-8 -*-
"""
comparador_similitud_gui_v2.py

GUI para comparar dos columnas de dos tablas (CSV/XLSX/MD) y encontrar
las 2 mejores coincidencias por registro con porcentaje de similitud.

Requisitos: Python 3.12.5 en Windows 10/11
Librerías: pandas, openpyxl (para .xlsx), tkinter (stdlib)
Notas:
- No se sube información fuera de la red corporativa (offline-first).
- Logs rotativos (5 MB), mensajes en español, sin PII en logs.
- Evita credenciales incrustadas.
- Soporta archivos hasta ~500 MB (depende de RAM/columnas).
"""

from __future__ import annotations
import os
import re
import sys
import time
import math
import queue
import threading
import unicodedata
import logging
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import List, Tuple, Optional

import pandas as pd
from tkinter import (
    Tk, Toplevel, Frame, Label, Button, filedialog, messagebox, StringVar,
    BOTH, X, Y, LEFT, RIGHT, TOP, NSEW, END, Text, Scrollbar, Listbox
)
from tkinter import ttk

# ---------------------------------------------------------------------
# Configuración de logging
# ---------------------------------------------------------------------
LOG_DIR = Path.home() / "comparador_similitud_logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "comparador.log"

logger = logging.getLogger("comparador")
logger.setLevel(logging.INFO)
handler = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
handler.setFormatter(fmt)
logger.addHandler(handler)

# ---------------------------------------------------------------------
# Utilidades de normalización y similitud (sin dependencias externas)
# ---------------------------------------------------------------------

def normaliza(texto: str) -> str:
    """Normaliza texto: quita tildes, deja solo A-Z0-9 y mayúsculas."""
    if pd.isna(texto):
        return ""
    s = str(texto)
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = re.sub(r"[^A-Za-z0-9]+", " ", s)
    s = s.upper().strip()
    s = re.sub(r"\s+", " ", s)
    return s

def seq_ratio(a: str, b: str) -> float:
    from difflib import SequenceMatcher
    return SequenceMatcher(None, a, b).ratio()

def token_set_ratio(a: str, b: str) -> float:
    ta = set(a.split())
    tb = set(b.split())
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    inter = len(ta & tb)
    prec = inter / len(ta)
    rec = inter / len(tb)
    return 0.0 if (prec + rec) == 0 else (2 * prec * rec / (prec + rec))

def similitud_compuesta(a: str, b: str) -> float:
    na, nb = normaliza(a), normaliza(b)
    if not na and not nb:
        return 1.0
    r1 = seq_ratio(na, nb)
    r2 = token_set_ratio(na, nb)
    return 0.6 * r1 + 0.4 * r2

# ---------------------------------------------------------------------
# Carga de archivos (CSV / XLSX / MD)
# ---------------------------------------------------------------------

def es_markdown_table_line(line: str) -> bool:
    return "|" in line and not line.strip().startswith(":")

def parse_markdown_table(md_text: str) -> Optional[pd.DataFrame]:
    lines = [ln.rstrip("\n") for ln in md_text.splitlines()]
    blocks: List[List[str]] = []
    current: List[str] = []
    for ln in lines:
        if es_markdown_table_line(ln):
            current.append(ln)
        else:
            if current:
                blocks.append(current)
                current = []
    if current:
        blocks.append(current)

    for blk in blocks:
        if len(blk) < 2:
            continue
        sep_idx = None
        for i, ln in enumerate(blk[:3]):
            if re.search(r"\|\s*:?-{3,}\s*(\|\s*:?-{3,}\s*)+\|?", ln):
                sep_idx = i
                break
        if sep_idx is None:
            continue
        header_line = blk[0].strip().strip("|")
        headers = [h.strip() for h in header_line.split("|")]
        data_lines = [l for l in blk[sep_idx + 1:] if "|" in l]
        rows = []
        for dl in data_lines:
            parts = [p.strip() for p in dl.strip().strip("|").split("|")]
            if len(parts) < len(headers):
                parts += [""] * (len(headers) - len(parts))
            elif len(parts) > len(headers):
                parts = parts[:len(headers)]
            rows.append(parts)
        if rows:
            return pd.DataFrame(rows, columns=headers)
    return None

def cargar_archivo(path: str, parent: Tk) -> pd.DataFrame:
    ext = Path(path).suffix.lower()
    logger.info(f"Cargando archivo: {path}")
    if ext == ".csv":
        try:
            return pd.read_csv(path, dtype=str, low_memory=False, encoding="utf-8")
        except Exception:
            return pd.read_csv(path, dtype=str, low_memory=False, encoding="latin-1")
    elif ext == ".xlsx":
        xls = pd.ExcelFile(path, engine="openpyxl")
        sheets = xls.sheet_names
        sel = seleccionar_opcion(parent, "Selecciona la hoja", sheets)
        if sel is None:
            raise RuntimeError("Operación cancelada al seleccionar hoja.")
        return pd.read_excel(path, sheet_name=sel, dtype=str, engine="openpyxl")
    elif ext == ".xls":
        # xlrd>=2.0 no soporta .xls. Sugerir alternativas.
        raise ValueError(
            "El formato .xls ya no es leído por defecto.\n"
            "Opciones:\n"
            "  1) Abrir y guardar como .xlsx.\n"
            "  2) Instalar xlrd==1.2.0 y usar engine='xlrd'.\n"
            "  3) Convertir el archivo con Excel/LibreOffice."
        )
    elif ext == ".md":
        with open(path, "r", encoding="utf-8") as f:
            md = f.read()
        df = parse_markdown_table(md)
        if df is None:
            raise ValueError("No se detectó una tabla Markdown válida en el archivo.")
        return df.astype(str)
    else:
        raise ValueError("Formato no soportado. Usa .csv, .xlsx o .md")

def seleccionar_opcion(parent: Tk, titulo: str, opciones: List[str]) -> Optional[str]:
    result = {"value": None}

    def on_ok():
        sel = lb.curselection()
        if sel:
            result["value"] = opciones[sel[0]]
            win.destroy()
        else:
            messagebox.showwarning("Selección", "Selecciona una opción.")

    def on_cancel():
        result["value"] = None
        win.destroy()

    win = Toplevel(parent)
    win.title(titulo)
    win.grab_set()
    win.resizable(False, False)

    Label(win, text=titulo, font=("Segoe UI", 10, "bold")).pack(padx=10, pady=(10, 5))
    fr = Frame(win)
    fr.pack(padx=10, pady=5, fill=BOTH, expand=True)
    sb = Scrollbar(fr)
    sb.pack(side=RIGHT, fill=Y)
    lb = Listbox(fr, height=8, yscrollcommand=sb.set)
    for o in opciones:
        lb.insert(END, o)
    lb.pack(side=LEFT, fill=BOTH, expand=True)
    sb.config(command=lb.yview)

    btn_fr = Frame(win)
    btn_fr.pack(padx=10, pady=(5, 10))
    Button(btn_fr, text="Aceptar", command=on_ok, width=12).pack(side=LEFT, padx=5)
    Button(btn_fr, text="Cancelar", command=on_cancel, width=12).pack(side=RIGHT, padx=5)

    win.wait_window()
    return result["value"]

# ---------------------------------------------------------------------
# Hilo de procesamiento
# ---------------------------------------------------------------------

class ComparadorThread(threading.Thread):
    def __init__(self, fuente: pd.Series, destino: pd.Series, out_queue: "queue.Queue",
                 cancel_flag: threading.Event, preview_every: int = 50):
        super().__init__(daemon=True)
        self.fuente = fuente.fillna("").astype(str)
        self.destino = destino.fillna("").astype(str)
        self.out_queue = out_queue
        self.cancel_flag = cancel_flag
        self.preview_every = preview_every

    def run(self):
        n = len(self.fuente)
        destino_cache = [(val, normaliza(val)) for val in self.destino.tolist()]
        resultados = []
        t0 = time.time()
        for i, val_src in enumerate(self.fuente.tolist(), start=1):
            if self.cancel_flag.is_set():
                self.out_queue.put(("cancelled", None))
                logger.info("Proceso cancelado por el usuario.")
                return
            best1 = ("", -1.0)
            best2 = ("", -1.0)
            norm_src = normaliza(val_src)
            for orig_dst, norm_dst in destino_cache:
                sc = 100.0 * similitud_compuesta(norm_src, norm_dst)
                if sc > best1[1]:
                    best2 = best1
                    best1 = (orig_dst, sc)
                elif sc > best2[1]:
                    best2 = (orig_dst, sc)
            resultados.append({
                "VALOR_FUENTE": val_src,
                "MEJOR_COINCIDENCIA_1": best1[0],
                "PUNTAJE_1_%": round(best1[1], 2),
                "MEJOR_COINCIDENCIA_2": best2[0],
                "PUNTAJE_2_%": round(best2[1], 2),
            })
            if i % self.preview_every == 0 or i == n:
                elapsed = time.time() - t0
                rate = i / elapsed if elapsed > 0 else 0.0
                remaining = (n - i) / rate if rate > 0 else 0.0
                self.out_queue.put(("progress", {"done": i, "total": n, "eta": remaining}))
        self.out_queue.put(("done", pd.DataFrame(resultados)))

# ---------------------------------------------------------------------
# GUI principal
# ---------------------------------------------------------------------

class App(Tk):
    def __init__(self):
        super().__init__()
        self.title("Comparador de Similitud (Top 2 coincidencias)")
        self.geometry("1200x720")
        self.minsize(1100, 680)

        self.df1: Optional[pd.DataFrame] = None
        self.df2: Optional[pd.DataFrame] = None
        self.path1 = StringVar(value="")
        self.path2 = StringVar(value="")
        self.col1 = StringVar()
        self.col2 = StringVar()
        self.result_df: Optional[pd.DataFrame] = None

        self.worker: Optional[ComparadorThread] = None
        self.queue: "queue.Queue" = queue.Queue()
        self.cancel_flag = threading.Event()

        self._build_ui()
        logger.info("Aplicación iniciada.")

    def _build_ui(self):
        top = Frame(self)
        top.pack(side=TOP, fill=X, padx=10, pady=10)
        Button(top, text="Seleccionar Archivo 1 (.csv/.xlsx/.md)", command=self.sel_file1).pack(side=LEFT, padx=5)
        Label(top, textvariable=self.path1, anchor="w").pack(side=LEFT, padx=5, expand=True, fill=X)
        Button(top, text="Seleccionar Archivo 2 (.csv/.xlsx/.md)", command=self.sel_file2).pack(side=LEFT, padx=5)
        Label(top, textvariable=self.path2, anchor="w").pack(side=LEFT, padx=5, expand=True, fill=X)

        mid = Frame(self)
        mid.pack(side=TOP, fill=X, padx=10, pady=5)
        Label(mid, text="Columna de Archivo 1:", font=("Segoe UI", 9, "bold")).pack(side=LEFT, padx=5)
        self.cb1 = ttk.Combobox(mid, textvariable=self.col1, width=40, state="disabled")
        self.cb1.pack(side=LEFT, padx=5)
        Label(mid, text="Columna de Archivo 2:", font=("Segoe UI", 9, "bold")).pack(side=LEFT, padx=15)
        self.cb2 = ttk.Combobox(mid, textvariable=self.col2, width=40, state="disabled")
        self.cb2.pack(side=LEFT, padx=5)

        act = Frame(self)
        act.pack(side=TOP, fill=X, padx=10, pady=5)
        self.btn_run = Button(act, text="Calcular similitud", command=self.run_task, state="disabled")
        self.btn_run.pack(side=LEFT, padx=5)
        self.btn_cancel = Button(act, text="Cancelar", command=self.cancel_task, state="disabled")
        self.btn_cancel.pack(side=LEFT, padx=5)
        self.btn_save = Button(act, text="Guardar resultado (CSV/XLSX/MD)", command=self.save_result, state="disabled")
        self.btn_save.pack(side=LEFT, padx=5)

        prog = Frame(self)
        prog.pack(side=TOP, fill=X, padx=10, pady=5)
        self.pb = ttk.Progressbar(prog, mode="determinate")
        self.pb.pack(side=LEFT, fill=X, expand=True, padx=5)
        self.eta_lbl = Label(prog, text="ETA: --:--")
        self.eta_lbl.pack(side=RIGHT, padx=5)

        body = Frame(self)
        body.pack(side=TOP, fill="both", expand=True, padx=10, pady=10)
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=1)
        body.grid_rowconfigure(0, weight=3)
        body.grid_rowconfigure(1, weight=2)

        self.frame1 = Frame(body)
        self.frame1.grid(row=0, column=0, sticky=NSEW, padx=5, pady=5)
        Label(self.frame1, text="Vista previa Archivo 1", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.tree1 = None

        self.frame2 = Frame(body)
        self.frame2.grid(row=0, column=1, sticky=NSEW, padx=5, pady=5)
        Label(self.frame2, text="Vista previa Archivo 2", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.tree2 = None

        log_fr = Frame(body)
        log_fr.grid(row=1, column=0, columnspan=2, sticky=NSEW, padx=5, pady=5)
        Label(log_fr, text="Logs", font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.log_txt = Text(log_fr, height=8, wrap="word")
        sb = Scrollbar(log_fr, command=self.log_txt.yview)
        self.log_txt.configure(yscrollcommand=sb.set)
        self.log_txt.pack(side=LEFT, fill="both", expand=True)
        sb.pack(side=RIGHT, fill=Y)

    def _render_df_in_tree(self, container: Frame, df: pd.DataFrame, max_rows: int = 100):
        # Limpia treeview previo
        for w in list(container.pack_slaves())[1:]:  # conserva primer Label (título)
            w.destroy()
        cols = list(df.columns.astype(str))
        tree = ttk.Treeview(container, columns=cols, show="headings")
        for c in cols:
            tree.heading(c, text=c)
            tree.column(c, width=150, stretch=True)
        view_df = df.head(max_rows).fillna("")
        for _, row in view_df.iterrows():
            tree.insert("", END, values=[str(row[c]) for c in cols])
        tree.pack(side=LEFT, fill="both", expand=True)
        sb = Scrollbar(container, command=tree.yview)
        tree.configure(yscrollcommand=sb.set)
        sb.pack(side=RIGHT, fill=Y)
        return tree

    def _update_cols_comboboxes(self):
        if self.df1 is not None:
            cols1 = list(self.df1.columns.astype(str))
            self.cb1["values"] = cols1
            self.cb1["state"] = "readonly"
            if cols1:
                self.cb1.current(0)
        if self.df2 is not None:
            cols2 = list(self.df2.columns.astype(str))
            self.cb2["values"] = cols2
            self.cb2["state"] = "readonly"
            if cols2:
                self.cb2.current(0)
        self.btn_run["state"] = "normal" if (self.df1 is not None and self.df2 is not None) else "disabled"

    def sel_file1(self):
        path = filedialog.askopenfilename(
            title="Seleccionar Archivo 1",
            filetypes=[("Archivos soportados", "*.csv *.xlsx *.md"),
                       ("CSV", "*.csv"), ("Excel", "*.xlsx"), ("Markdown", "*.md")],
        )
        if not path:
            return
        try:
            df = cargar_archivo(path, self)
            self.df1 = df
            self.path1.set(path)
            self.tree1 = self._render_df_in_tree(self.frame1, df)
            self._update_cols_comboboxes()
            self.log(f"Archivo 1 cargado. Filas: {len(df)}, Columnas: {len(df.columns)}.")
        except Exception as e:
            logger.exception("Error al cargar Archivo 1")
            messagebox.showerror("Error", f"No se pudo cargar el archivo 1:\n{e}")

    def sel_file2(self):
        path = filedialog.askopenfilename(
            title="Seleccionar Archivo 2",
            filetypes=[("Archivos soportados", "*.csv *.xlsx *.md"),
                       ("CSV", "*.csv"), ("Excel", "*.xlsx"), ("Markdown", "*.md")],
        )
        if not path:
            return
        try:
            df = cargar_archivo(path, self)
            self.df2 = df
            self.path2.set(path)
            self.tree2 = self._render_df_in_tree(self.frame2, df)
            self._update_cols_comboboxes()
            self.log(f"Archivo 2 cargado. Filas: {len(df)}, Columnas: {len(df.columns)}.")
        except Exception as e:
            logger.exception("Error al cargar Archivo 2")
            messagebox.showerror("Error", f"No se pudo cargar el archivo 2:\n{e}")

    def run_task(self):
        if self.df1 is None or self.df2 is None:
            messagebox.showwarning("Datos", "Debes cargar ambos archivos primero.")
            return
        c1 = self.col1.get()
        c2 = self.col2.get()
        if not c1 or not c2:
            messagebox.showwarning("Columnas", "Selecciona una columna de cada archivo.")
            return
        fuente = self.df1[c1]
        destino = self.df2[c2]
        self.btn_run["state"] = "disabled"
        self.btn_cancel["state"] = "normal"
        self.btn_save["state"] = "disabled"
        self.pb["value"] = 0
        self.eta_lbl["text"] = "ETA: --:--"
        self.cancel_flag.clear()
        self.queue = queue.Queue()
        self.result_df = None
        self.log(f"Iniciando comparación: {len(fuente)} vs {len(destino)} (Top 2).")
        self.worker = ComparadorThread(fuente, destino, self.queue, self.cancel_flag)
        self.worker.start()
        self.after(100, self.check_queue)

    def check_queue(self):
        try:
            while True:
                msg, payload = self.queue.get_nowait()
                if msg == "progress":
                    done = payload["done"]; total = payload["total"]; eta = payload["eta"]
                    pct = int(100 * done / total) if total else 0
                    self.pb["value"] = pct
                    self.eta_lbl["text"] = f"ETA: {self.fmt_eta(eta)}"
                elif msg == "done":
                    self.result_df = payload
                    self.pb["value"] = 100
                    self.eta_lbl["text"] = "ETA: 00:00"
                    self.btn_save["state"] = "normal"
                    self.btn_cancel["state"] = "disabled"
                    self.btn_run["state"] = "normal"
                    self.log("Comparación finalizada. Puedes guardar el resultado.")
                elif msg == "cancelled":
                    self.pb["value"] = 0
                    self.eta_lbl["text"] = "ETA: --:--"
                    self.btn_cancel["state"] = "disabled"
                    self.btn_run["state"] = "normal"
                    self.log("Proceso cancelado por el usuario.")
        except queue.Empty:
            pass
        if self.worker and self.worker.is_alive():
            self.after(150, self.check_queue)

    def cancel_task(self):
        if self.worker and self.worker.is_alive():
            self.cancel_flag.set()
            self.log("Solicitando cancelación...")

    def save_result(self):
        if self.result_df is None:
            messagebox.showwarning("Resultado", "Aún no hay resultados para guardar.")
            return
        path = filedialog.asksaveasfilename(
            title="Guardar resultado",
            defaultextension=".xlsx",
            filetypes=[("Excel", "*.xlsx"), ("CSV", "*.csv"), ("Markdown", "*.md")],
        )
        if not path:
            return
        try:
            ext = Path(path).suffix.lower()
            if ext == ".xlsx":
                with pd.ExcelWriter(path, engine="openpyxl") as xw:
                    self.result_df.to_excel(xw, index=False, sheet_name="coincidencias")
            elif ext == ".csv":
                self.result_df.to_csv(path, index=False, encoding="utf-8")
            elif ext == ".md":
                md = self.dataframe_to_markdown(self.result_df)
                with open(path, "w", encoding="utf-8") as f:
                    f.write(md)
            else:
                raise ValueError("Extensión no soportada. Usa .xlsx, .csv o .md")
            self.log(f"Resultado guardado en: {path}")
            messagebox.showinfo("Guardar", "Archivo guardado correctamente.")
        except Exception as e:
            logger.exception("Error al guardar resultado")
            messagebox.showerror("Error", f"No se pudo guardar el resultado:\n{e}")

    @staticmethod
    def dataframe_to_markdown(df: pd.DataFrame) -> str:
        cols = list(df.columns.astype(str))
        lines = []
        header = "| " + " | ".join(cols) + " |"
        sep = "| " + " | ".join(["---"] * len(cols)) + " |"
        lines.append(header); lines.append(sep)
        for _, row in df.iterrows():
            vals = [str(row[c]) if not pd.isna(row[c]) else "" for c in cols]
            lines.append("| " + " | ".join(vals) + " |")
        return "\n".join(lines)

    @staticmethod
    def fmt_eta(seconds: float) -> str:
        if seconds is None or math.isinf(seconds) or math.isnan(seconds):
            return "--:--"
        seconds = int(max(0, seconds))
        m, s = divmod(seconds, 60)
        return f"{m:02d}:{s:02d}"

    def log(self, msg: str):
        safe = re.sub(r"[A-Za-z0-9]{2,}", lambda m: m.group(0) if len(m.group(0)) < 20 else m.group(0)[:3]+"***", msg)
        logger.info(safe)
        self.log_txt.insert(END, msg + "\n")
        self.log_txt.see(END)

if __name__ == "__main__":
    try:
        app = App()
        app.mainloop()
    except Exception as e:
        logger.exception("Fallo crítico de la aplicación")
        print(f"Error crítico: {e}")
        sys.exit(1)
