"""
AS400QueryUI (single-file)
Aplicación Tkinter para ejecutar consultas SQL contra IBM i (AS/400, DB2 for i)
con exportación CSV, progreso, cancelación y logging con rotación.

▶ Este script SUPONE que existe junto a él un archivo `conexion_as400*.py`
  que contiene el MÉTODO de conexión. Se importa y usa TAL CUAL, sin cambiar
  su firma ni su flujo. El cargador detecta si ese módulo usa pyodbc o ibm_db
  y opera con la misma librería. 

Requisitos clave (resumen):
- Editor SQL + botón "Cargar .sql"
- Probar conexión / Ejecutar / Cancelar / Cancelar dura / Limpiar / Exportar / Salir
- Límite por defecto 20 000 (inyecta FETCH FIRST N ROWS ONLY si no hay limitador)
- Tamaño de lote 5 000, timeout 300 s (ambos configurables)
- CSV UTF-8 con BOM (on/off), delimitador , o ;, EOL \r\n
- Logs con rotación (5MB, 3 copias) en la carpeta del exe/script o fallback a
  %LOCALAPPDATA%/AS400QueryUI/logs. Se incluye: usuario, host, driver, duración,
  filas, ruta CSV, primeros ~2KB del SQL + SHA-256 del SQL completo, tracebacks,
  e indicador INCOMPLETO si hubo cancelación.
- Preferencias persistidas en %APPDATA%/AS400QueryUI/config.json
- Empaquetable luego con PyInstaller/Nuitka si se desea (no requerido para VS Code)

Compatibilidad: Windows 10/11 x64. UI: Tkinter/ttk.
"""
from __future__ import annotations

import contextlib
import csv
import getpass
import hashlib
import importlib.util
import json
import logging
import os
import re
import sys
import threading
import time
import tkinter as tk
from dataclasses import dataclass
from logging.handlers import RotatingFileHandler
from tkinter import filedialog, messagebox, ttk
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

# ============================ Constantes ============================
APP_NAME = "AS400QueryUI"
DEFAULT_LIMIT = 20_000
DEFAULT_BATCH = 5_000
DEFAULT_TIMEOUT = 300
CONFIG_DIRNAME = APP_NAME

# ============================ Utilidades generales ============================

def get_main_path() -> str:
    """Devuelve la ruta del binario congelado o el archivo .py actual."""
    return getattr(sys, "frozen", False) and sys.executable or __file__


# ============================ Logging con rotación ============================
class CtxLogger(logging.LoggerAdapter):
    def process(self, msg, kwargs):
        extra = kwargs.setdefault("extra", {})
        extra.setdefault("user", getpass.getuser())
        extra.setdefault("host", os.environ.get("COMPUTERNAME", "?"))
        return msg, kwargs


def _candidate_log_dirs() -> Tuple[str, ...]:
    exe_dir = os.path.dirname(get_main_path())
    local_appdata = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
    return (
        os.path.join(exe_dir, "logs"),
        os.path.join(local_appdata, APP_NAME, "logs"),
    )


def get_logger(app_name: str) -> logging.Logger:
    logger = logging.getLogger(app_name)
    if logger.handlers:
        return logger
    logger.setLevel(logging.INFO)

    for d in _candidate_log_dirs():
        try:
            os.makedirs(d, exist_ok=True)
            log_path = os.path.join(d, f"{app_name}.log")
            handler = RotatingFileHandler(log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
            fmt = logging.Formatter(
                fmt=("%(asctime)s | %(levelname)s | user=%(user)s host=%(host)s | msg=%(message)s"),
                datefmt="%Y-%m-%d %H:%M:%S",
            )
            handler.setFormatter(fmt)
            logger.addHandler(handler)
            break
        except Exception:
            continue
    return CtxLogger(logger, {})


LOGGER = get_logger(APP_NAME)

# ============================ Configuración persistente ============================
class AppConfig:
    """Gestiona %APPDATA%/AS400QueryUI/config.json"""

    def __init__(self) -> None:
        self.data: Dict[str, Any] = {
            "last_dir": "",
            "delimiter": ",",
            "limit": DEFAULT_LIMIT,
            "batch_size": DEFAULT_BATCH,
            "timeout": DEFAULT_TIMEOUT,
            "bom": True,
            "select_only": True,
        }

    @property
    def path(self) -> str:
        base = os.environ.get("APPDATA") or os.path.expanduser("~")
        cfg_dir = os.path.join(base, CONFIG_DIRNAME)
        os.makedirs(cfg_dir, exist_ok=True)
        return os.path.join(cfg_dir, "config.json")

    def load(self) -> None:
        try:
            if os.path.exists(self.path):
                with open(self.path, "r", encoding="utf-8") as f:
                    self.data.update(json.load(f))
        except Exception:
            pass

    def save(self) -> None:
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)


