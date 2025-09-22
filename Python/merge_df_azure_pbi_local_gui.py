# -*- coding: utf-8 -*-
"""
merge_df_azure_pbi_local_gui.py  (v3 – fix connect)

GUI para seleccionar un Excel LOCAL (hoja 'Facturacion') y hacer MERGE
contra "PDB_CRONUS"."DF_AZURE_PBI" usando STAGING.

Cambios v3:
- Conexión Oracle robusta: intenta con encoding/nencoding y reintenta sin ellos si el
  driver no los soporta. Compatibilidad con 'oracledb' y 'cx_Oracle'.
- Loguea el driver y su versión.

Requisitos:
    pip install pandas openpyxl oracledb   # (o cx_Oracle)
"""
from __future__ import annotations

import os
import sys
import json
import time
import queue
import threading
from typing import Dict, Tuple

import pandas as pd

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

import logging
from logging.handlers import RotatingFileHandler

# --- Driver Oracle con fallback ---
try:
    import oracledb as db  # driver moderno (modo thin por defecto)
except Exception:
    try:
        import cx_Oracle as db  # fallback
    except Exception as e:
        raise SystemExit("Instala 'oracledb' o 'cx_Oracle'. Detalle: %s" % e)

APP_NAME = "MERGE DF_AZURE_PBI (Excel local)"
LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "merge_df_azure_pbi.log")
BATCH_SIZE = 1000
KEY_SENTINEL = -1

SCHEMA = "PDB_CRONUS"
TGT_TABLE = "DF_AZURE_PBI"
STG_TABLE = "STG_DF_AZURE_PBI_MERGE"
DEFAULT_SHEET = "Facturacion"

ALL_COLUMNS = [
    "T_WORK_ITEM_ID", "T_FACTURABLE", "T_TITLE", "T_ASSIGNED_TO", "T_ESTADO",
    "T_PERIODO_FIN_TAREA", "T_FECHA_INICIO", "T_FECHA_FIN", "T_HITO", "T_PROCESO",
    "T_EMPRESA", "T_ROL", "T_LINEA_PRODUCTO", "T_PUNTOS_HISTORIA", "T_VALOR_FACTURADO",
    "T_VALUESTREAM", "T_TEAM",
    "P_WORKITEMID", "P_TIPO_HU", "P_ASSIGNED_TO", "P_TITLE", "P_LINEA_PRODUCTO",
    "P_FECHA_ESTIMADA", "P_FECHA_CIERRE", "P_TIPO_PPTO", "P_PEP_CECO", "P_ESTADO",
    "P_SUBESTADO", "PH_DESARROLLO", "PH_TALLA_DESARROLLO", "PH_PRUEBAS",
    "PH_TALLA_PRUEBAS", "P_PUNTOS_HISTORIA_PBI", "P_TALLA_PBI", "P_VALUESTREAM", "P_TEAM",
    "F_WORKITEMID", "F_TITLE", "F_PI_PPTO", "F_INICIATIVA", "F_FECHAESTEV",
    "F_FECHAPEF", "F_FECHAREALEV", "F_VALUESTREAM", "F_TEAM", "AUDITADO"
]
KEY_COLS = ["T_WORK_ITEM_ID", "P_WORKITEMID", "F_WORKITEMID"]
DATE_COLS = ["T_FECHA_INICIO", "T_FECHA_FIN", "P_FECHA_ESTIMADA", "P_FECHA_CIERRE", "F_FECHAESTEV"]
NUM_COLS = [
    "T_WORK_ITEM_ID", "T_PERIODO_FIN_TAREA", "T_PUNTOS_HISTORIA", "T_VALOR_FACTURADO",
    "P_WORKITEMID", "P_PUNTOS_HISTORIA_PBI", "F_WORKITEMID", "F_INICIATIVA"
]
STR_DATE_LIKE = ["F_FECHAPEF", "F_FECHAREALEV"]


