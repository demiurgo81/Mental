# -*- coding: utf-8 -*-
"""
merge_df_azure_pbi_gui.py

GUI para descargar un Excel desde SharePoint (hoja 'Facturacion') y hacer MERGE
contra la tabla Oracle "PDB_CRONUS"."DF_AZURE_PBI" usando una tabla staging.

- Llaves de coincidencia (triple clave): T_WORK_ITEM_ID, P_WORKITEMID, F_WORKITEMID
- Regla MERGE:
    WHEN MATCHED THEN UPDATE (todas las columnas NO llave)
    WHEN NOT MATCHED THEN INSERT (todas las columnas)
- Los NULL de las llaves se comparan como valor usando NVL(col, -1).
- Commits por lotes de 1000 filas.
- Logs en español con rotación (5 MB).

Requisitos (Python 3.12.5):
    pip install pandas openpyxl oracledb office365-rest-python-client msal
    (o cx_Oracle si tu 'conectarOracle.py' lo usa)

Licencias/Notas:
- Acceso a SharePoint requiere un App Registration (Client ID/Secret) o el método que definas.
- No se suben datos fuera de la red corporativa salvo la descarga del Excel.
- No se incrustan credenciales en código. Se usan archivos externos.

Autor: (tu equipo)
"""
from __future__ import annotations

import os
import sys
import json
import time
import queue
import threading
from datetime import datetime
from typing import List, Tuple, Optional, Dict

import pandas as pd

# GUI
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

# Logging (rotación)
import logging
from logging.handlers import RotatingFileHandler

# Oracle
try:
    # Se usará la conexión del módulo local
    # Intentamos dos nombres de función comunes: conectarOracle() o get_connection()
    from conectarOracle import conectarOracle as oracle_connect  # type: ignore
except Exception:
    try:
        from conectarOracle import get_connection as oracle_connect  # type: ignore
    except Exception as _e:
        oracle_connect = None  # se validará en runtime

# SharePoint / MSAL (app-only client credentials recomendado)
try:
    from office365.sharepoint.client_context import ClientContext
    from office365.runtime.auth.client_credential import ClientCredential
except Exception:
    ClientContext = None
    ClientCredential = None


APP_NAME = "MERGE DF_AZURE_PBI"
LOG_DIR = "logs"
LOG_FILE = os.path.join(LOG_DIR, "merge_df_azure_pbi.log")
BATCH_SIZE = 1000
KEY_SENTINEL = -1  # para NVL en llaves numéricas


# Columnas según DDL recibido
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
# VARCHAR "fecha" del lado F_... (tal cual en DDL)
STR_DATE_LIKE = ["F_FECHAPEF", "F_FECHAREALEV"]


# ----------------- Logging -----------------
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