# ============================ Políticas/Helpers SQL ============================
class SqlPolicyError(ValueError):
    pass


def _strip_comments(sql: str) -> str:
    s = re.sub(r"/\*.*?\*/", " ", sql, flags=re.DOTALL)
    s = re.sub(r"--.*?$", " ", s, flags=re.MULTILINE)
    return s


def ensure_select_only(sql: str) -> None:
    s = _strip_comments(sql).strip().upper()
    if not (s.startswith("SELECT ") or s.startswith("WITH ")):
        raise SqlPolicyError("La consulta debe iniciar con SELECT o WITH.")
    forbidden = r"\b(INSERT|UPDATE|DELETE|MERGE|CREATE|ALTER|DROP|TRUNCATE|RENAME|GRANT|REVOKE|CALL|BEGIN|END)\b"
    if re.search(forbidden, s):
        raise SqlPolicyError("Política activa: solo SELECT. Se detectó posible DML/DDL.")


def maybe_inject_fetch_first(sql: str, n: int) -> str:
    s_wo = _strip_comments(sql)
    if re.search(r"\bFETCH\s+FIRST\b", s_wo, flags=re.IGNORECASE) or re.search(r"\bLIMIT\b", s_wo, flags=re.IGNORECASE):
        return sql
    # Conservar punto y coma final si existe
    m = re.search(r";\s*$", sql)
    suffix = ";" if m else ""
    body = sql[: m.start()] if m else sql
    return f"{body}\nFETCH FIRST {int(n)} ROWS ONLY{suffix}"


# ============================ CSV streaming ============================
@dataclass
class CsvWriterOptions:
    path: str
    delimiter: str = ","
    bom: bool = True


class CsvStreamWriter:
    def __init__(self, options: CsvWriterOptions):
        self.options = options
        self._f = None
        self._writer = None

    def __enter__(self) -> "CsvStreamWriter":
        enc = "utf-8-sig" if self.options.bom else "utf-8"
        self._f = open(self.options.path, "w", encoding=enc, newline="\r\n")
        self._writer = csv.writer(self._f, delimiter=self.options.delimiter, quoting=csv.QUOTE_MINIMAL)
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if self._f:
            self._f.flush()
            self._f.close()

    def write_header(self, columns: Sequence[str]) -> None:
        self._writer.writerow(list(columns))
        self._f.flush()

    def write_rows(self, rows: Iterable[Sequence[object]]) -> None:
        for row in rows:
            self._writer.writerow([self._to_str(v) for v in row])
        self._f.flush()

    @staticmethod
    def _to_str(v: object) -> str:
        from decimal import Decimal
        if v is None or v == "":
            return "0.0"
        if isinstance(v, Decimal):
            return format(v, "f")
        return str(v)


# ============================ Capa de conexión (loader del adjunto) ============================
@dataclass
class DriverInfo:
    library: str  # "pyodbc" o "ibm_db"
    driver_string: str  # pista de DRIVER/DSN si está en el adjunto


