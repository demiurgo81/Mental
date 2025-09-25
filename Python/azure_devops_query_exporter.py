"""
azure_devops_query_exporter.py

GUI para descargar los resultados de una consulta de Azure DevOps Work Items
usando un Personal Access Token. Permite exportar a CSV (con separador
personalizable), XLSX o PDF y ofrece previsualizacion de resultados.
"""
from __future__ import annotations

import json
import queue
import re
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Sequence
from urllib.parse import quote

import pandas as pd
import requests
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

API_VERSION = "7.0"
MAX_BATCH = 200
GUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

APP_NAME = "Azure DevOps Query Exporter"
SUPPORTED_FORMATS = ("xlsx", "csv", "pdf")
LOG_MAX_LINES = 400
PREVIEW_MAX_DISPLAY = 200

DEFAULT_ORGANIZATION = "OrgClaroColombia"
DEFAULT_PROJECT = ""
DEFAULT_TEAM_PATH = ""
DEFAULT_CSV_SEPARATOR = ";"
DEFAULT_PREVIEW_ROWS = "20"


class AzureQueryError(RuntimeError):
    """Errores especificos del flujo de consulta."""


@dataclass
class QueryContext:
    organization: str
    project: str | None
    team_segments: Sequence[str]
    query_id: str

    def api_base(self) -> str:
        parts = [self.organization, self.project, *self.team_segments]
        encoded = [quote(part, safe="") for part in parts if part]
        return f"https://dev.azure.com/{'/'.join(encoded)}"


@dataclass
class RunConfig:
    context: QueryContext
    token: str
    fmt: str
    output_path: Path | None
    csv_separator: str
    preview_limit: int


class AzureDevOpsQueryApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("960x720")
        self.root.minsize(900, 660)

        self.org_var = tk.StringVar(value=DEFAULT_ORGANIZATION)
        self.project_var = tk.StringVar(value=DEFAULT_PROJECT)
        self.team_var = tk.StringVar(value=DEFAULT_TEAM_PATH)
        self.query_id_var = tk.StringVar()
        self.token_var = tk.StringVar()
        self.format_var = tk.StringVar(value=SUPPORTED_FORMATS[0])
        self.csv_separator_var = tk.StringVar(value=DEFAULT_CSV_SEPARATOR)
        self.output_var = tk.StringVar(value=str(self._default_output(SUPPORTED_FORMATS[0])))
        self.preview_rows_var = tk.StringVar(value=DEFAULT_PREVIEW_ROWS)
        self.status_var = tk.StringVar(value="Listo.")
        self.preview_info_var = tk.StringVar(value="Sin datos cargados.")

        self.log_queue: "queue.Queue[str]" = queue.Queue()
        self.thread: threading.Thread | None = None

        self.preview_tree: ttk.Treeview | None = None

        self._build_ui()
        self._schedule_log_pump()

    # ------------------------------------------------------------------
    # UI setup
    def _build_ui(self) -> None:
        root = self.root
        root.columnconfigure(0, weight=1)
        root.rowconfigure(0, weight=1)

        main = ttk.Frame(root, padding=15)
        main.grid(row=0, column=0, sticky="nsew")
        for col in range(2):
            main.columnconfigure(col, weight=1)
        for row in range(8):
            main.rowconfigure(row, weight=0)
        main.rowconfigure(8, weight=2)
        main.rowconfigure(9, weight=2)
        main.rowconfigure(10, weight=3)

        # Fila 0 - Organizacion
        ttk.Label(main, text="Organizacion:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.entry_org = ttk.Entry(main, textvariable=self.org_var)
        self.entry_org.grid(row=0, column=1, sticky="ew", padx=5, pady=5)

        # Fila 1 - Proyecto
        ttk.Label(main, text="Proyecto (opcional):").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        self.entry_project = ttk.Entry(main, textvariable=self.project_var)
        self.entry_project.grid(row=1, column=1, sticky="ew", padx=5, pady=5)

        # Fila 2 - Team path
        ttk.Label(main, text="Ruta de equipo (opcional):").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        self.entry_team = ttk.Entry(main, textvariable=self.team_var)
        self.entry_team.grid(row=2, column=1, sticky="ew", padx=5, pady=5)

        # Fila 3 - Query ID
        ttk.Label(main, text="Query ID (GUID):").grid(row=3, column=0, sticky="w", padx=5, pady=5)
        self.entry_query_id = ttk.Entry(main, textvariable=self.query_id_var)
        self.entry_query_id.grid(row=3, column=1, sticky="ew", padx=5, pady=5)

        # Fila 4 - Token
        ttk.Label(main, text="Personal Access Token:").grid(row=4, column=0, sticky="w", padx=5, pady=5)
        self.entry_token = ttk.Entry(main, textvariable=self.token_var, show="*")
        self.entry_token.grid(row=4, column=1, sticky="ew", padx=5, pady=5)

        # Fila 5 - Formato y separador
        fmt_frame = ttk.Frame(main)
        fmt_frame.grid(row=5, column=0, columnspan=2, sticky="ew", padx=5, pady=5)
        fmt_frame.columnconfigure(1, weight=1)
        ttk.Label(fmt_frame, text="Formato de salida:").grid(row=0, column=0, sticky="w")
        self.combo_format = ttk.Combobox(fmt_frame, textvariable=self.format_var, values=list(SUPPORTED_FORMATS), state="readonly", width=8)
        self.combo_format.grid(row=0, column=1, sticky="w")
        self.combo_format.bind("<<ComboboxSelected>>", self._on_format_change)

        ttk.Label(fmt_frame, text="Separador CSV:").grid(row=0, column=2, sticky="w", padx=(20, 0))
        self.entry_csv_sep = ttk.Entry(fmt_frame, textvariable=self.csv_separator_var, width=6)
        self.entry_csv_sep.grid(row=0, column=3, sticky="w")

        # Fila 6 - Archivo salida
        ttk.Label(main, text="Archivo de salida:").grid(row=6, column=0, sticky="w", padx=5, pady=5)
        path_frame = ttk.Frame(main)
        path_frame.grid(row=6, column=1, sticky="ew", padx=5, pady=5)
        path_frame.columnconfigure(0, weight=1)
        self.entry_output = ttk.Entry(path_frame, textvariable=self.output_var)
        self.entry_output.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        self.btn_browse = ttk.Button(path_frame, text="Examinar...", command=self._select_output)
        self.btn_browse.grid(row=0, column=1)

        # Fila 7 - Botones principales
        button_frame = ttk.Frame(main)
        button_frame.grid(row=7, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        button_frame.columnconfigure(0, weight=1)
        button_frame.columnconfigure(1, weight=1)
        button_frame.columnconfigure(2, weight=1)

        self.btn_preview = ttk.Button(button_frame, text="Previsualizar", command=self._on_preview)
        self.btn_preview.grid(row=0, column=0, sticky="ew", padx=5)

        self.btn_run = ttk.Button(button_frame, text="Descargar", command=self._on_execute)
        self.btn_run.grid(row=0, column=1, sticky="ew", padx=5)

        ttk.Button(button_frame, text="Salir", command=self.root.destroy).grid(row=0, column=2, sticky="ew", padx=5)

        # Fila 8 - Progreso y estado
        status_frame = ttk.Frame(main)
        status_frame.grid(row=8, column=0, columnspan=2, sticky="ew", pady=(10, 0))
        status_frame.columnconfigure(0, weight=1)
        self.progress = ttk.Progressbar(status_frame, mode="determinate", maximum=100)
        self.progress.grid(row=0, column=0, sticky="ew", padx=5)
        ttk.Label(status_frame, textvariable=self.status_var).grid(row=1, column=0, sticky="w", padx=5, pady=(5, 0))

        # Fila 9 - Log
        log_frame = ttk.LabelFrame(main, text="Eventos")
        log_frame.grid(row=9, column=0, columnspan=2, sticky="nsew", pady=(10, 0))
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)

        self.log_text = tk.Text(log_frame, height=10, wrap="word", state="disabled")
        self.log_text.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log_text.configure(yscrollcommand=scrollbar.set)

        # Previsualizacion
        preview_frame = ttk.LabelFrame(main, text="Previsualizacion (limite configurable)")
        preview_frame.grid(row=10, column=0, columnspan=2, sticky="nsew", pady=(10, 0))
        preview_frame.columnconfigure(0, weight=1)
        preview_frame.rowconfigure(1, weight=1)

        preview_controls = ttk.Frame(preview_frame)
        preview_controls.grid(row=0, column=0, sticky="ew", padx=5, pady=5)
        preview_controls.columnconfigure(3, weight=1)
        ttk.Label(preview_controls, text="Filas a mostrar:").grid(row=0, column=0, sticky="w")
        self.spin_preview_rows = ttk.Spinbox(preview_controls, from_=1, to=PREVIEW_MAX_DISPLAY, textvariable=self.preview_rows_var, width=6)
        self.spin_preview_rows.grid(row=0, column=1, sticky="w", padx=(5, 15))
        ttk.Label(preview_controls, textvariable=self.preview_info_var).grid(row=0, column=2, sticky="w")

        tree_container = ttk.Frame(preview_frame)
        tree_container.grid(row=1, column=0, sticky="nsew", padx=5, pady=(0, 5))
        tree_container.columnconfigure(0, weight=1)
        tree_container.rowconfigure(0, weight=1)

        self.preview_tree = ttk.Treeview(tree_container, show="headings", selectmode="browse")
        self.preview_tree.grid(row=0, column=0, sticky="nsew")
        scroll_y = ttk.Scrollbar(tree_container, orient="vertical", command=self.preview_tree.yview)
        scroll_y.grid(row=0, column=1, sticky="ns")
        scroll_x = ttk.Scrollbar(tree_container, orient="horizontal", command=self.preview_tree.xview)
        scroll_x.grid(row=1, column=0, sticky="ew")
        self.preview_tree.configure(yscrollcommand=scroll_y.set, xscrollcommand=scroll_x.set)

        self._on_format_change()

    # ------------------------------------------------------------------
    # Event handlers
    def _on_format_change(self, *_args) -> None:
        fmt = self.format_var.get()
        current = self.output_var.get().strip()
        if fmt == "csv":
            self.entry_csv_sep.configure(state="normal")
            if not self.csv_separator_var.get():
                self.csv_separator_var.set(DEFAULT_CSV_SEPARATOR)
        else:
            self.entry_csv_sep.configure(state="disabled")
        if current:
            path = Path(current)
            self.output_var.set(str(path.with_suffix(f".{fmt}")))
        else:
            self.output_var.set(str(self._default_output(fmt)))

    def _select_output(self) -> None:
        fmt = self.format_var.get()
        current = self.output_var.get().strip()
        initial_path = Path(current) if current else self._default_output(fmt)
        filetypes = [
            ("Excel (*.xlsx)", "*.xlsx"),
            ("CSV (*.csv)", "*.csv"),
            ("PDF (*.pdf)", "*.pdf"),
        ]
        initialdir = str(initial_path.parent if initial_path.parent.exists() else Path.cwd())
        filename = filedialog.asksaveasfilename(
            parent=self.root,
            title="Guardar como",
            defaultextension=f".{fmt}",
            filetypes=filetypes,
            initialdir=initialdir,
            initialfile=initial_path.name,
        )
        if filename:
            self.output_var.set(filename)

    def _on_preview(self) -> None:
        config = self._collect_inputs(require_output=False)
        if config is None:
            return
        self._start_run(config, mode="preview")

    def _on_execute(self) -> None:
        config = self._collect_inputs(require_output=True)
        if config is None:
            return
        self._start_run(config, mode="export")

    # ------------------------------------------------------------------
    # Helpers
    def _collect_inputs(self, require_output: bool) -> RunConfig | None:
        organization = self.org_var.get().strip()
        project = self.project_var.get().strip()
        team_text = self.team_var.get().strip()
        query_id = self.query_id_var.get().strip()
        token = self.token_var.get().strip()
        fmt = self.format_var.get().strip()
        output_text = self.output_var.get().strip()
        csv_separator = self.csv_separator_var.get()
        preview_limit_text = self.preview_rows_var.get().strip()

        if not organization:
            messagebox.showerror(APP_NAME, "Ingresa la organizacion.")
            return None
        project_value = project or None
        if project_value is None and team_text:
            messagebox.showerror(APP_NAME, "Si dejas el proyecto vacio, la ruta de equipo tambien debe estar vacia.")
            return None
        if not query_id:
            messagebox.showerror(APP_NAME, "Ingresa el Query ID.")
            return None
        if not GUID_RE.match(query_id):
            messagebox.showerror(APP_NAME, "El Query ID debe ser un GUID valido.")
            return None
        if not token:
            messagebox.showerror(APP_NAME, "Ingresa el Personal Access Token.")
            return None
        if fmt not in SUPPORTED_FORMATS:
            messagebox.showerror(APP_NAME, "Selecciona un formato de salida valido.")
            return None

        if fmt == "csv":
            if not csv_separator:
                messagebox.showerror(APP_NAME, "Ingresa un separador para CSV.")
                return None
        else:
            csv_separator = DEFAULT_CSV_SEPARATOR

        if not output_text:
            default_path = self._default_output(fmt)
            output_text = str(default_path)
            if require_output:
                self.output_var.set(output_text)
        output_path = Path(output_text).expanduser().with_suffix(f".{fmt}") if require_output else None

        try:
            preview_limit = int(preview_limit_text)
        except ValueError:
            messagebox.showerror(APP_NAME, "El limite de previsualizacion debe ser numerico.")
            return None
        if preview_limit <= 0:
            messagebox.showerror(APP_NAME, "El limite de previsualizacion debe ser mayor que cero.")
            return None
        if preview_limit > PREVIEW_MAX_DISPLAY:
            preview_limit = PREVIEW_MAX_DISPLAY
            self.preview_rows_var.set(str(PREVIEW_MAX_DISPLAY))

        team_segments = [segment.strip() for segment in team_text.split("/") if segment.strip()]
        context = QueryContext(
            organization=organization,
            project=project_value,
            team_segments=team_segments,
            query_id=query_id,
        )

        return RunConfig(
            context=context,
            token=token,
            fmt=fmt,
            output_path=output_path,
            csv_separator=csv_separator,
            preview_limit=preview_limit,
        )

    def _start_run(self, config: RunConfig, mode: str) -> None:
        if self.thread and self.thread.is_alive():
            messagebox.showwarning(APP_NAME, "Ya hay una operacion en ejecucion.")
            return

        self._prepare_run()

        def worker() -> None:
            try:
                def progress_cb(done: int, total: int) -> None:
                    self._async(lambda: self._update_progress(done, total))

                self._log("Consultando Azure DevOps...")
                df = obtener_resultados(config.context, config.token, progress_cb)

                if df.empty:
                    msg = "La consulta no devolvio elementos."
                    self._log(msg)
                    self._async(lambda: self._finish(msg, success=False, popup=(mode == "export")))
                    if mode == "preview":
                        self._async(lambda: self._show_preview(pd.DataFrame(), config.preview_limit))
                    return

                self._log(f"Filas recibidas: {len(df)}")

                if mode == "preview":
                    self._async(lambda: self._show_preview(df, config.preview_limit))
                    self._async(lambda: self._finish("Previsualizacion lista.", success=True, popup=False))
                else:
                    assert config.output_path is not None
                    exportar(df, config.output_path, config.fmt, config.csv_separator)
                    msg = f"Archivo generado: {config.output_path}"
                    self._log(msg)
                    self._async(lambda: self._finish(msg, success=True))
            except AzureQueryError as exc:
                err = str(exc)
                self._log(f"ERROR: {err}")
                self._async(lambda: self._finish(err, success=False))
            except Exception as exc:  # pragma: no cover - defensivo
                err = f"Error inesperado: {exc}"
                self._log(err)
                self._async(lambda: self._finish(err, success=False))
            finally:
                self._async(lambda: self._set_running(False))
                self.thread = None

        self.thread = threading.Thread(target=worker, daemon=True)
        self.thread.start()

    def _prepare_run(self) -> None:
        self._clear_log()
        self.status_var.set("Procesando...")
        self._set_running(True)
        self._update_progress(0, 0)

    def _set_running(self, running: bool) -> None:
        state = "disabled" if running else "normal"
        self.btn_run.configure(state=state)
        self.btn_preview.configure(state=state)
        self.btn_browse.configure(state=state)
        self.combo_format.configure(state="disabled" if running else "readonly")
        self.entry_csv_sep.configure(state="disabled" if (running or self.format_var.get() != "csv") else "normal")
        if running:
            self.progress.start(10)
        else:
            self.progress.stop()

    def _finish(self, message: str, success: bool, popup: bool = True) -> None:
        self.status_var.set(message)
        if popup:
            if success:
                messagebox.showinfo(APP_NAME, message)
            else:
                messagebox.showerror(APP_NAME, message)

    def _log(self, message: str) -> None:
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.log_queue.put(f"[{timestamp}] {message}")

    def _clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _schedule_log_pump(self) -> None:
        try:
            while True:
                entry = self.log_queue.get_nowait()
                self.log_text.configure(state="normal")
                self.log_text.insert("end", entry + "\n")
                lines = int(self.log_text.index("end-1c").split(".")[0])
                if lines > LOG_MAX_LINES:
                    self.log_text.delete("1.0", f"{lines - LOG_MAX_LINES}.0")
                self.log_text.see("end")
                self.log_text.configure(state="disabled")
        except queue.Empty:
            pass
        finally:
            self.root.after(200, self._schedule_log_pump)

    def _update_progress(self, done: int, total: int) -> None:
        if total <= 0:
            self.progress.configure(mode="indeterminate", maximum=100)
            return
        self.progress.stop()
        self.progress.configure(mode="determinate", maximum=total)
        self.progress["value"] = done

    def _show_preview(self, df: pd.DataFrame, limit: int) -> None:
        if self.preview_tree is None:
            return
        self.preview_tree.delete(*self.preview_tree.get_children())
        columns = list(df.columns)
        if not columns:
            self.preview_tree["columns"] = ("Sin datos",)
            self.preview_tree.heading("Sin datos", text="Sin datos")
            self.preview_tree.column("Sin datos", width=200, anchor="w")
            self.preview_info_var.set("Sin datos cargados.")
            return

        self.preview_tree["columns"] = columns
        for col in columns:
            self.preview_tree.heading(col, text=col)
            self.preview_tree.column(col, width=150, anchor="w")

        max_rows = min(len(df), limit)
        for idx in range(max_rows):
            row = df.iloc[idx]
            values = ["" if pd.isna(row[col]) else str(row[col]) for col in columns]
            self.preview_tree.insert("", "end", values=values)

        self.preview_info_var.set(f"Filas totales: {len(df)} | mostrando {max_rows}")

    def _default_output(self, fmt: str) -> Path:
        return Path.cwd() / f"azure_query_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{fmt}"

    def _async(self, func: Callable[[], None]) -> None:
        self.root.after(0, func)


# ----------------------------------------------------------------------
# Llamadas a la API de Azure DevOps

def obtener_resultados(
    ctx: QueryContext,
    token: str,
    progress_cb: Callable[[int, int], None] | None = None,
) -> pd.DataFrame:
    session = requests.Session()
    session.auth = ("", token)
    session.headers.update({"Accept": "application/json"})

    wiql_url = f"{ctx.api_base()}/_apis/wit/wiql/{ctx.query_id}"
    wiql_resp = session.get(wiql_url, params={"api-version": API_VERSION}, timeout=60)
    validar_respuesta(wiql_resp, "No fue posible recuperar la definicion del query")
    wiql_data = cargar_json(wiql_resp, "No fue posible interpretar la definicion del query")

    work_items = wiql_data.get("workItems", []) or []
    relations = wiql_data.get("workItemRelations", []) or []

    columns = wiql_data.get("columns", [])
    field_order, header_map = preparar_columnas(columns)

    ids = extraer_identificadores(work_items, relations)
    if not ids:
        if progress_cb:
            progress_cb(0, 0)
        return pd.DataFrame()
    registros = recolectar_work_items(session, ctx, ids, field_order, progress_cb)

    if not registros:
        return pd.DataFrame()

    datos: List[Dict[str, object]] = []
    index_por_id: Dict[int, Dict[str, object]] = {}
    for registro in registros:
        fila: Dict[str, object] = {}
        for ref in field_order:
            clave = header_map.get(ref, ref)
            valor = normalizar_valor(recuperar_valor_campo(ref, registro))
            fila[clave] = valor
        datos.append(fila)
        try:
            reg_id = int(recuperar_valor_campo("System.Id", registro) or registro.get("id"))
        except (TypeError, ValueError):
            reg_id = None
        if reg_id is not None and reg_id not in index_por_id:
            index_por_id[reg_id] = fila

    if relations:
        filas_rel: List[Dict[str, object]] = []
        for relacion in relations:
            if not isinstance(relacion, dict):
                continue
            target = relacion.get("target")
            if not isinstance(target, dict):
                continue
            target_id = target.get("id")
            if target_id is None:
                continue
            try:
                target_id_int = int(target_id)
            except (TypeError, ValueError):
                continue
            fila_base = index_por_id.get(target_id_int)
            if fila_base is None:
                continue
            fila_copia = dict(fila_base)
            atributos = relacion.get("attributes") or {}
            if "recurseLevel" in atributos:
                fila_copia.setdefault("TreeLevel", atributos.get("recurseLevel"))
            source = relacion.get("source")
            if isinstance(source, dict) and source.get("id") is not None:
                fila_copia.setdefault("ParentId", source.get("id"))
            rel_type = relacion.get("rel")
            if rel_type:
                fila_copia.setdefault("LinkType", rel_type)
            filas_rel.append(fila_copia)
        if filas_rel:
            datos = filas_rel

    df = pd.DataFrame(datos)
    return df


def extraer_identificadores(work_items: Sequence[Dict[str, object]], relations: Sequence[Dict[str, object]]) -> List[int]:
    ids: List[int] = []
    vistos: set[int] = set()

    def registrar(valor: object) -> None:
        if valor is None:
            return
        try:
            wid = int(valor)
        except (TypeError, ValueError):
            return
        if wid not in vistos:
            vistos.add(wid)
            ids.append(wid)

    for item in work_items:
        if isinstance(item, dict):
            registrar(item.get("id"))
    for relacion in relations:
        if not isinstance(relacion, dict):
            continue
        target = relacion.get("target")
        if isinstance(target, dict):
            registrar(target.get("id"))
        source = relacion.get("source")
        if isinstance(source, dict):
            registrar(source.get("id"))

    return ids

def preparar_columnas(columns: Sequence[Dict[str, object]]) -> tuple[List[str], Dict[str, str]]:
    orden: List[str] = []
    encabezados: Dict[str, str] = {}
    usados: Dict[str, int] = {}

    def registrar(ref: str, nombre: str) -> None:
        if ref in orden:
            return
        base = nombre or ref
        contador = usados.get(base, 0)
        etiqueta = base if contador == 0 else f"{base} ({contador + 1})"
        usados[base] = contador + 1
        encabezados[ref] = etiqueta
        orden.append(ref)

    for columna in columns:
        ref = columna.get("referenceName")
        nombre = columna.get("name")
        if isinstance(ref, str):
            registrar(ref, nombre if isinstance(nombre, str) and nombre else ref)

    if "System.Id" not in orden:
        registrar("System.Id", "ID")

    return orden, encabezados


def recolectar_work_items(
    session: requests.Session,
    ctx: QueryContext,
    ids: Sequence[int],
    fields: Sequence[str],
    progress_cb: Callable[[int, int], None] | None = None,
) -> List[Dict[str, object]]:
    registros: List[Dict[str, object]] = []
    url = f"{ctx.api_base()}/_apis/wit/workitemsbatch"
    total = len(ids)
    done = 0
    if progress_cb:
        progress_cb(0, total)
    for chunk in dividir(ids, MAX_BATCH):
        payload = {"ids": chunk, "fields": list(fields)}
        resp = session.post(url, params={"api-version": API_VERSION}, json=payload, timeout=60)
        validar_respuesta(resp, "No fue posible recuperar los work items")
        data = cargar_json(resp, "No fue posible interpretar los work items")
        valores = data.get("value", [])
        for item in valores:
            if isinstance(item, dict):
                registros.append(item)
        done += len(chunk)
        if progress_cb:
            progress_cb(done, total)
    return registros


def dividir(sequence: Sequence[int], tamano: int) -> Iterable[List[int]]:
    acumulado: List[int] = []
    for elemento in sequence:
        acumulado.append(elemento)
        if len(acumulado) >= tamano:
            yield acumulado
            acumulado = []
    if acumulado:
        yield acumulado


def validar_respuesta(resp: requests.Response, mensaje_error: str) -> None:
    if resp.ok:
        return
    detalle = extraer_detalle_error(resp)
    raise AzureQueryError(f"{mensaje_error}. Detalle: {detalle}")


def cargar_json(resp: requests.Response, contexto: str):
    try:
        return resp.json()
    except ValueError as exc:
        snippet = resp.text[:500].strip()
        status = resp.status_code
        detalle = snippet if snippet else f'HTTP {status} sin contenido'
        raise AzureQueryError(f"{contexto}. Respuesta no es JSON valido. Detalle: {detalle}") from exc


def extraer_detalle_error(resp: requests.Response) -> str:
    try:
        data = resp.json()
        if isinstance(data, dict):
            return data.get("message") or data.get("value") or json.dumps(data)
        return json.dumps(data)
    except ValueError:
        return resp.text[:500]


def recuperar_valor_campo(ref: str, item: Dict[str, object]) -> object:
    if ref == "System.Id":
        return item.get("id")
    fields = item.get("fields", {})
    if isinstance(fields, dict):
        return fields.get(ref)
    return None


def normalizar_valor(valor: object) -> object:
    if isinstance(valor, dict):
        for clave in ("displayName", "name", "value", "id"):
            contenido = valor.get(clave) if isinstance(valor, dict) else None
            if contenido:
                return contenido
        return json.dumps(valor, ensure_ascii=False)
    if isinstance(valor, list):
        return ", ".join(str(normalizar_valor(elemento)) for elemento in valor)
    return valor


def exportar(df: pd.DataFrame, ruta: Path, fmt: str, csv_separator: str = ",") -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "csv":
        df.to_csv(ruta, index=False, encoding="utf-8-sig", sep=csv_separator)
    elif fmt == "xlsx":
        df.to_excel(ruta, index=False)
    elif fmt == "pdf":
        exportar_pdf(df, ruta)
    else:
        raise AzureQueryError(f"Formato no soportado: {fmt}")


def exportar_pdf(df: pd.DataFrame, ruta: Path) -> None:
    try:
        from reportlab.lib import colors
        from reportlab.lib.pagesizes import landscape, letter
        from reportlab.platypus import SimpleDocTemplate, Table, TableStyle
    except ImportError as exc:
        raise AzureQueryError("Para exportar a PDF instala reportlab (pip install reportlab).") from exc

    doc = SimpleDocTemplate(str(ruta), pagesize=landscape(letter))
    datos = [list(df.columns)] + df.fillna("").astype(str).values.tolist()
    tabla = Table(datos, repeatRows=1)
    tabla.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#003366")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.whitesmoke, colors.lightgrey]),
        ("GRID", (0, 0), (-1, -1), 0.25, colors.grey),
    ]))
    doc.build([tabla])


def main() -> None:
    root = tk.Tk()
    app = AzureDevOpsQueryApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()