# ---------------- Logging ----------------
def setup_logging() -> logging.Logger:
    os.makedirs(LOG_DIR, exist_ok=True)
    logger = logging.getLogger(APP_NAME)
    logger.setLevel(logging.INFO)
    fmt = logging.Formatter("[%(asctime)s] %(levelname)s - %(message)s", "%Y-%m-%d %H:%M:%S")
    fh = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    logger.addHandler(fh)
    sh = logging.StreamHandler(sys.stdout)
    sh.setFormatter(fmt)
    logger.addHandler(sh)
    return logger


logger = setup_logging()


# --------------- Helpers de ruta/config ---------------
def app_base_dir() -> str:
    """Carpeta donde está el .py o el .exe (PyInstaller)."""
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def find_oracle_config_path(default_name: str = "oracle_config.json") -> str | None:
    """
    Busca oracle_config.json en:
      1) ORACLE_CONFIG_PATH (env)
      2) Junto al .py/.exe
      3) En CWD
    """
    env_path = os.environ.get("ORACLE_CONFIG_PATH")
    if env_path and os.path.isfile(env_path):
        return env_path
    base = app_base_dir()
    candidate1 = os.path.join(base, default_name)
    if os.path.isfile(candidate1):
        return candidate1
    candidate2 = os.path.join(os.getcwd(), default_name)
    if os.path.isfile(candidate2):
        return candidate2
    return None


def load_oracle_config(path: str) -> Dict[str, str]:
    """Carga el JSON de credenciales Oracle."""
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    for k in ("user", "password", "dsn"):
        if not cfg.get(k):
            raise ValueError(f"'{k}' es obligatorio en {os.path.basename(path)}")
    # 'encoding' y 'nencoding' son opcionales; se probarán y si el driver no los soporta, se ignoran.
    return cfg


# ---------------- Conexión Oracle robusta ----------------
def connect_oracle(cfg: Dict[str, str]):
    """
    Intenta conectar usando el driver disponible (oracledb o cx_Oracle).
    - Primero intenta con 'encoding'/'nencoding' si están en el JSON.
    - Si el driver no acepta esos kwargs (TypeError), reintenta sin ellos.
    """
    params = dict(user=cfg["user"], password=cfg["password"], dsn=cfg["dsn"])
    if cfg.get("encoding"):
        params["encoding"] = cfg["encoding"]
    if cfg.get("nencoding"):
        params["nencoding"] = cfg["nencoding"]

    try:
        conn = db.connect(**params)
        logger.info("Conexión establecida con %s %s (con encoding).", db.__name__, getattr(db, "__version__", ""))
        return conn
    except TypeError:
        # Remover argumentos no soportados y reintentar
        params.pop("encoding", None)
        params.pop("nencoding", None)
        conn = db.connect(**params)
        logger.info("Conexión establecida con %s %s (sin encoding).", db.__name__, getattr(db, "__version__", ""))
        return conn


# ---------------- Normalización Excel ----------------
def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.rename(columns={c: c.upper() for c in df.columns})
    for c in ALL_COLUMNS:
        if c not in df.columns:
            df[c] = None
    df = df[ALL_COLUMNS]

    for c in NUM_COLS:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    for c in DATE_COLS:
        df[c] = pd.to_datetime(df[c], errors="coerce")

    for c in STR_DATE_LIKE:
        df[c] = df[c].astype(object)
        df.loc[df[c].isin([None, "", " ", "NaN", "nan", "NaT"]), c] = None

    df = df.drop_duplicates(subset=KEY_COLS, keep="last")
    return df


# ---------------- Oracle DDL/DML ----------------
def create_staging_table(cur, schema: str, stg: str, tgt: str) -> None:
    cur.execute("""
        BEGIN
            EXECUTE IMMEDIATE 'DROP TABLE "{schema}"."{stg}" PURGE';
        EXCEPTION WHEN OTHERS THEN
            IF SQLCODE != -942 THEN RAISE; END IF;
        END;
    """.format(schema=schema, stg=stg))
    cur.execute('CREATE TABLE "{schema}"."{stg}" AS SELECT * FROM "{schema}"."{tgt}" WHERE 1=0'
                .format(schema=schema, stg=stg, tgt=tgt))