class _ConnHandle:
    def __init__(self, library: str, raw_conn: Any, driver_name: str):
        self.library = library
        self._raw_conn = raw_conn
        self.driver_name = driver_name

    def execute(self, sql: str) -> Any:
        if self.library == "pyodbc":
            cur = self._raw_conn.cursor()
            cur.execute(sql)
            return cur
        else:
            import ibm_db

            return ibm_db.exec_immediate(self._raw_conn, sql)

    def describe_columns(self, stmt: Any) -> List[str]:
        if self.library == "pyodbc":
            return [d[0] for d in stmt.description]
        else:
            import ibm_db

            cols: List[str] = []
            n = ibm_db.num_fields(stmt)
            for i in range(n):
                cols.append(ibm_db.field_name(stmt, i))
            return cols

    def fetchmany(self, stmt: Any, size: int) -> List[Sequence[Any]]:
        if self.library == "pyodbc":
            rows = stmt.fetchmany(size)
            return [tuple(r) for r in rows]
        else:
            import ibm_db

            out: List[Sequence[Any]] = []
            for _ in range(size):
                row = ibm_db.fetch_tuple(stmt)
                if row is None:
                    break
                out.append(row)
            return out

    def cancel(self, stmt: Any) -> bool:
        if self.library == "pyodbc":
            with contextlib.suppress(Exception):
                stmt.cancel()
                return True
            return False
        else:
            import ibm_db

            try:
                return ibm_db.cancel(stmt)
            except Exception:
                return False

    def close_statement(self, stmt: Any) -> None:
        if self.library == "pyodbc":
            with contextlib.suppress(Exception):
                stmt.close()
        else:
            import ibm_db

            with contextlib.suppress(Exception):
                ibm_db.free_stmt(stmt)

    def close_immediately(self, stmt: Any) -> None:
        try:
            self.close_statement(stmt)
        finally:
            with contextlib.suppress(Exception):
                self._raw_conn.close()

    def __enter__(self) -> "_ConnHandle":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        with contextlib.suppress(Exception):
            self._raw_conn.close()


class ConnectionFactory:
    def __init__(self, module, library: str, driver_string: str):
        self.module = module
        self.library = library
        self.driver_string = driver_string

    @staticmethod
    def from_adjacent_module(filename_hint: str = "conexion_as400") -> Tuple["ConnectionFactory", DriverInfo]:
        base_dir = os.path.dirname(os.path.abspath(get_main_path()))
        candidates = [
            os.path.join(base_dir, f)
            for f in os.listdir(base_dir)
            if f.lower().startswith(filename_hint) and f.lower().endswith(".py")
        ]
        if not candidates:
            raise FileNotFoundError(
                f"No se encontró el módulo de conexión '{filename_hint}*.py' junto al script."
            )
        path = candidates[0]
        spec = importlib.util.spec_from_file_location("conexion_as400_module", path)
        if spec is None or spec.loader is None:
            raise RuntimeError("No se pudo cargar el módulo de conexión.")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)  # importa TAL CUAL

        with open(path, "r", encoding="utf-8", errors="ignore") as f:
            src = f.read()
        lib = "ibm_db" if re.search(r"\bibm_db\b", src) else "pyodbc"
        driver_hint = ""
        m = re.search(r"DRIVER\s*=\s*\{([^}]+)\}", src, re.IGNORECASE)
        if m:
            driver_hint = m.group(1)
        else:
            m2 = re.search(r"DATABASE\s*=\s*([^;\s]+)", src, re.IGNORECASE)
            if m2:
                driver_hint = m2.group(1)
        return ConnectionFactory(module, lib, driver_hint), DriverInfo(lib, driver_hint)

    def open_connection(self, timeout_s: int) -> _ConnHandle:
        if self.library == "pyodbc":
            import pyodbc

            conn_str = getattr(self.module, "conn_str", None)
            if not conn_str:
                raise RuntimeError("El módulo de conexión no define 'conn_str'.")
            raw = pyodbc.connect(conn_str, timeout=timeout_s)
            driver_name = raw.getinfo(pyodbc.SQL_DRIVER_NAME)
            return _ConnHandle("pyodbc", raw, driver_name)
        else:
            import ibm_db

            dsn = getattr(self.module, "dsn", None)
            uid = getattr(self.module, "UID", None) or getattr(self.module, "uid", None)
            pwd = getattr(self.module, "PWD", None) or getattr(self.module, "pwd", None)
            database = getattr(self.module, "DATABASE", None) or getattr(self.module, "database", None)
            system = getattr(self.module, "SYSTEM", None) or getattr(self.module, "system", None)

            if dsn:
                raw = ibm_db.connect(dsn, "", "")
            else:
                conn_str = getattr(self.module, "conn_str", None)
                if conn_str:
                    raw = ibm_db.connect(conn_str, "", "")
                else:
                    if not (database and uid and pwd and system):
                        raise RuntimeError("Faltan parámetros para ibm_db en el módulo adjunto.")
                    conninfo = (
                        f"DATABASE={database};HOSTNAME={system};PORT=50000;PROTOCOL=TCPIP;UID={uid};PWD={pwd};"
                    )
                    raw = ibm_db.connect(conninfo, "", "")
            return _ConnHandle("ibm_db", raw, "ibm_db")


