#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
CSV → Markdown (GFM) con GUI (Tkinter), streaming y detección automática.

Uso:
  python main.py

Características clave:
- Python 3.11, Windows, solo librerías estándar.
- GUI en español (Tkinter).
- Selección de archivo .csv (hasta ~2 GB) y carpeta de salida.
- Detección automática (codificación, delimitador, quotechar, escapechar, presencia de encabezado, lineterminator).
- Overrides manuales de todos los parámetros.
- Previsualización de primeras N filas (por defecto 100).
- Conversión en streaming a un único .md (GFM), sin metadatos.
- Escapado estricto por celda:
    \ -> \\
    | -> \|
    ` -> \`
    Saltos de línea -> <br> (opción activada por defecto)
    También escapa: *, _, ~, <, >
- Progreso basado en bytes, porcentaje, ETA; cancelación segura.
- Logs en panel y en archivo BASE_YYYYMMDD_HHMMSS.log junto al .md.
- RAM objetivo < 300 MB.
- threading (no multiprocessing). Comunicación con cola/after().

PyInstaller:
  pyinstaller --onefile --noconsole --name CSV_a_Markdown --icon optional.ico main.py
"""

from __future__ import annotations

import csv
import io
import os
import sys
import time
import struct
import threading
import queue
import logging
from pathlib import Path
from itertools import islice
from datetime import datetime

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# --------------------------- Límite seguro de campo CSV -----------------------
# En Windows el C long suele ser de 32 bits. Usar sys.maxsize puede desbordar.
# Calculamos el máximo representable y lo aplicamos de forma segura.
try:
    _MAX_C_LONG = (1 << (8 * struct.calcsize("l") - 1)) - 1
    csv.field_size_limit(_MAX_C_LONG)
except Exception:
    # Fallback conservador (~1 GB)
    try:
        csv.field_size_limit(2**30 - 1)
    except Exception:
        pass

# ----------------------------- Utilidades comunes -----------------------------

ENCODINGS_ORDER = ["utf-8-sig", "utf-8", "cp1252", "latin-1"]
CANDIDATE_DELIMS = [",", ";", "\t", "|"]
CANDIDATE_ESCAPES = [None, "\\"]
CANDIDATE_QUOTES = ['"', "'"]

# Mapea para mostrar "\t" como texto en los combos
VISIBLE_DELIM_TO_VALUE = {",": ",", ";": ";", "\\t": "\t", "|": "|"}
VALUE_TO_VISIBLE_DELIM = {v: k for k, v in VISIBLE_DELIM_TO_VALUE.items()}

# ----------------------------- Logger a la UI ---------------------------------

class TkQueueHandler(logging.Handler):
    """Handler de logging que envía mensajes a una cola para que la GUI los consuma."""
    def __init__(self, q: queue.Queue):
        super().__init__()
        self.q = q

    def emit(self, record: logging.LogRecord):
        try:
            msg = self.format(record)
            self.q.put(("log", msg))
        except Exception:
            pass


# ----------------------------- Detector CSV -----------------------------------

class DetectorCSV:
    """
    Detecta codificación, delimitador, quotechar, escapechar, si hay encabezado y lineterminator.
    Sin librerías externas. Usa csv.Sniffer + heurísticas de respaldo.
    """

    def __init__(self, path: Path, sample_mb: int = 5, logger: logging.Logger | None = None):
        self.path = Path(path)
        self.sample_mb = max(1, int(sample_mb))
        self.logger = logger or logging.getLogger(__name__)

    @staticmethod
    def _detect_lineterminator(sample_bytes: bytes) -> str:
        crlf = sample_bytes.count(b"\r\n")
        lf = sample_bytes.count(b"\n") - crlf
        cr = sample_bytes.count(b"\r") - crlf
        if crlf >= lf and crlf >= cr and crlf > 0:
            return "\\r\\n"
        if lf >= cr and lf > 0:
            return "\\n"
        if cr > 0:
            return "\\r"
        return "\\r\\n"

    def _try_decode(self, sample_bytes: bytes) -> tuple[str, str]:
        last_error = None
        for enc in ENCODINGS_ORDER:
            try:
                s = sample_bytes.decode(enc, errors="strict")
                return enc, s
            except UnicodeDecodeError as e:
                last_error = e
        if last_error:
            raise last_error
        raise UnicodeDecodeError("unknown", b"", 0, 1, "No se pudo decodificar")

    @staticmethod
    def _sniff_dialect(sample_str: str) -> tuple[csv.Dialect | None, bool | None]:
        sniffer = csv.Sniffer()
        try:
            dialect = sniffer.sniff(sample_str, delimiters=",;\t|")
        except Exception:
            dialect = None
        try:
            has_header = sniffer.has_header(sample_str)
        except Exception:
            has_header = None
        return dialect, has_header

    def _fallback_dialect(self, sample_str: str) -> tuple[str, str, str | None, bool]:
        lines = [ln for ln in sample_str.splitlines() if ln.strip()][:50]
        best = None  # (score, delimiter, escapechar, columns_count)
        for delim in CANDIDATE_DELIMS:
            for esc in CANDIDATE_ESCAPES:
                try:
                    reader = csv.reader(lines, delimiter=delim, quotechar='"', escapechar=esc)
                    cols = []
                    for i, row in enumerate(reader):
                        cols.append(len(row))
                        if i > 20:
                            break
                    if not cols:
                        continue
                    mode_cols = max(set(cols), key=cols.count)
                    consistency = cols.count(mode_cols) / len(cols)
                    score = (consistency, mode_cols)
                    if best is None or score > best[0]:
                        best = (score, delim, esc, mode_cols)
                except Exception:
                    continue

        if best is None:
            delim, esc, mode_cols = ",", None, 1
        else:
            _, delim, esc, mode_cols = best

        try:
            reader = csv.reader([lines[0]], delimiter=delim, quotechar='"', escapechar=esc)
            first = next(reader, [])
            nums = 0
            for c in first:
                try:
                    float(c)
                    nums += 1
                except Exception:
                    pass
            has_header_guess = nums == 0 and len(first) == mode_cols
        except Exception:
            has_header_guess = False

        return delim, '"', esc, has_header_guess

    def detect(self) -> dict:
        sample_size = self.sample_mb * 1024 * 1024
        with open(self.path, "rb") as f:
            sample_bytes = f.read(sample_size)

        lineterminator = self._detect_lineterminator(sample_bytes)
        encoding, sample_str = self._try_decode(sample_bytes)
        dialect, has_header = self._sniff_dialect(sample_str)

        if dialect is None:
            delim, quotechar, escapechar, has_header_guess = self._fallback_dialect(sample_str)
        else:
            delim = getattr(dialect, "delimiter", ",")
            quotechar = getattr(dialect, "quotechar", '"') or '"'
            escapechar = getattr(dialect, "escapechar", None)
            has_header_guess = has_header if has_header is not None else False

        return {
            "encoding": encoding,
            "delimiter": delim,
            "quotechar": quotechar,
            "escapechar": escapechar,
            "has_header": bool(has_header_guess),
            "lineterminator": lineterminator
        }


# --------------------------- Convertidor a Markdown ---------------------------

def escape_cell_gfm(s: str, replace_newlines_with_br: bool = True) -> str:
    """
    Escapado estricto por celda para Markdown GFM, según los requisitos.
    Orden importante para evitar doble escape.
    """
    if s is None:
        s = ""
    if not isinstance(s, str):
        s = str(s)

    if replace_newlines_with_br:
        s = s.replace("\r\n", "<br>").replace("\n", "<br>").replace("\r", "<br>")

    s = s.replace("\\", "\\\\")
    s = s.replace("|", "\\|")
    s = s.replace("`", "\\`")

    for ch in ["*", "_", "~", "<", ">"]:
        s = s.replace(ch, "\\" + ch)

    return s


class ConvertidorMarkdown:
    """
    Convierte CSV → Markdown (GFM) en streaming, con progreso por bytes, cancelación y logs.
    """

    def __init__(self,
                 input_path: Path,
                 output_dir: Path,
                 encoding: str,
                 delimiter: str,
                 quotechar: str,
                 escapechar: str | None,
                 has_header: bool,
                 replace_newlines_with_br: bool,
                 logger: logging.Logger,
                 cancel_event: threading.Event,
                 progress_cb):
        self.input_path = Path(input_path)
        self.output_dir = Path(output_dir)
        self.encoding = encoding
        self.delimiter = delimiter
        self.quotechar = quotechar
        self.escapechar = escapechar
        self.has_header = has_header
        self.replace_newlines_with_br = replace_newlines_with_br
        self.logger = logger
        self.cancel_event = cancel_event
        self.progress_cb = progress_cb  # progress_cb(bytes_done, total_bytes, eta)

    def _build_output_names(self) -> tuple[Path, Path, Path]:
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = self.input_path.stem + "_" + stamp
        md_final = self.output_dir / f"{base}.md"
        md_tmp = self.output_dir / f"{base}.tmp"
        log_file = self.output_dir / f"{base}.log"
        return md_final, md_tmp, log_file

    @staticmethod
    def _make_dialect(delimiter: str, quotechar: str, escapechar: str | None):
        """
        Crear un 'objeto dialecto' sin tocar csv.excel global.
        _csv acepta cualquier objeto con los atributos necesarios.
        """
        class _D:
            pass
        d = _D()
        d.delimiter = delimiter
        d.quotechar = quotechar
        d.escapechar = escapechar
        d.doublequote = True if not escapechar else False
        d.lineterminator = "\n"
        d.skipinitialspace = False
        d.quoting = csv.QUOTE_MINIMAL
        return d

    def convert(self) -> Path:
        total_bytes = self.input_path.stat().st_size
        md_final, md_tmp, _ = self._build_output_names()

        with open(self.input_path, "rb", buffering=io.DEFAULT_BUFFER_SIZE) as fbin:
            ftxt = io.TextIOWrapper(fbin, encoding=self.encoding, errors="strict", newline=None)
            dialect_obj = self._make_dialect(self.delimiter, self.quotechar, self.escapechar)
            reader = csv.reader(ftxt, dialect=dialect_obj)

            with open(md_tmp, "w", encoding="utf-8", newline="\n") as fout:
                last_time = time.time()
                speed_window = []

                def report_progress():
                    done = fbin.tell()
                    now = time.time()
                    speed_window.append((now, done))
                    if len(speed_window) > 10:
                        speed_window.pop(0)
                    if len(speed_window) >= 2:
                        dt = speed_window[-1][0] - speed_window[0][0]
                        db = speed_window[-1][1] - speed_window[0][1]
                        speed = db / dt if dt > 0 else 0.0
                        remaining = max(0, total_bytes - done)
                        eta = remaining / speed if speed > 0 else None
                    else:
                        eta = None
                    self.progress_cb(done, total_bytes, eta)

                try:
                    first_row = next(reader)
                except StopIteration:
                    fout.write("| \n| --- \n")
                    report_progress()
                    os.replace(md_tmp, md_final)
                    return md_final

                if self.cancel_event.is_set():
                    raise RuntimeError("Cancelado por el usuario")

                if self.has_header:
                    headers = [escape_cell_gfm(c, self.replace_newlines_with_br) for c in first_row]
                    num_cols = len(headers)
                    fout.write("| " + " | ".join(headers) + " |\n")
                    fout.write("| " + " | ".join(["---"] * num_cols) + " |\n")
                else:
                    num_cols = len(first_row)
                    headers = [f"col_{i+1}" for i in range(num_cols)]
                    fout.write("| " + " | ".join(headers) + " |\n")
                    fout.write("| " + " | ".join(["---"] * num_cols) + " |\n")
                    row_cells = [escape_cell_gfm(c, self.replace_newlines_with_br) for c in first_row]
                    if len(row_cells) < num_cols:
                        row_cells += [""] * (num_cols - len(row_cells))
                    elif len(row_cells) > num_cols:
                        row_cells = row_cells[:num_cols]
                    fout.write("| " + " | ".join(row_cells) + " |\n")

                report_progress()

                for row in reader:
                    if self.cancel_event.is_set():
                        raise RuntimeError("Cancelado por el usuario")
                    row_cells = [escape_cell_gfm(c, self.replace_newlines_with_br) for c in row]
                    if len(row_cells) < num_cols:
                        row_cells += [""] * (num_cols - len(row_cells))
                    elif len(row_cells) > num_cols:
                        row_cells = row_cells[:num_cols]
                    fout.write("| " + " | ".join(row_cells) + " |\n")

                    now = time.time()
                    if now - last_time >= 0.25:
                        report_progress()
                        last_time = now

                report_progress()

        os.replace(md_tmp, md_final)
        return md_final


# --------------------------------- GUI (Tk) -----------------------------------

class GUIApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("CSV a Markdown (GFM)")
        self.root.geometry("1080x720")

        self.csv_path = tk.StringVar()
        self.out_dir = tk.StringVar()
        self.sample_mb = tk.IntVar(value=5)
        self.preview_rows = tk.IntVar(value=100)
        self.replace_br = tk.BooleanVar(value=True)
        self.has_header_var = tk.BooleanVar(value=True)
        self.log_level_var = tk.StringVar(value="INFO")

        # Detectados (solo lectura)
        self.detect_encoding = tk.StringVar()
        self.detect_delim = tk.StringVar()
        self.detect_quote = tk.StringVar()
        self.detect_escape = tk.StringVar()
        self.detect_header = tk.StringVar()
        self.detect_lf = tk.StringVar()

        # Overrides (combos)
        self.override_encoding = tk.StringVar()
        self.override_delim = tk.StringVar()
        self.override_quote = tk.StringVar()
        self.override_escape = tk.StringVar()
        self.override_has_header = tk.BooleanVar(value=True)

        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_text = tk.StringVar(value="Progreso: 0.00% — ETA: …")
        self.is_running = False
        self.cancel_event = threading.Event()
        self.msg_queue = queue.Queue()

        self._logger = logging.getLogger("CSV2MD")
        self._logger.setLevel(logging.INFO)
        self.ui_handler = TkQueueHandler(self.msg_queue)
        fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
        self.ui_handler.setFormatter(fmt)
        self._logger.addHandler(self.ui_handler)
        self.file_handler = None  # se crea al iniciar conversión

        self._build_ui()
        self._poll_queue()

    # ---------- UI builders ----------

    def _build_ui(self):
        pad = dict(padx=8, pady=4)

        top = ttk.Frame(self.root)
        top.pack(fill="x", **pad)

        ttk.Label(top, text="Archivo CSV:").grid(row=0, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.csv_path, width=90).grid(row=0, column=1, sticky="we")
        ttk.Button(top, text="Seleccionar CSV", command=self._select_csv).grid(row=0, column=2)

        ttk.Label(top, text="Carpeta de salida:").grid(row=1, column=0, sticky="w")
        ttk.Entry(top, textvariable=self.out_dir, width=90).grid(row=1, column=1, sticky="we")
        ttk.Button(top, text="Elegir carpeta", command=self._select_dir).grid(row=1, column=2)

        # Opciones de detección / overrides
        opts = ttk.LabelFrame(self.root, text="Detección y Overrides")
        opts.pack(fill="x", **pad)

        # Detecciones (solo lectura)
        det_grid = ttk.Frame(opts)
        det_grid.pack(fill="x", **pad)

        r = 0
        ttk.Label(det_grid, text="Codificación detectada:").grid(row=r, column=0, sticky="w")
        ttk.Entry(det_grid, textvariable=self.detect_encoding, width=20, state="readonly").grid(row=r, column=1, sticky="w")
        ttk.Label(det_grid, text="Delimitador:").grid(row=r, column=2, sticky="w")
        ttk.Entry(det_grid, textvariable=self.detect_delim, width=10, state="readonly").grid(row=r, column=3, sticky="w")
        ttk.Label(det_grid, text="Quotechar:").grid(row=r, column=4, sticky="w")
        ttk.Entry(det_grid, textvariable=self.detect_quote, width=10, state="readonly").grid(row=r, column=5, sticky="w")
        ttk.Label(det_grid, text="Escapechar:").grid(row=r, column=6, sticky="w")
        ttk.Entry(det_grid, textvariable=self.detect_escape, width=10, state="readonly").grid(row=r, column=7, sticky="w")
        r += 1
        ttk.Label(det_grid, text="Encabezado:").grid(row=r, column=0, sticky="w")
        ttk.Entry(det_grid, textvariable=self.detect_header, width=10, state="readonly").grid(row=r, column=1, sticky="w")
        ttk.Label(det_grid, text="Lineterminator:").grid(row=r, column=2, sticky="w")
        ttk.Entry(det_grid, textvariable=self.detect_lf, width=10, state="readonly").grid(row=r, column=3, sticky="w")

        # Overrides
        ov = ttk.Frame(opts)
        ov.pack(fill="x", **pad)

        r = 0
        ttk.Label(ov, text="Codificación:").grid(row=r, column=0, sticky="w")
        enc_combo = ttk.Combobox(ov, values=ENCODINGS_ORDER, textvariable=self.override_encoding, width=18, state="readonly")
        enc_combo.grid(row=r, column=1, sticky="w")

        ttk.Label(ov, text="Delimitador:").grid(row=r, column=2, sticky="w")
        delim_combo = ttk.Combobox(ov, values=[",", ";", "\\t", "|"], textvariable=self.override_delim, width=6, state="readonly")
        delim_combo.grid(row=r, column=3, sticky="w")

        ttk.Label(ov, text="Quotechar:").grid(row=r, column=4, sticky="w")
        quote_combo = ttk.Combobox(ov, values=CANDIDATE_QUOTES, textvariable=self.override_quote, width=6, state="readonly")
        quote_combo.grid(row=r, column=5, sticky="w")

        ttk.Label(ov, text="Escapechar:").grid(row=r, column=6, sticky="w")
        esc_combo = ttk.Combobox(ov, values=["", "\\"], textvariable=self.override_escape, width=6, state="readonly")
        esc_combo.grid(row=r, column=7, sticky="w")

        ttk.Checkbutton(ov, text="El CSV tiene encabezado", variable=self.override_has_header).grid(row=r, column=8, padx=10, sticky="w")

        # Parámetros adicionales
        extra = ttk.LabelFrame(self.root, text="Parámetros")
        extra.pack(fill="x", **pad)

        ttk.Label(extra, text="Filas para previsualizar:").grid(row=0, column=0, sticky="w")
        ttk.Spinbox(extra, from_=1, to=1000, textvariable=self.preview_rows, width=6).grid(row=0, column=1, sticky="w")

        ttk.Label(extra, text="Tamaño de muestra (MB) para detección:").grid(row=0, column=2, sticky="w")
        ttk.Spinbox(extra, from_=1, to=64, textvariable=self.sample_mb, width=6).grid(row=0, column=3, sticky="w")

        ttk.Checkbutton(extra, text="Reemplazar saltos por <br>", variable=self.replace_br).grid(row=0, column=4, sticky="w", padx=10)

        ttk.Label(extra, text="Nivel de log:").grid(row=0, column=5, sticky="e")
        level_combo = ttk.Combobox(extra, values=["INFO", "DEBUG"], textvariable=self.log_level_var, width=8, state="readonly")
        level_combo.grid(row=0, column=6, sticky="w")

        # Botones acción
        actions = ttk.Frame(self.root)
        actions.pack(fill="x", **pad)
        ttk.Button(actions, text="Previsualizar", command=self._preview).pack(side="left")
        ttk.Button(actions, text="Iniciar", command=self._start).pack(side="left", padx=8)
        self.btn_cancel = ttk.Button(actions, text="Cancelar", command=self._cancel, state="disabled")
        self.btn_cancel.pack(side="left", padx=8)

        # Progreso
        prog = ttk.Frame(self.root)
        prog.pack(fill="x", **pad)
        self.pb = ttk.Progressbar(prog, variable=self.progress_var, maximum=100.0)
        self.pb.pack(fill="x")
        ttk.Label(prog, textvariable=self.progress_text).pack(anchor="w")

        # Previsualización tabla
        prev = ttk.LabelFrame(self.root, text="Previsualización")
        prev.pack(fill="both", expand=True, **pad)

        self.tree = ttk.Treeview(prev, columns=(), show="headings")
        self.tree.pack(side="left", fill="both", expand=True)
        vsb = ttk.Scrollbar(prev, orient="vertical", command=self.tree.yview)
        hsb = ttk.Scrollbar(prev, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscroll=vsb.set, xscroll=hsb.set)
        vsb.pack(side="right", fill="y")
        hsb.pack(side="bottom", fill="x")

        # Logs
        logfrm = ttk.LabelFrame(self.root, text="Logs")
        logfrm.pack(fill="both", expand=True, **pad)
        self.txt_logs = tk.Text(logfrm, height=10, wrap="word")
        self.txt_logs.pack(side="left", fill="both", expand=True)
        logsb = ttk.Scrollbar(logfrm, orient="vertical", command=self.txt_logs.yview)
        self.txt_logs.configure(yscrollcommand=logsb.set)
        logsb.pack(side="right", fill="y")

    # ---------- Interacción ----------

    def _select_csv(self):
        path = filedialog.askopenfilename(
            title="Seleccionar CSV",
            filetypes=[("Archivos CSV", "*.csv")],
        )
        if path:
            self.csv_path.set(path)
            try:
                self._run_detection()
            except Exception as e:
                messagebox.showwarning("Detección", f"No fue posible detectar automáticamente.\n{e}")

    def _select_dir(self):
        d = filedialog.askdirectory(title="Seleccionar carpeta de salida")
        if d:
            self.out_dir.set(d)

    def _apply_detect_to_overrides(self, det: dict):
        self.detect_encoding.set(det["encoding"])
        self.detect_delim.set(VALUE_TO_VISIBLE_DELIM.get(det["delimiter"], det["delimiter"]))
        self.detect_quote.set(det["quotechar"])
        self.detect_escape.set("" if (det["escapechar"] in (None, "")) else det["escapechar"])
        self.detect_header.set("Sí" if det["has_header"] else "No")
        self.detect_lf.set(det["lineterminator"])

        self.override_encoding.set(det["encoding"])
        self.override_delim.set(VALUE_TO_VISIBLE_DELIM.get(det["delimiter"], det["delimiter"]))
        self.override_quote.set(det["quotechar"])
        self.override_escape.set("" if (det["escapechar"] in (None, "")) else det["escapechar"])
        self.override_has_header.set(bool(det["has_header"]))

    def _run_detection(self):
        path = self.csv_path.get()
        if not path:
            return
        det = DetectorCSV(Path(path), sample_mb=self.sample_mb.get(), logger=self._logger).detect()
        self._apply_detect_to_overrides(det)
        self._logger.info(f"Detección: {det}")

    def _preview(self):
        if not self.csv_path.get():
            messagebox.showwarning("Previsualización", "Selecciona primero un archivo CSV.")
            return

        if not self.detect_encoding.get():
            try:
                self._run_detection()
            except Exception as e:
                messagebox.showwarning("Detección", f"No fue posible detectar automáticamente.\n{e}")

        enc = self.override_encoding.get() or self.detect_encoding.get()
        delim_visible = self.override_delim.get() or self.detect_delim.get()
        delim = VISIBLE_DELIM_TO_VALUE.get(delim_visible, ",")
        quote = self.override_quote.get() or '"'
        esc = self.override_escape.get() or None
        has_header = self.override_has_header.get()

        rows_to_show = max(1, int(self.preview_rows.get()))

        try:
            with open(self.csv_path.get(), "rb") as fbin:
                ftxt = io.TextIOWrapper(fbin, encoding=enc, errors="strict", newline=None)
                dialect_obj = ConvertidorMarkdown._make_dialect(delim, quote, esc)
                reader = csv.reader(ftxt, dialect=dialect_obj)

                first = next(reader, None)
                if first is None:
                    messagebox.showinfo("Previsualización", "El CSV está vacío.")
                    return

                if has_header:
                    headers = first
                else:
                    headers = [f"col_{i+1}" for i in range(len(first))]

                self.tree.delete(*self.tree.get_children())
                for col in self.tree["columns"]:
                    self.tree.heading(col, text="")
                    self.tree.column(col, width=100)

                self.tree["columns"] = [str(i) for i in range(len(headers))]
                for i, h in enumerate(headers):
                    self.tree.heading(str(i), text=str(h))
                    self.tree.column(str(i), width=max(80, min(300, len(str(h)) * 8)))

                count = 0
                if not has_header:
                    self.tree.insert("", "end", values=first)
                    count += 1

                for row in islice(reader, rows_to_show - count):
                    if len(row) < len(headers):
                        row = row + [""] * (len(headers) - len(row))
                    elif len(row) > len(headers):
                        row = row[:len(headers)]
                    self.tree.insert("", "end", values=row)

                self._logger.info(f"Previsualización: {rows_to_show} filas mostradas.")
        except UnicodeDecodeError as e:
            messagebox.showerror("Previsualización", f"Error de decodificación: {e}")
        except csv.Error as e:
            messagebox.showerror("Previsualización", f"Error CSV: {e}")
        except OSError as e:
            messagebox.showerror("Previsualización", f"Error de archivo: {e}")

    def _start(self):
        if self.is_running:
            return
        if not self.csv_path.get():
            messagebox.showwarning("Ejecución", "Selecciona primero un archivo CSV.")
            return
        if not self.out_dir.get():
            messagebox.showwarning("Ejecución", "Selecciona una carpeta de salida.")
            return

        lvl = logging.DEBUG if self.log_level_var.get() == "DEBUG" else logging.INFO
        self._logger.setLevel(lvl)

        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = Path(self.csv_path.get()).stem + "_" + stamp
        log_file = Path(self.out_dir.get()) / f"{base}.log"
        self.file_handler = logging.FileHandler(log_file, encoding="utf-8")
        self.file_handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
        self.file_handler.setLevel(lvl)
        self._logger.addHandler(self.file_handler)

        self._logger.info("Inicio de conversión")
        self._logger.info(f"CSV: {self.csv_path.get()}")
        self._logger.info(f"Salida: {self.out_dir.get()}")

        enc = self.override_encoding.get() or self.detect_encoding.get() or "utf-8"
        delim_visible = self.override_delim.get() or self.detect_delim.get() or ","
        delim = VISIBLE_DELIM_TO_VALUE.get(delim_visible, ",")
        quote = self.override_quote.get() or self.detect_quote.get() or '"'
        esc = self.override_escape.get() or (self.detect_escape.get() or None)
        if esc == "":
            esc = None
        has_header = self.override_has_header.get()
        replace_br = self.replace_br.get()

        self.is_running = True
        self.cancel_event.clear()
        self._set_controls_state(disabled=True)
        self.btn_cancel.config(state="normal")
        self.progress_var.set(0.0)
        self.progress_text.set("Progreso: 0.00% — ETA: …")

        args = (Path(self.csv_path.get()), Path(self.out_dir.get()), enc, delim, quote, esc, has_header, replace_br)
        worker = threading.Thread(target=self._worker_convert, args=args, daemon=True)
        worker.start()

    def _set_controls_state(self, disabled: bool):
        state = "disabled" if disabled else "normal"
        def toggle(container):
            for child in container.winfo_children():
                try:
                    if child is self.btn_cancel:
                        continue
                    if isinstance(child, (ttk.Entry, ttk.Combobox, ttk.Button, ttk.Checkbutton, ttk.Spinbox)):
                        child.config(state=state)
                except Exception:
                    pass
                toggle(child)
        toggle(self.root)

    def _cancel(self):
        if not self.is_running:
            return
        self.cancel_event.set()
        self._logger.info("Solicitud de cancelación recibida.")

    # ---------- Worker y progreso ----------

    def _worker_convert(self, input_path: Path, out_dir: Path, enc: str, delim: str, quote: str,
                        esc: str | None, has_header: bool, replace_br: bool):
        try:
            conv = ConvertidorMarkdown(
                input_path=input_path,
                output_dir=out_dir,
                encoding=enc,
                delimiter=delim,
                quotechar=quote,
                escapechar=esc,
                has_header=has_header,
                replace_newlines_with_br=replace_br,
                logger=self._logger,
                cancel_event=self.cancel_event,
                progress_cb=self._on_progress
            )
            md_path = conv.convert()
            self.msg_queue.put(("done", str(md_path)))
        except RuntimeError as e:
            # Cancelación: eliminar .tmp si quedó
            try:
                for p in Path(out_dir).glob(f"{Path(input_path).stem}_*.tmp"):
                    try:
                        p.unlink()
                    except Exception:
                        pass
            except Exception:
                pass
            self.msg_queue.put(("error", f"Proceso cancelado: {e}"))
        except UnicodeDecodeError as e:
            self.msg_queue.put(("error", f"Error de codificación: {e}"))
        except csv.Error as e:
            self.msg_queue.put(("error", f"Error CSV: {e}"))
        except OSError as e:
            self.msg_queue.put(("error", f"Error de archivo: {e}"))
        except Exception as e:
            # En error inesperado, intentar limpiar .tmp
            try:
                for p in Path(out_dir).glob(f"{Path(input_path).stem}_*.tmp"):
                    try:
                        p.unlink()
                    except Exception:
                        pass
            except Exception:
                pass
            self.msg_queue.put(("error", f"Error inesperado: {e}"))

    def _on_progress(self, done_bytes: int, total_bytes: int, eta_seconds: float | None):
        self.msg_queue.put(("progress", (done_bytes, total_bytes, eta_seconds)))

    def _poll_queue(self):
        try:
            while True:
                kind, payload = self.msg_queue.get_nowait()
                if kind == "log":
                    self.txt_logs.insert("end", payload + "\n")
                    self.txt_logs.see("end")
                elif kind == "progress":
                    done, total, eta = payload
                    pct = (done / total * 100.0) if total > 0 else 0.0
                    self.progress_var.set(pct)
                    eta_txt = self._fmt_eta(eta) if eta is not None else "…"
                    self.progress_text.set(f"Progreso: {pct:0.2f}% — ETA: {eta_txt}")
                elif kind == "done":
                    self._logger.info(f"Conversión finalizada: {payload}")
                    messagebox.showinfo("Éxito", f"Archivo generado:\n{payload}")
                    self._finish()
                elif kind == "error":
                    self._logger.error(payload)
                    messagebox.showerror("Error", payload)
                    self._finish()
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _fmt_eta(self, eta: float) -> str:
        if eta is None or eta <= 0:
            return "…"
        secs = int(eta)
        h = secs // 3600
        m = (secs % 3600) // 60
        s = secs % 60
        if h > 0:
            return f"{h}h {m}m {s}s"
        if m > 0:
            return f"{m}m {s}s"
        return f"{s}s"

    def _finish(self):
        self.is_running = False
        self.btn_cancel.config(state="disabled")
        self._set_controls_state(disabled=False)
        if self.file_handler:
            try:
                self._logger.removeHandler(self.file_handler)
                self.file_handler.close()
            except Exception:
                pass
            self.file_handler = None


# --------------------------------- Main ---------------------------------------

def main():
    root = tk.Tk()
    app = GUIApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