# --------------- SharePoint helpers ----------------
def load_sp_config(path: str) -> Dict[str, str]:
    """
    Lee configuración JSON con credenciales y ubicación del archivo en SharePoint.

    Ejemplo de sharepoint_config.json:
    {
      "tenant": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
      "client_id": "yyyyyyyy-yyyy-yyyy-yyyy-yyyyyyyyyyyy",
      "client_secret": "ZZZZZZZZZZZZZZZZZZZZZZ",
      "site_url": "https://claromovilco.sharepoint.com/sites/coordinacion_lideresdeaplicaciones",
      "server_relative_url": "/sites/coordinacion_lideresdeaplicaciones/Shared Documents/carpeta/archivo.xlsx",
      "sheet_name": "Facturacion"
    }
    """
    with open(path, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    required = ["tenant", "client_id", "client_secret", "site_url", "server_relative_url"]
    missing = [k for k in required if k not in cfg or not cfg[k]]
    if missing:
        raise ValueError(f"Faltan claves en {path}: {', '.join(missing)}")
    if "sheet_name" not in cfg or not cfg["sheet_name"]:
        cfg["sheet_name"] = "Facturacion"
    return cfg


def download_excel_from_sharepoint(cfg: Dict[str, str], dest_path: str) -> str:
    """
    Descarga el archivo Excel desde SharePoint usando app-only (client credentials).
    """
    if ClientContext is None or ClientCredential is None:
        raise RuntimeError("Falta instalar 'office365-rest-python-client'.")

    site_url = cfg["site_url"]
    server_relative_url = cfg["server_relative_url"]
    client_credentials = ClientCredential(cfg["client_id"], cfg["client_secret"])
    ctx = ClientContext(site_url).with_credentials(client_credentials)

    logger.info("Conectando a SharePoint...")
    file = ctx.web.get_file_by_server_relative_path(server_relative_url)
    ctx.load(file)
    ctx.execute_query()
    logger.info("Descargando archivo de SharePoint...")
    with open(dest_path, "wb") as f:
        file.download(f).execute_query()
    logger.info(f"Descarga completada: {dest_path}")
    return dest_path


# --------------- Excel -> DataFrame ----------------
def normalize_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    """
    Normaliza tipos, columnas y duplicados.
    - Asegura todas las columnas del DDL (añade faltantes como None).
    - Convierte numéricas, fechas y mantiene strings.
    - Elimina duplicados por triple llave (conserva la última fila).
    """
    # Renombrar columnas del Excel si vienen con variaciones de mayúsculas/minúsculas
    col_map = {c: c.upper() for c in df.columns}
    df = df.rename(columns=col_map)

    # Añadir columnas faltantes como None
    for c in ALL_COLUMNS:
        if c not in df.columns:
            df[c] = None

    # Quedarse solo con columnas esperadas y reordenar
    df = df[ALL_COLUMNS]

    # Numéricas
    for c in NUM_COLS:
        df[c] = pd.to_numeric(df[c], errors="coerce").astype("Int64" if c != "T_PUNTOS_HISTORIA" and c != "P_PUNTOS_HISTORIA_PBI" else "float64")

    # Fechas DATE
    for c in DATE_COLS:
        df[c] = pd.to_datetime(df[c], errors="coerce")

    # Las "fechas" que en DDL son VARCHAR2
    for c in STR_DATE_LIKE:
        df[c] = df[c].astype(str).replace({"NaT": None, "NaN": None, "nan": None, "None": None})
        df.loc[df[c].isin(["", " ", "NaT"]), c] = None

    # Deduplicar por triple clave, quedando con la última
    df = df.drop_duplicates(subset=KEY_COLS, keep="last")

    return df


# --------------- Oracle helpers ----------------
def ensure_oracle_connection():
    if oracle_connect is None:
        raise RuntimeError(
            "No se pudo importar la conexión desde 'conectarOracle.py'. "
            "Asegúrate de tener una función 'conectarOracle()' o 'get_connection()' que retorne cx_Oracle/oracledb.Connection."
        )
    con = oracle_connect()
    return con


def create_staging_table(cur, schema: str, stg_name: str, tgt_name: str):
    # Crea staging como copia de estructura (sin filas)
    cur.execute(f"""
        BEGIN
            EXECUTE IMMEDIATE 'DROP TABLE "{schema}"."{stg_name}" PURGE';
        EXCEPTION
            WHEN OTHERS THEN
                IF SQLCODE != -942 THEN RAISE; END IF;
        END;
    """)
    cur.execute(f'CREATE TABLE "{schema}"."{stg_name}" AS SELECT * FROM "{schema}"."{tgt_name}" WHERE 1=0')


def insert_staging_in_batches(conn, df: pd.DataFrame, schema: str, stg_name: str,
                              progress_cb=None, cancel_flag: threading.Event = None):
    """
    Inserta el DataFrame en la staging usando executemany con batches y commit cada 1000.
    """
    cur = conn.cursor()

    placeholders = ",".join([f":{i+1}" for i in range(len(ALL_COLUMNS))])
    sql = f'INSERT INTO "{schema}"."{stg_name}" ({",".join(ALL_COLUMNS)}) VALUES ({placeholders})'

    rows = []
    for _, r in df.iterrows():
        row = []
        for c in ALL_COLUMNS:
            v = r[c]
            if pd.isna(v):
                v = None
            # pandas Timestamp -> datetime
            if isinstance(v, pd.Timestamp):
                v = None if pd.isna(v) else v.to_pydatetime()
            row.append(v)
        rows.append(tuple(row))

    total = len(rows)
    done = 0
    for i in range(0, total, BATCH_SIZE):
        if cancel_flag and cancel_flag.is_set():
            logger.warning("Proceso cancelado por el usuario durante la carga a staging.")
            break
        batch = rows[i:i + BATCH_SIZE]
        cur.executemany(sql, batch)
        conn.commit()
        done += len(batch)
        if progress_cb:
            progress_cb(done, total)

    cur.close()
    return done, total


def merge_from_staging(conn, schema: str, stg_name: str, tgt_name: str) -> int:
    """
    Ejecuta el MERGE desde staging a target.
    Devuelve rowcount (aproximado, Oracle puede reportar filas afectadas).
    """
    cur = conn.cursor()

    # Build SET for UPDATE (todas menos las llaves)
    update_cols = [c for c in ALL_COLUMNS if c not in KEY_COLS]
    set_clause = ", ".join([f'tgt."{c}" = src."{c}"' for c in update_cols])

    insert_cols = ",".join([f'"{c}"' for c in ALL_COLUMNS])
    insert_vals = ",".join([f'src."{c}"' for c in ALL_COLUMNS])

    merge_sql = f"""
        MERGE INTO "{schema}"."{tgt_name}" tgt
        USING (
            SELECT
                NVL("T_WORK_ITEM_ID", {KEY_SENTINEL}) AS "T_WORK_ITEM_ID",
                NVL("P_WORKITEMID", {KEY_SENTINEL}) AS "P_WORKITEMID",
                NVL("F_WORKITEMID", {KEY_SENTINEL}) AS "F_WORKITEMID",
                {", ".join([f'"{c}"' for c in update_cols])}
            FROM "{schema}"."{stg_name}"
        ) src
        ON (
            NVL(tgt."T_WORK_ITEM_ID", {KEY_SENTINEL}) = src."T_WORK_ITEM_ID"
        AND NVL(tgt."P_WORKITEMID", {KEY_SENTINEL}) = src."P_WORKITEMID"
        AND NVL(tgt."F_WORKITEMID", {KEY_SENTINEL}) = src."F_WORKITEMID"
        )
        WHEN MATCHED THEN UPDATE
            SET {set_clause}
        WHEN NOT MATCHED THEN
            INSERT ({insert_cols})
            VALUES ({insert_vals})
    """
    cur.execute(merge_sql)
    affected = cur.rowcount
    conn.commit()
    cur.close()
    return affected


# --------------- Tkinter GUI ----------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("980x680")

        self.cancel_event = threading.Event()
        self.queue = queue.Queue()

        self._build_ui()
        self._start_log_updater()

    def _build_ui(self):
        pad = {"padx": 6, "pady": 4}

        # Frame superior: SharePoint config
        frm_sp = ttk.LabelFrame(self, text="Origen de datos (SharePoint Excel)")
        frm_sp.pack(fill="x", **pad)

        self.var_cfg_path = tk.StringVar()
        ttk.Label(frm_sp, text="Config JSON:").grid(row=0, column=0, sticky="w", **pad)
        ttk.Entry(frm_sp, textvariable=self.var_cfg_path, width=80).grid(row=0, column=1, **pad)
        ttk.Button(frm_sp, text="Buscar...",
                   command=self._choose_config).grid(row=0, column=2, **pad)

        self.var_tmp_path = tk.StringVar(value=os.path.join(os.getcwd(), "tmp_sharepoint.xlsx"))
        ttk.Label(frm_sp, text="Descargar a:").grid(row=1, column=0, sticky="w", **pad)
        ttk.Entry(frm_sp, textvariable=self.var_tmp_path, width=80).grid(row=1, column=1, **pad)
        ttk.Button(frm_sp, text="Descargar y Previsualizar",
                   command=self._download_and_preview).grid(row=1, column=2, **pad)

        # Frame medio: Preview
        frm_prev = ttk.LabelFrame(self, text="Vista previa (primeras 50 filas)")
        frm_prev.pack(fill="both", expand=True, **pad)
        self.txt_preview = tk.Text(frm_prev, height=14, wrap="none")
        self.txt_preview.pack(fill="both", expand=True)

        # Progress bar + eta + botones
        frm_prog = ttk.Frame(self)
        frm_prog.pack(fill="x", **pad)
        self.pb = ttk.Progressbar(frm_prog, length=400, mode="determinate")
        self.pb.grid(row=0, column=0, **pad)
        self.var_eta = tk.StringVar(value="ETA: -")
        ttk.Label(frm_prog, textvariable=self.var_eta).grid(row=0, column=1, sticky="w", **pad)
        ttk.Button(frm_prog, text="Procesar MERGE", command=self._process_merge).grid(row=0, column=2, **pad)
        ttk.Button(frm_prog, text="Cancelar", command=self._cancel).grid(row=0, column=3, **pad)

        # Logs
        frm_log = ttk.LabelFrame(self, text="Logs")
        frm_log.pack(fill="both", expand=True, **pad)
        self.txt_log = tk.Text(frm_log, height=10, wrap="word")
        self.txt_log.pack(fill="both", expand=True)

        # Estado
        self.var_status = tk.StringVar(value="Listo.")
        ttk.Label(self, textvariable=self.var_status).pack(anchor="w", **pad)

    # --------- UI callbacks ----------
    def _choose_config(self):
        p = filedialog.askopenfilename(title="Seleccionar sharepoint_config.json",
                                       filetypes=[("JSON", "*.json"), ("Todos", "*.*")])
        if p:
            self.var_cfg_path.set(p)

    def _download_and_preview(self):
        try:
            cfg = load_sp_config(self.var_cfg_path.get())
        except Exception as e:
            messagebox.showerror("Config SharePoint", f"Error cargando configuración:\n{e}")
            return

        tmp = self.var_tmp_path.get()

        def work():
            try:
                t0 = time.time()
                download_excel_from_sharepoint(cfg, tmp)
                df = pd.read_excel(tmp, sheet_name=cfg["sheet_name"])
                df = normalize_dataframe(df)
                preview = df.head(50).to_markdown(index=False)
                self._async_ui(lambda: self._set_preview(preview))
                self._log(f"Excel filas totales: {len(df)}")
                dt = time.time() - t0
                self._log(f"Descarga+preparación completadas en {dt:0.1f}s")
            except Exception as e:
                self._log(f"[ERROR] {_exc_text(e)}")
                messagebox.showerror("Descarga/Preview", str(e))

        threading.Thread(target=work, daemon=True).start()

    def _set_preview(self, md_text: str):
        self.txt_preview.delete("1.0", "end")
        self.txt_preview.insert("1.0", md_text)

    def _process_merge(self):
        # Preparar
        try:
            cfg = load_sp_config(self.var_cfg_path.get())
        except Exception as e:
            messagebox.showerror("Config SharePoint", f"Error cargando configuración:\n{e}")
            return
        tmp = self.var_tmp_path.get()

        self.cancel_event.clear()
        self.pb["value"] = 0
        self.var_eta.set("ETA: -")
        self.var_status.set("Procesando...")
        self._log("== Iniciando proceso MERGE ==")

        def work():
            t0 = time.time()
            try:
                # 1) Descargar
                self._log("Descargando Excel de SharePoint...")
                download_excel_from_sharepoint(cfg, tmp)

                # 2) DataFrame
                self._log("Leyendo y normalizando Excel...")
                df = pd.read_excel(tmp, sheet_name=cfg["sheet_name"])
                df = normalize_dataframe(df)
                total_rows = len(df)
                self._log(f"Filas tras normalización y deduplicación: {total_rows}")

                # 3) Conexión Oracle
                self._log("Conectando a Oracle usando conectarOracle.py...")
                conn = ensure_oracle_connection()
                cur = conn.cursor()

                schema = "PDB_CRONUS"
                tgt = "DF_AZURE_PBI"
                stg = "STG_DF_AZURE_PBI_MERGE"

                # 4) Staging
                self._log("Creando tabla STAGING...")
                create_staging_table(cur, schema, stg, tgt)
                conn.commit()

                # 5) Insert staging en lotes
                self._log("Cargando datos a STAGING en lotes de 1000...")
                start_batch = time.time()

                def prog(done, total):
                    pct = 0 if total == 0 else int(done * 100 / total)
                    self._async_ui(lambda: self._set_progress(pct, done, total, start_batch))

                inserted, total = insert_staging_in_batches(
                    conn, df, schema, stg, progress_cb=prog, cancel_flag=self.cancel_event
                )
                if self.cancel_event.is_set():
                    conn.rollback()
                    cur.close()
                    conn.close()
                    self._log("Proceso cancelado antes del MERGE.")
                    self._async_ui(lambda: self._finish("Cancelado por el usuario."))
                    return
                self._log(f"Insertados en STAGING: {inserted}/{total}")

                # 6) MERGE
                self._log("Ejecutando MERGE desde STAGING a TARGET...")
                affected = merge_from_staging(conn, schema, stg, tgt)
                self._log(f"MERGE filas afectadas (INSERT+UPDATE): {affected}")

                # 7) Limpieza staging (drop)
                self._log("Eliminando STAGING...")
                try:
                    cur.execute(f'DROP TABLE "{schema}"."{stg}" PURGE')
                    conn.commit()
                except Exception as _:
                    pass

                cur.close()
                conn.close()
                dt = time.time() - t0
                self._async_ui(lambda: self._finish(f"Completado en {dt:0.1f}s"))
            except Exception as e:
                self._log(f"[ERROR] {_exc_text(e)}")
                self._async_ui(lambda: self._finish(f"Error: {_exc_text(e)}", error=True))

        threading.Thread(target=work, daemon=True).start()

    def _set_progress(self, pct: int, done: int, total: int, t0: float):
        self.pb["value"] = pct
        elapsed = time.time() - t0
        rate = (done / elapsed) if elapsed > 0 else 0
        remaining = (total - done) / rate if rate > 0 else 0
        self.var_eta.set(f"ETA: {int(remaining)} s")
        self.var_status.set(f"Progreso: {done}/{total} filas ({pct}%)")

    def _finish(self, msg: str, error: bool = False):
        self.var_status.set(msg)
        if error:
            messagebox.showerror(APP_NAME, msg)
        else:
            messagebox.showinfo(APP_NAME, msg)

    def _cancel(self):
        self.cancel_event.set()
        self._log("Solicitud de cancelación recibida...")

    def _log(self, msg: str):
        logger.info(msg)
        self.queue.put(msg)

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

    def _async_ui(self, fn):
        self.after(0, fn)


def _exc_text(e: Exception) -> str:
    return f"{type(e).__name__}: {e}"


if __name__ == "__main__":
    app = App()
    app.mainloop()