# ============================ Runner en hilo ============================
@dataclass
class RunnerEvents:
    on_header: Callable[[List[str]], None]
    on_progress: Callable[[int], None]
    on_done: Callable[[str, float, bool], None]
    on_error: Callable[[Exception], None]


class QueryRunner:
    def __init__(
        self,
        connection_factory: ConnectionFactory,
        sql: str,
        csv_options: CsvWriterOptions,
        batch_size: int,
        timeout_s: int,
        expected_rows: Optional[int],
        logger: logging.Logger,
        ui_log: Callable[[str], None],
    ) -> None:
        self.cf = connection_factory
        self.sql = sql
        self.csv_options = csv_options
        self.batch_size = max(1, int(batch_size))
        self.timeout_s = max(1, int(timeout_s))
        self.expected_rows = expected_rows
        self.logger = logger
        self.ui_log = ui_log
        self._cancel_requested = threading.Event()
        self._hard_cancel_requested = threading.Event()
        self.is_running = False

    def request_cancel(self, soft: bool) -> None:
        self._cancel_requested.set()
        if not soft:
            self._hard_cancel_requested.set()

    def run(self, events: RunnerEvents) -> None:
        start = time.time()
        rows_exported = 0
        incomplete = False
        sha_sql = hashlib.sha256(self.sql.encode("utf-8", errors="ignore")).hexdigest()
        self.is_running = True
        try:
            with self.cf.open_connection(timeout_s=self.timeout_s) as conn:
                self.ui_log(f"Conectado con {conn.library} | Driver: {conn.driver_name}")
                self.logger.info("Conectado. Lib: %s Driver: %s", conn.library, conn.driver_name)
                with CsvStreamWriter(self.csv_options) as csvw:
                    stmt = conn.execute(self.sql)
                    try:
                        cols = conn.describe_columns(stmt)
                        events.on_header(cols)
                        csvw.write_header(cols)
                        while True:
                            if self._hard_cancel_requested.is_set():
                                incomplete = True
                                self.ui_log("Cancelación dura: cerrando cursor/conexión…")
                                conn.close_immediately(stmt)
                                break
                            if self._cancel_requested.is_set():
                                self.ui_log("Cancelación suave: intentando cancelar el cursor…")
                                if conn.cancel(stmt):
                                    incomplete = True
                                    break
                            batch = conn.fetchmany(stmt, self.batch_size)
                            if not batch:
                                break
                            csvw.write_rows(batch)
                            rows_exported += len(batch)
                            events.on_progress(rows_exported)
                    finally:
                        with contextlib.suppress(Exception):
                            conn.close_statement(stmt)
            duration = time.time() - start
            self.logger.info(
                "Ejecución terminada | filas=%s | duracion=%.2fs | INCOMPLETO=%s | csv=%s",
                rows_exported,
                duration,
                incomplete,
                self.csv_options.path,
            )
            # Nota: primeros 2KB del SQL para log legible
            preview = self.sql[:2048].replace("\n", " ")
            self.ui_log(
                f"SQL[0..2KB]=""{preview}"" | SHA-256={sha_sql} | Filas={rows_exported} | Duración={duration:.2f}s | INCOMPLETO={incomplete}"
            )
            events.on_done(self.csv_options.path, duration, incomplete)
        except Exception as exc:
            self.logger.exception("Fallo en ejecución | INCOMPLETO=%s", incomplete)
            events.on_error(exc)
        finally:
            self.is_running = False