def insert_staging_in_batches(conn, df: pd.DataFrame, schema: str, stg: str,
                              progress_cb=None, cancel_flag: threading.Event | None = None) -> Tuple[int, int]:
    cur = conn.cursor()
    placeholders = ",".join([f":{i+1}" for i in range(len(ALL_COLUMNS))])
    sql = f'INSERT INTO "{schema}"."{stg}" ({",".join(ALL_COLUMNS)}) VALUES ({placeholders})'

    rows = []
    for _, r in df.iterrows():
        vals = []
        for c in ALL_COLUMNS:
            v = r[c]
            if isinstance(v, pd.Timestamp):
                v = None if pd.isna(v) else v.to_pydatetime()
            elif pd.isna(v):
                v = None
            vals.append(v)
        rows.append(tuple(vals))

    total = len(rows)
    done = 0
    for i in range(0, total, BATCH_SIZE):
        if cancel_flag and cancel_flag.is_set():
            logger.warning("Cancelación solicitada durante carga a STAGING.")
            break
        batch = rows[i:i + BATCH_SIZE]
        cur.executemany(sql, batch)
        conn.commit()
        done += len(batch)
        if progress_cb:
            progress_cb(done, total)
    cur.close()
    return done, total


def merge_from_staging(conn, schema: str, stg: str, tgt: str) -> int:
    cur = conn.cursor()
    update_cols = [c for c in ALL_COLUMNS if c not in KEY_COLS]
    set_clause = ", ".join([f'tgt."{c}" = src."{c}"' for c in update_cols])
    insert_cols = ",".join([f'"{c}"' for c in ALL_COLUMNS])
    insert_vals = ",".join([f'src."{c}"' for c in ALL_COLUMNS])

    merge_sql = f"""
        MERGE INTO "{schema}"."{tgt}" tgt
        USING (
            SELECT
                NVL("T_WORK_ITEM_ID", {KEY_SENTINEL}) AS "T_WORK_ITEM_ID",
                NVL("P_WORKITEMID", {KEY_SENTINEL}) AS "P_WORKITEMID",
                NVL("F_WORKITEMID", {KEY_SENTINEL}) AS "F_WORKITEMID",
                {", ".join([f'"{c}"' for c in update_cols])}
            FROM "{schema}"."{stg}"
        ) src
        ON (
            NVL(tgt."T_WORK_ITEM_ID", {KEY_SENTINEL}) = src."T_WORK_ITEM_ID"
        AND NVL(tgt."P_WORKITEMID", {KEY_SENTINEL}) = src."P_WORKITEMID"
        AND NVL(tgt."F_WORKITEMID", {KEY_SENTINEL}) = src."F_WORKITEMID"
        )
        WHEN MATCHED THEN UPDATE SET
            {set_clause}
        WHEN NOT MATCHED THEN INSERT ({insert_cols}) VALUES ({insert_vals})
    """
    cur.execute(merge_sql)
    affected = cur.rowcount
    conn.commit()
    cur.close()
    return affected