# ============================ UI Tkinter ============================
class App(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title(f"{APP_NAME} - IBM i / DB2 for i")
        self.geometry("1060x720")
        self.minsize(980, 640)

        self.config_store = AppConfig()
        self.config_store.load()

        self.connection_factory: Optional[ConnectionFactory] = None
        self.driver_info: Optional[DriverInfo] = None
        self.runner: Optional[QueryRunner] = None
        self.current_csv_path: Optional[str] = None
        self.rows_exported = tk.IntVar(value=0)

        self._build_widgets()
        self._load_connection_module()

    # ---- UI ----
    def _build_widgets(self) -> None:
        top = ttk.Frame(self)
        top.pack(fill=tk.X, padx=8, pady=6)
        ttk.Button(top, text="Probar conexión", command=self.on_test_connection).pack(side=tk.LEFT)
        ttk.Button(top, text="Ejecutar", command=self.on_execute).pack(side=tk.LEFT, padx=(6, 0))
        self.btn_cancel = ttk.Button(top, text="Cancelar", command=self.on_cancel, state=tk.DISABLED)
        self.btn_cancel.pack(side=tk.LEFT, padx=(6, 0))
        self.btn_hard_cancel = ttk.Button(top, text="Cancelar dura", command=self.on_hard_cancel, state=tk.DISABLED)
        self.btn_hard_cancel.pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(top, text="Limpiar", command=self.on_clear).pack(side=tk.LEFT, padx=(6, 0))
        self.btn_export = ttk.Button(top, text="Exportar", command=self.on_export, state=tk.DISABLED)
        self.btn_export.pack(side=tk.LEFT, padx=(6, 0))
        ttk.Button(top, text="Salir", command=self.on_quit).pack(side=tk.RIGHT)

        mid = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        mid.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 6))

        left = ttk.Frame(mid)
        ttk.Label(left, text="SQL (solo SELECT por defecto):").pack(anchor=tk.W)
        self.txt_sql = tk.Text(left, wrap=tk.NONE, undo=True, height=20)
        self.txt_sql.pack(fill=tk.BOTH, expand=True)
        yscroll = ttk.Scrollbar(left, command=self.txt_sql.yview)
        xscroll = ttk.Scrollbar(left, orient=tk.HORIZONTAL, command=self.txt_sql.xview)
        self.txt_sql.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        yscroll.pack(side=tk.RIGHT, fill=tk.Y)
        xscroll.pack(side=tk.BOTTOM, fill=tk.X)
        ttk.Button(left, text="Cargar .sql", command=self.on_load_sql_file).pack(anchor=tk.W, pady=4)
        mid.add(left, weight=3)

        right = ttk.Frame(mid)
        frm_opts = ttk.LabelFrame(right, text="Opciones de ejecución y exportación")
        frm_opts.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(frm_opts, text="Delimitador CSV:").grid(row=0, column=0, sticky=tk.W, padx=6, pady=4)
        self.delim_var = tk.StringVar(value=self.config_store.data.get("delimiter", ","))
        ttk.Radiobutton(frm_opts, text=", (coma)", variable=self.delim_var, value=",").grid(row=0, column=1, sticky=tk.W)
        ttk.Radiobutton(frm_opts, text="; (punto y coma)", variable=self.delim_var, value=";").grid(row=0, column=2, sticky=tk.W)

        self.bom_var = tk.BooleanVar(value=self.config_store.data.get("bom", True))
        ttk.Checkbutton(frm_opts, text="Incluir BOM UTF-8", variable=self.bom_var).grid(row=1, column=1, sticky=tk.W, padx=6)

        self.select_only_var = tk.BooleanVar(value=self.config_store.data.get("select_only", True))
        ttk.Checkbutton(frm_opts, text="Bloquear DML/DDL (solo SELECT)", variable=self.select_only_var).grid(row=1, column=2, sticky=tk.W)

        ttk.Label(frm_opts, text="Límite de filas:").grid(row=2, column=0, sticky=tk.W, padx=6)
        self.limit_var = tk.IntVar(value=int(self.config_store.data.get("limit", DEFAULT_LIMIT)))
        self.all_rows_var = tk.BooleanVar(value=False)
        self.spn_limit = ttk.Spinbox(frm_opts, from_=1, to=10_000_000, textvariable=self.limit_var, width=10)
        self.spn_limit.grid(row=2, column=1, sticky=tk.W)
        ttk.Checkbutton(frm_opts, text="Todos los registros", variable=self.all_rows_var, command=self._update_progress_mode).grid(row=2, column=2, sticky=tk.W)

        ttk.Label(frm_opts, text="Tamaño de lote:").grid(row=3, column=0, sticky=tk.W, padx=6)
        self.batch_var = tk.IntVar(value=int(self.config_store.data.get("batch_size", DEFAULT_BATCH)))
        ttk.Spinbox(frm_opts, from_=100, to=100_000, textvariable=self.batch_var, width=10).grid(row=3, column=1, sticky=tk.W)

        ttk.Label(frm_opts, text="Timeout (s):").grid(row=3, column=2, sticky=tk.W)
        self.timeout_var = tk.IntVar(value=int(self.config_store.data.get("timeout", DEFAULT_TIMEOUT)))
        ttk.Spinbox(frm_opts, from_=5, to=3600, textvariable=self.timeout_var, width=10).grid(row=3, column=3, sticky=tk.W)

        frm_out = ttk.LabelFrame(right, text="Salida")
        frm_out.pack(fill=tk.X)
        ttk.Label(frm_out, text="Archivo CSV:").grid(row=0, column=0, sticky=tk.W, padx=6, pady=4)
        self.out_path_var = tk.StringVar(value="")
        self.ent_out = ttk.Entry(frm_out, textvariable=self.out_path_var, width=60)
        self.ent_out.grid(row=0, column=1, sticky=tk.W, padx=4)
        ttk.Button(frm_out, text="Guardar como…", command=self.on_browse_output).grid(row=0, column=2, padx=4)
        mid.add(right, weight=2)

        bottom = ttk.Frame(self)
        bottom.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
        self.prog = ttk.Progressbar(bottom, mode="indeterminate")
        self.prog.pack(fill=tk.X)
        stats = ttk.Frame(bottom)
        stats.pack(fill=tk.X)
        self.lbl_rows = ttk.Label(stats, text="Filas exportadas: 0")
        self.lbl_rows.pack(side=tk.LEFT)
        self.txt_log = tk.Text(bottom, height=10, wrap=tk.WORD, state=tk.DISABLED)
        self.txt_log.pack(fill=tk.BOTH, expand=True, pady=(4, 0))

    def _log_to_ui(self, msg: str) -> None:
        self.txt_log.configure(state=tk.NORMAL)
        self.txt_log.insert(tk.END, time.strftime("[%Y-%m-%d %H:%M:%S] ") + msg + "\n")
        self.txt_log.configure(state=tk.DISABLED)
        self.txt_log.see(tk.END)

    def _update_progress_mode(self) -> None:
        if self.all_rows_var.get():
            self.prog.config(mode="indeterminate")
        else:
            self.prog.config(mode="determinate", maximum=max(1, self.limit_var.get()))

    # ---- Carga de módulo de conexión ----
    def _load_connection_module(self) -> None:
        try:
            self.connection_factory, self.driver_info = ConnectionFactory.from_adjacent_module()
            self._log_to_ui(f"Conector detectado: {self.driver_info.library} - {self.driver_info.driver_string}")
            LOGGER.info("Librería detectada: %s | Driver/DSN: %s", self.driver_info.library, self.driver_info.driver_string)
        except Exception as exc:
            LOGGER.exception("Error cargando módulo de conexión adjunto")
            messagebox.showerror("Error", f"No se pudo cargar el módulo de conexión adjunto. Detalle: {exc}")

    # ---- Acciones ----
    def on_load_sql_file(self) -> None:
        path = filedialog.askopenfilename(
            title="Selecciona archivo .sql",
            filetypes=[("SQL", "*.sql"), ("Todos", "*.*")],
            initialdir=self.config_store.data.get("last_dir") or os.path.expanduser("~"),
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                sql = f.read()
            self.txt_sql.delete("1.0", tk.END)
            self.txt_sql.insert("1.0", sql)
            self._log_to_ui(f"Cargado SQL desde: {path}")
            self.config_store.data["last_dir"] = os.path.dirname(path)
            self.config_store.save()
        except Exception as exc:
            messagebox.showerror("Error", f"No se pudo leer el archivo SQL: {exc}")

    def on_browse_output(self) -> None:
        initialdir = self.config_store.data.get("last_dir") or os.path.expanduser("~")
        path = filedialog.asksaveasfilename(
            title="Guardar como CSV",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            initialdir=initialdir,
        )
        if path:
            self.out_path_var.set(path)
            self.config_store.data["last_dir"] = os.path.dirname(path)
            self.config_store.save()

    def on_test_connection(self) -> None:
        if not self.connection_factory:
            messagebox.showwarning("Conexión", "No se encontró el módulo de conexión adjunto.")
            return
        try:
            timeout = int(self.timeout_var.get())
            with self.connection_factory.open_connection(timeout_s=timeout) as conn:
                driver_str = conn.driver_name
            messagebox.showinfo("Conexión", f"Conexión exitosa. Driver: {driver_str}")
            self._log_to_ui(f"Conexión OK. Driver: {driver_str}")
        except Exception as exc:
            LOGGER.exception("Fallo de prueba de conexión")
            messagebox.showerror("Conexión", f"Error probando conexión: {exc}")
            self._log_to_ui(f"Error de conexión: {exc}")

    def _gather_sql(self) -> str:
        raw_sql = self.txt_sql.get("1.0", tk.END).strip()
        if not raw_sql:
            raise ValueError("El editor SQL está vacío.")
        if self.select_only_var.get():
            ensure_select_only(raw_sql)
        if not self.all_rows_var.get():
            limit = int(self.limit_var.get())
            raw_sql = maybe_inject_fetch_first(raw_sql, limit)
        return raw_sql

    def _gather_csv_options(self) -> CsvWriterOptions:
        delim = self.delim_var.get()
        bom = bool(self.bom_var.get())
        out_path = self.out_path_var.get().strip()
        if not out_path:
            self.on_browse_output()
            out_path = self.out_path_var.get().strip()
        if not out_path:
            raise ValueError("Selecciona una ruta de salida para el CSV.")
        return CsvWriterOptions(path=out_path, delimiter=delim, bom=bom)

    def on_execute(self) -> None:
        if self.runner and self.runner.is_running:
            messagebox.showwarning("Ejecución", "Ya hay una ejecución en curso.")
            return
        try:
            sql = self._gather_sql()
            csv_opts = self._gather_csv_options()
            batch = int(self.batch_var.get())
            timeout = int(self.timeout_var.get())
        except Exception as exc:
            messagebox.showerror("Parámetros", str(exc))
            return

        self.rows_exported.set(0)
        self.lbl_rows.config(text="Filas exportadas: 0")
        self._update_progress_mode()
        self.prog.start(12)

        self.config_store.data.update({
            "delimiter": csv_opts.delimiter,
            "bom": csv_opts.bom,
            "limit": int(self.limit_var.get()),
            "batch_size": batch,
            "timeout": timeout,
            "select_only": bool(self.select_only_var.get()),
        })
        self.config_store.save()

        events = RunnerEvents(
            on_header=lambda cols: self._log_to_ui(f"Columnas: {len(cols)}"),
            on_progress=self._on_rows_progress,
            on_done=self._on_run_done,
            on_error=self._on_run_error,
        )
        self.runner = QueryRunner(
            connection_factory=self.connection_factory,
            sql=sql,
            csv_options=csv_opts,
            batch_size=batch,
            timeout_s=timeout,
            expected_rows=None if self.all_rows_var.get() else int(self.limit_var.get()),
            logger=LOGGER,
            ui_log=self._log_to_ui,
        )
        self._toggle_run_buttons(True)
        threading.Thread(target=self.runner.run, args=(events,), daemon=True).start()

    def _toggle_run_buttons(self, running: bool) -> None:
        self.btn_cancel.config(state=tk.NORMAL if running else tk.DISABLED)
        self.btn_hard_cancel.config(state=tk.NORMAL if running else tk.DISABLED)

    def _on_rows_progress(self, rows: int) -> None:
        self.rows_exported.set(rows)
        self.lbl_rows.config(text=f"Filas exportadas: {rows}")
        if self.prog["mode"] == "determinate":
            self.prog["value"] = rows

    def _on_run_done(self, csv_path: str, duration_s: float, incomplete: bool) -> None:
        self.prog.stop()
        self._toggle_run_buttons(False)
        self.btn_export.config(state=tk.NORMAL)
        self.current_csv_path = csv_path
        msg = "Completado" if not incomplete else "Completado (INCOMPLETO por cancelación)"
        self._log_to_ui(f"{msg}. Archivo: {csv_path}. Duración: {duration_s:.2f}s")
        messagebox.showinfo("Ejecución", f"{msg}.\nArchivo: {csv_path}")

    def _on_run_error(self, exc: Exception) -> None:
        self.prog.stop()
        self._toggle_run_buttons(False)
        LOGGER.exception("Error de ejecución")
        messagebox.showerror("Error", str(exc))

    def on_cancel(self) -> None:
        if self.runner:
            self.runner.request_cancel(soft=True)
            self._log_to_ui("Cancelación solicitada (suave)…")

    def on_hard_cancel(self) -> None:
        if self.runner:
            self.runner.request_cancel(soft=False)
            self._log_to_ui("Cancelación DURA solicitada… (se cerrará cursor/conexión)")

    def on_export(self) -> None:
        if not self.current_csv_path or not os.path.exists(self.current_csv_path):
            messagebox.showwarning("Exportar", "No hay resultados recientes que exportar.")
            return
        dest = filedialog.asksaveasfilename(
            title="Exportar copia como",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
            initialdir=self.config_store.data.get("last_dir") or os.path.expanduser("~"),
        )
        if not dest:
            return
        try:
            from shutil import copyfile

            copyfile(self.current_csv_path, dest)
            self._log_to_ui(f"Copia exportada a: {dest}")
            self.config_store.data["last_dir"] = os.path.dirname(dest)
            self.config_store.save()
        except Exception as exc:
            messagebox.showerror("Exportar", f"No se pudo exportar: {exc}")

    def on_clear(self) -> None:
        self.txt_log.configure(state=tk.NORMAL)
        self.txt_log.delete("1.0", tk.END)
        self.txt_log.configure(state=tk.DISABLED)
        self.lbl_rows.config(text="Filas exportadas: 0")

    def on_quit(self) -> None:
        if self.runner and self.runner.is_running:
            if not messagebox.askyesno("Salir", "Hay una ejecución en curso. ¿Deseas salir y cancelar?"):
                return
            self.on_hard_cancel()
        self.destroy()


# ============================ Main ============================
if __name__ == "__main__":
    app = App()
    app.mainloop()