# ---------------- GUI ----------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1000x700")
        self.cancel_event = threading.Event()
        self.queue: "queue.Queue[str]" = queue.Queue()
        self._build_ui()
        self._start_log_updater()
        logger.info("Driver Oracle: %s %s", db.__name__, getattr(db, "__version__", ""))
        logger.info("BaseDir: %s", app_base_dir())
        logger.info("CWD    : %s", os.getcwd())

    def _build_ui(self):
        pad = {"padx": 6, "pady": 4}

        frm_xlsx = ttk.LabelFrame(self, text="Origen: Excel local")
        frm_xlsx.pack(fill="x", **pad)
        self.var_xlsx_path = tk.StringVar()
        ttk.Label(frm_xlsx, text="Archivo .xlsx:").grid(row=0, column=0, sticky="w", **pad)
        ttk.Entry(frm_xlsx, textvariable=self.var_xlsx_path, width=85).grid(row=0, column=1, **pad)
        ttk.Button(frm_xlsx, text="Buscar...", command=self._choose_xlsx).grid(row=0, column=2, **pad)

        self.var_sheet = tk.StringVar(value=DEFAULT_SHEET)
        ttk.Label(frm_xlsx, text="Hoja:").grid(row=1, column=0, sticky="w", **pad)
        ttk.Entry(frm_xlsx, textvariable=self.var_sheet, width=30).grid(row=1, column=1, sticky="w", **pad)
        ttk.Button(frm_xlsx, text="Previsualizar", command=self._preview).grid(row=1, column=2, **pad)

        frm_prev = ttk.LabelFrame(self, text="Vista previa (primeras 50 filas)")
        frm_prev.pack(fill="both", expand=True, **pad)
        self.txt_preview = tk.Text(frm_prev, height=14, wrap="none")
        self.txt_preview.pack(fill="both", expand=True)

        frm_prog = ttk.Frame(self)
        frm_prog.pack(fill="x", **pad)
        self.pb = ttk.Progressbar(frm_prog, length=420, mode="determinate")
        self.pb.grid(row=0, column=0, **pad)
        self.var_eta = tk.StringVar(value="ETA: -")
        ttk.Label(frm_prog, textvariable=self.var_eta).grid(row=0, column=1, sticky="w", **pad)
        ttk.Button(frm_prog, text="Procesar MERGE", command=self._process_merge).grid(row=0, column=2, **pad)
        ttk.Button(frm_prog, text="Cancelar", command=self._cancel).grid(row=0, column=3, **pad)

        frm_log = ttk.LabelFrame(self, text="Logs")
        frm_log.pack(fill="both", expand=True, **pad)
        self.txt_log = tk.Text(frm_log, height=12, wrap="word")
        self.txt_log.pack(fill="both", expand=True)

        self.var_status = tk.StringVar(value="Listo.")
        ttk.Label(self, textvariable=self.var_status).pack(anchor="w", **pad)

    # --- UI callbacks ---
    def _choose_xlsx(self):
        p = filedialog.askopenfilename(title="Seleccionar archivo Excel",
                                       filetypes=[("Excel", "*.xlsx"), ("Todos", "*.*")])
        if p:
            self.var_xlsx_path.set(p)

    def _preview(self):
        try:
            path = self.var_xlsx_path.get().strip()
            if not path:
                raise FileNotFoundError("Selecciona primero un archivo .xlsx.")
            sheet = self.var_sheet.get().strip() or DEFAULT_SHEET
            df = pd.read_excel(path, sheet_name=sheet)
            df = normalize_dataframe(df)
            self._set_preview(df.head(50).to_markdown(index=False))
            self._log(f"Previsualización OK. Filas tras normalización: {len(df)}")
        except Exception as e:
            self._log(f"[ERROR] {self._exc_text(e)}")
            messagebox.showerror("Previsualización", str(e))

    def _process_merge(self):
        try:
            xlsx = self.var_xlsx_path.get().strip()
            if not xlsx:
                raise FileNotFoundError("Selecciona un archivo .xlsx antes de procesar.")
            sheet = self.var_sheet.get().strip() or DEFAULT_SHEET

            cfg_path = find_oracle_config_path()
            if not cfg_path:
                self._log("oracle_config.json no encontrado. Selección manual...")
                cfg_path = filedialog.askopenfilename(
                    title="Seleccionar oracle_config.json",
                    filetypes=[("JSON", "*.json"), ("Todos", "*.*")]
                )
                if not cfg_path:
                    raise FileNotFoundError(
                        "No se encontró 'oracle_config.json'. "
                        "Crea el archivo o selecciona su ubicación."
                    )
            self._log(f"Usando config Oracle: {cfg_path}")
            cfg = load_oracle_config(cfg_path)

        except Exception as e:
            messagebox.showerror("Preparación", str(e))
            return

        self.cancel_event.clear()
        self.pb["value"] = 0
        self.var_eta.set("ETA: -")
        self.var_status.set("Procesando...")
        self._log("== Iniciando MERGE (Excel local) ==")

        def work():
            t0 = time.time()
            try:
                # 1) Excel
                self._log("Leyendo Excel local...")
                df = pd.read_excel(xlsx, sheet_name=sheet)
                df = normalize_dataframe(df)
                total_rows = len(df)
                self._log(f"Filas tras normalización/deduplicación: {total_rows}")

                # 2) Oracle
                self._log("Conectando a Oracle...")
                conn = connect_oracle(cfg)
                cur = conn.cursor()

                # 3) STAGING
                self._log(f"Creando STAGING {SCHEMA}.{STG_TABLE}...")
                create_staging_table(cur, SCHEMA, STG_TABLE, TGT_TABLE)
                conn.commit()

                # 4) Insert STAGING por lotes
                self._log(f"Cargando STAGING en lotes de {BATCH_SIZE}...")
                start_batch = time.time()

                def prog(done, total):
                    pct = 0 if total == 0 else int(done * 100 / total)
                    self._async(lambda: self._set_progress(pct, done, total, start_batch))

                inserted, total = insert_staging_in_batches(
                    conn, df, SCHEMA, STG_TABLE, progress_cb=prog, cancel_flag=self.cancel_event
                )
                if self.cancel_event.is_set():
                    conn.rollback()
                    cur.close()
                    conn.close()
                    self._log("Proceso cancelado antes del MERGE.")
                    self._async(lambda: self._finish("Cancelado por el usuario."))
                    return
                self._log(f"Insertados en STAGING: {inserted}/{total}")

                # 5) MERGE
                self._log(f"Ejecutando MERGE {SCHEMA}.{TGT_TABLE} ...")
                affected = merge_from_staging(conn, SCHEMA, STG_TABLE, TGT_TABLE)
                self._log(f"MERGE filas afectadas (INSERT+UPDATE): {affected}")

                # 6) DROP STAGING
                self._log("Eliminando STAGING...")
                try:
                    cur.execute(f'DROP TABLE "{SCHEMA}"."{STG_TABLE}" PURGE')
                    conn.commit()
                except Exception:
                    pass

                cur.close()
                conn.close()
                self._async(lambda: self._finish(f"Completado en {time.time()-t0:0.1f}s"))
            except Exception as e:
                self._log(f"[ERROR] {self._exc_text(e)}")
                self._async(lambda: self._finish(f"Error: {self._exc_text(e)}", error=True))

        threading.Thread(target=work, daemon=True).start()

    def _set_preview(self, md_text: str):
        self.txt_preview.delete("1.0", "end")
        self.txt_preview.insert("1.0", md_text)

    def _set_progress(self, pct: int, done: int, total: int, t0: float):
        self.pb["value"] = pct
        elapsed = time.time() - t0
        rate = (done / elapsed) if elapsed > 0 else 0
        remaining = (total - done) / rate if rate > 0 else 0
        self.var_eta.set(f"ETA: {int(remaining)} s")
        self.var_status.set(f"Progreso: {done}/{total} ({pct}%)")

    def _finish(self, msg: str, error: bool = False):
        self.var_status.set(msg)
        if error:
            messagebox.showerror(APP_NAME, msg)
        else:
            messagebox.showinfo(APP_NAME, msg)

    def _cancel(self):
        self.cancel_event.set()
        self._log("Solicitud de cancelación recibida...")

    def _start_log_updater(self):
        def poll():
            try:
                while True:
                    msg = self.queue.get_nowait()
                    self.txt_log.insert("end", msg + "\n")
                    self.txt_log.see("end")
            except queue.Empty:
                pass
            self.after(300, poll)
        poll()

    def _log(self, msg: str):
        logger.info(msg)
        self.queue.put(msg)

    def _async(self, fn):
        self.after(0, fn)

    @staticmethod
    def _exc_text(e: Exception) -> str:
        return f"{type(e).__name__}: {e}"


if __name__ == "__main__":
    app = App()
    app.mainloop()
