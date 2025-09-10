# -*- coding: utf-8 -*-
"""
amortizacion_gui_v2.py
----------------------
Mejora: Asistente visual de mora.
- Botón "Asistente de mora..." que permite introducir días de atraso por cuota con Spinbox.
- Al aplicar, rellena el campo "Atrasos" en formato 1=10;3=5 automáticamente.
- Tips y placehoder aclaratorios en la UI.

Resto: Igual que la versión anterior (EA/EM, cadencias, exporta HTML/CSV/Excel/MD, logs, barra de progreso,
cancelar, vista previa, procesamiento en hilo, offline-first).
"""

from __future__ import annotations

import os
import sys
import math
import queue
import threading
import time
from datetime import datetime, timedelta
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# === Dependencias de datos ===
try:
    import pandas as pd
    import numpy as np
except Exception as e:  # pragma: no cover
    raise RuntimeError(
        "Falta instalar dependencias. Ejecute en Windows: "
        "pip install pandas numpy openpyxl pyarrow"
    ) from e

# === Logging con rotación ===
import logging
from logging.handlers import RotatingFileHandler

APP_NAME = "amortizacion_gui_v2"
LOG_FILE = os.path.join(os.path.expanduser("~"), f"{APP_NAME}.log")

logger = logging.getLogger(APP_NAME)
logger.setLevel(logging.INFO)

handler = RotatingFileHandler(LOG_FILE, maxBytes=5 * 1024 * 1024, backupCount=3, encoding="utf-8")
formatter = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")
handler.setFormatter(formatter)
if not logger.handlers:
    logger.addHandler(handler)

# === Utilidades ===

PERIODOS_ANIO = {
    "Semanal": 52,
    "Quincenal": 26,
    "Mensual": 12,
    "Semestral": 2,
    "Anual": 1,
}

def _add_months(d: datetime, months: int) -> datetime:
    year = d.year + (d.month - 1 + months) // 12
    month = (d.month - 1 + months) % 12 + 1
    day = min(d.day, [31,
                      29 if year % 4 == 0 and (year % 100 != 0 or year % 400 == 0) else 28,
                      31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1])
    return d.replace(year=year, month=month, day=day)

DELTA_CADENCIA = {
    "Semanal": lambda d: d + timedelta(weeks=1),
    "Quincenal": lambda d: d + timedelta(days=15),
    "Mensual": lambda d: _add_months(d, 1),
    "Semestral": lambda d: _add_months(d, 6),
    "Anual": lambda d: _add_months(d, 12),
}

def ea_to_period_rate(ea: float, cadencia: str) -> float:
    n = PERIODOS_ANIO[cadencia]
    return (1.0 + ea) ** (1.0 / n) - 1.0

def em_to_ea(em: float) -> float:
    return (1.0 + em) ** 12 - 1.0

def tasa_periodo(tasa_valor: float, tipo_tasa: str, cadencia: str) -> float:
    if tipo_tasa.upper() == "EA":
        return ea_to_period_rate(tasa_valor, cadencia)
    elif tipo_tasa.upper() == "EM":
        ea = em_to_ea(tasa_valor)
        return ea_to_period_rate(ea, cadencia)
    else:
        raise ValueError("Tipo de tasa no soportado. Use 'EA' o 'EM'.")

def tasa_mora_por_dias(ea_mora: float, dias_mora: int) -> float:
    return (1.0 + ea_mora) ** (dias_mora / 365.0) - 1.0

@dataclass
class Parametros:
    monto: float
    tipo_tasa: str  # 'EA' o 'EM'
    tasa: float  # decimal
    cadencia: str  # Semanal/Quincenal/Mensual/Semestral/Anual
    n_cuotas: int
    fecha_inicio: datetime
    ea_mora: float  # tasa de mora efectiva anual (decimal)
    cargo_fijo_mora: float  # COP por evento
    atrasos: Dict[int, int]  # {cuota: dias}
    carpeta_salida: str
    export_html: bool
    export_csv: bool
    export_excel: bool
    export_md: bool

class AmortizacionCalculator:
    def __init__(self, params: Parametros, cancel_event: threading.Event, progress_q: queue.Queue):
        self.p = params
        self.cancel_event = cancel_event
        self.progress_q = progress_q

    def _emit_progress(self, step: int, total: int):
        pct = int(step * 100 / max(total, 1))
        self.progress_q.put(("progress", pct))

    def calcular(self) -> pd.DataFrame:
        logger.info("Inicio cálculo de amortización.")
        P = self.p.monto
        n = self.p.n_cuotas
        i = tasa_periodo(self.p.tasa, self.p.tipo_tasa, self.p.cadencia)

        if i <= -1.0:
            raise ValueError("La tasa por periodo es inválida (<= -100%). Verifique parámetros.")

        if i == 0:
            cuota = P / n
        else:
            cuota = P * (i) / (1 - (1 + i) ** (-n))

        fechas: List[datetime] = []
        fecha = self.p.fecha_inicio
        for k in range(n):
            # primer vencimiento = fecha_inicio + delta(cadencia)
            fecha = DELTA_CADENCIA[self.p.cadencia](fecha)
            fechas.append(fecha)

        saldo = P
        rows: List[Dict] = []
        total_steps = n
        for k in range(1, n + 1):
            if self.cancel_event.is_set():
                logger.warning("Cálculo cancelado por el usuario.")
                raise RuntimeError("Proceso cancelado.")

            interes = saldo * i
            abono_capital = cuota - interes
            if k == n:
                abono_capital = saldo
                cuota_ajustada = interes + abono_capital
            else:
                cuota_ajustada = cuota

            saldo = max(0.0, saldo - abono_capital)

            dias_mora = self.p.atrasos.get(k, 0)
            mora_interes = 0.0
            cargo_fijo = 0.0
            if dias_mora > 0:
                factor_mora = tasa_mora_por_dias(self.p.ea_mora, dias_mora)
                mora_interes = cuota_ajustada * factor_mora
                cargo_fijo = self.p.cargo_fijo_mora

            fecha_cuota = fechas[k - 1]
            dias_desde_inicio = (fecha_cuota - self.p.fecha_inicio).days
            semanas_desde_inicio = dias_desde_inicio // 7
            meses_desde_inicio = (fecha_cuota.year - self.p.fecha_inicio.year) * 12 + (fecha_cuota.month - self.p.fecha_inicio.month)
            anios_desde_inicio = meses_desde_inicio / 12.0

            rows.append({
                "Cuota": k,
                "Fecha vencimiento": fecha_cuota.date().isoformat(),
                "Días desde inicio": dias_desde_inicio,
                "Semanas desde inicio": semanas_desde_inicio,
                "Meses desde inicio": meses_desde_inicio,
                "Años desde inicio": round(anios_desde_inicio, 4),
                "Saldo inicial": round(saldo + abono_capital, 2),
                "Interés periodo": round(interes, 2),
                "Abono a capital": round(abono_capital, 2),
                "Cuota (sin mora)": round(cuota_ajustada, 2),
                "Mora interés": round(mora_interes, 2),
                "Mora cargo fijo": round(cargo_fijo, 2),
                "Cuota total a pagar": round(cuota_ajustada + mora_interes + cargo_fijo, 2),
                "Saldo final": round(saldo, 2),
                "Días mora": dias_mora,
            })

            self._emit_progress(k, total_steps)
            time.sleep(0.003)

        df = pd.DataFrame(rows)
        logger.info("Cálculo finalizado.")
        return df

    def exportar(self, df: pd.DataFrame) -> Dict[str, str]:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        base = f"amortizacion_{ts}"
        rutas = {}

        os.makedirs(self.p.carpeta_salida, exist_ok=True)

        resumen = {
            "Monto": self.p.monto,
            "Cadencia": self.p.cadencia,
            "Tipo tasa": self.p.tipo_tasa,
            "Tasa declarada": self.p.tasa,
            "Nº cuotas": self.p.n_cuotas,
            "Fecha inicio": self.p.fecha_inicio.date().isoformat(),
            "EA mora": self.p.ea_mora,
            "Cargo fijo mora": self.p.cargo_fijo_mora,
        }

        if self.p.export_csv:
            ruta = os.path.join(self.p.carpeta_salida, base + ".csv")
            df.to_csv(ruta, index=False, encoding="utf-8-sig")
            rutas["csv"] = ruta
            logger.info(f"CSV exportado: {ruta}")

        if self.p.export_excel:
            ruta = os.path.join(self.p.carpeta_salida, base + ".xlsx")
            with pd.ExcelWriter(ruta, engine="openpyxl") as w:
                df.to_excel(w, index=False, sheet_name="amortizacion")
                pd.DataFrame([resumen]).to_excel(w, index=False, sheet_name="resumen")
            rutas["xlsx"] = ruta
            logger.info(f"Excel exportado: {ruta}")

        if self.p.export_md:
            ruta = os.path.join(self.p.carpeta_salida, base + ".md")
            with open(ruta, "w", encoding="utf-8") as f:
                f.write("# Tabla de amortización\n\n")
                for k, v in resumen.items():
                    f.write(f"- **{k}**: {v}\n")
                f.write("\n\n")
                f.write(df.to_markdown(index=False))
            rutas["md"] = ruta
            logger.info(f"Markdown exportado: {ruta}")

        if self.p.export_html:
            ruta = os.path.join(self.p.carpeta_salida, base + ".html")
            style = (
                "<style>"
                "body{font-family:Segoe UI,Arial,sans-serif;margin:20px;}"
                "table{border-collapse:collapse;width:100%;}"
                "th,td{border:1px solid #ddd;padding:8px;text-align:right;}"
                "th{text-align:center;background:#f2f2f2;position:sticky;top:0;}"
                "tr:nth-child(even){background:#fafafa;}"
                ".title{font-size:18px;margin-bottom:10px;}"
                ".meta{margin:10px 0 20px 0;}"
                ".meta span{display:inline-block;margin-right:15px;}"
                "</style>"
            )
            resumen_html = "".join([f"<span><b>{k}:</b> {v}</span>" for k, v in resumen.items()])
            html = f"<html><head><meta charset='utf-8'>{style}</head><body>"
            html += "<div class='title'><b>Tabla de amortización</b></div>"
            html += f"<div class='meta'>{resumen_html}</div>"
            html += df.to_html(index=False, justify='center')
            html += "</body></html>"
            with open(ruta, "w", encoding="utf-8") as f:
                f.write(html)
            rutas["html"] = ruta
            logger.info(f"HTML exportado: {ruta}")

        return rutas


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Amortización con Mora - Tkinter (v2)")
        self.geometry("1150x760")
        self.minsize(1000, 680)

        self.cancel_event = threading.Event()
        self.progress_q: "queue.Queue[Tuple[str, int]]" = queue.Queue()
        self.worker: Optional[threading.Thread] = None

        # Variables GUI
        self.var_monto = tk.StringVar(value="1000000")
        self.var_tipo_tasa = tk.StringVar(value="EA")
        self.var_tasa = tk.StringVar(value="0.25")
        self.var_cadencia = tk.StringVar(value="Mensual")
        self.var_n_cuotas = tk.StringVar(value="12")
        self.var_fecha_inicio = tk.StringVar(value=datetime.now().date().isoformat())
        self.var_ea_mora = tk.StringVar(value="0.36")
        self.var_cargo_fijo = tk.StringVar(value="0")
        self.var_atrasos = tk.StringVar(value="")  # ejemplo: 1=10;3=5
        self.var_out_html = tk.BooleanVar(value=True)
        self.var_out_csv = tk.BooleanVar(value=True)
        self.var_out_excel = tk.BooleanVar(value=False)
        self.var_out_md = tk.BooleanVar(value=False)
        self.var_carpeta = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "AmortizacionSalida"))

        self._build_ui()
        self.after(100, self._poll_progress)

    def _build_ui(self):
        frm = ttk.Frame(self, padding=10)
        frm.pack(fill="both", expand=True)

        # --- Parámetros ---
        box = ttk.LabelFrame(frm, text="Parámetros del cálculo")
        box.pack(fill="x", pady=5)

        def add_row(parent, r, label, widget):
            ttk.Label(parent, text=label).grid(row=r, column=0, sticky="w", padx=5, pady=4)
            widget.grid(row=r, column=1, sticky="ew", padx=5, pady=4)

        box.columnconfigure(1, weight=1)
        add_row(box, 0, "Monto (COP):", ttk.Entry(box, textvariable=self.var_monto))
        add_row(box, 1, "Tipo de tasa:", ttk.Combobox(box, textvariable=self.var_tipo_tasa, values=["EA", "EM"], state="readonly"))
        add_row(box, 2, "Tasa (decimal, p.ej. 0.25):", ttk.Entry(box, textvariable=self.var_tasa))
        add_row(box, 3, "Cadencia:", ttk.Combobox(box, textvariable=self.var_cadencia, values=list(PERIODOS_ANIO.keys()), state="readonly"))
        add_row(box, 4, "Nº de cuotas:", ttk.Entry(box, textvariable=self.var_n_cuotas))
        add_row(box, 5, "Fecha inicio (YYYY-MM-DD):", ttk.Entry(box, textvariable=self.var_fecha_inicio))

        # --- Mora ---
        mora = ttk.LabelFrame(frm, text="Penalización por mora (si hay atrasos)")
        mora.pack(fill="x", pady=5)
        ttk.Label(mora, text="EA mora (decimal, ej. 0.36 = 36% EA):").grid(row=0, column=0, sticky="w", padx=5, pady=4)
        ttk.Entry(mora, textvariable=self.var_ea_mora).grid(row=0, column=1, sticky="ew", padx=5, pady=4)
        ttk.Label(mora, text="Cargo fijo por evento (COP):").grid(row=1, column=0, sticky="w", padx=5, pady=4)
        ttk.Entry(mora, textvariable=self.var_cargo_fijo).grid(row=1, column=1, sticky="ew", padx=5, pady=4)

        # Atrasos
        atrasos_frame = ttk.Frame(mora)
        atrasos_frame.grid(row=2, column=0, columnspan=2, sticky="ew", padx=5, pady=4)
        atrasos_frame.columnconfigure(1, weight=1)
        ttk.Label(atrasos_frame, text="Atrasos (formato 1=10;3=5):").grid(row=0, column=0, sticky="w")
        entry_atrasos = ttk.Entry(atrasos_frame, textvariable=self.var_atrasos)
        entry_atrasos.grid(row=0, column=1, sticky="ew", padx=(5, 5))
        ttk.Button(atrasos_frame, text="Asistente de mora...", command=self._assistant_mora).grid(row=0, column=2, padx=5)

        ttk.Label(mora, foreground="#666",
                  text="TIP: '1=10;3=5' significa: cuota 1 con 10 días de atraso, cuota 3 con 5 días. Si no hay atrasos, déjalo vacío."
                  ).grid(row=3, column=0, columnspan=2, sticky="w", padx=5, pady=(0,6))

        # --- Salida ---
        out = ttk.LabelFrame(frm, text="Salida")
        out.pack(fill="x", pady=5)
        ttk.Checkbutton(out, text="HTML", variable=self.var_out_html).grid(row=0, column=0, padx=5, pady=5, sticky="w")
        ttk.Checkbutton(out, text="CSV", variable=self.var_out_csv).grid(row=0, column=1, padx=5, pady=5, sticky="w")
        ttk.Checkbutton(out, text="Excel", variable=self.var_out_excel).grid(row=0, column=2, padx=5, pady=5, sticky="w")
        ttk.Checkbutton(out, text="Markdown", variable=self.var_out_md).grid(row=0, column=3, padx=5, pady=5, sticky="w")
        ttk.Label(out, text="Carpeta de salida:").grid(row=1, column=0, padx=5, pady=5, sticky="w")
        ttk.Entry(out, textvariable=self.var_carpeta).grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        ttk.Button(out, text="Examinar...", command=self._sel_carpeta).grid(row=1, column=2, padx=5, pady=5, sticky="w")
        out.columnconfigure(1, weight=1)

        # --- Botones ---
        btns = ttk.Frame(frm)
        btns.pack(fill="x", pady=5)
        ttk.Button(btns, text="Calcular", command=self._run).pack(side="left", padx=5)
        ttk.Button(btns, text="Cancelar", command=self._cancel).pack(side="left", padx=5)

        # --- Progreso ---
        prog = ttk.Frame(frm)
        prog.pack(fill="x", pady=5)
        self.pb = ttk.Progressbar(prog, orient="horizontal", mode="determinate", maximum=100)
        self.pb.pack(fill="x", padx=5, pady=5)
        self.var_eta = tk.StringVar(value="ETA: --")
        ttk.Label(prog, textvariable=self.var_eta).pack(side="right", padx=5)

        # --- Vista previa ---
        prev = ttk.LabelFrame(frm, text="Vista previa (primeras 20 filas)")
        prev.pack(fill="both", expand=True, pady=5)
        self.tree = ttk.Treeview(prev, columns=(), show="headings")
        self.tree.pack(fill="both", expand=True, padx=5, pady=5)

        # --- Logs ---
        logs = ttk.LabelFrame(frm, text=f"Logs (archivo: {LOG_FILE})")
        logs.pack(fill="both", expand=False, pady=5)
        self.txt_log = tk.Text(logs, height=8, wrap="word")
        self.txt_log.pack(fill="both", expand=True, padx=5, pady=5)
        self._log_to_panel("Aplicación iniciada.")

    # ---------- Asistente de mora ----------
    def _assistant_mora(self):
        """Ventana para capturar días de atraso por cuota con Spinbox."""
        try:
            n = int(self.var_n_cuotas.get())
            if n <= 0:
                raise ValueError
        except Exception:
            messagebox.showwarning("Atrasos", "Primero indique un Nº de cuotas válido (>0).")
            return

        win = tk.Toplevel(self)
        win.title("Asistente de mora")
        win.geometry("420x520")
        win.transient(self)
        win.grab_set()

        ttk.Label(win, text="Días de atraso por cuota (0 = sin atraso)").pack(anchor="w", padx=10, pady=(10,5))
        canvas = tk.Canvas(win)
        frm = ttk.Frame(canvas)
        vsb = ttk.Scrollbar(win, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)
        canvas.create_window((0,0), window=frm, anchor="nw")

        spins: List[tk.Spinbox] = []
        for k in range(1, n+1):
            row = ttk.Frame(frm)
            row.pack(fill="x", padx=10, pady=2)
            ttk.Label(row, text=f"Cuota {k}", width=12).pack(side="left")
            sb = tk.Spinbox(row, from_=0, to=3650, width=8)
            sb.delete(0, "end")
            # Si el campo ya tiene atrasos, precargar
            dias_prev = 0
            try:
                txt = self.var_atrasos.get().strip()
                if txt:
                    dic = {}
                    for par in txt.replace(",", ";").split(";"):
                        if "=" in par:
                            a,b = par.split("=",1)
                            dic[int(a.strip())] = int(b.strip())
                    dias_prev = dic.get(k, 0)
            except Exception:
                dias_prev = 0
            sb.insert(0, str(dias_prev))
            sb.pack(side="left")
            spins.append(sb)

        def on_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
        frm.bind("<Configure>", on_configure)

        btns = ttk.Frame(win)
        btns.pack(fill="x", padx=10, pady=10)
        def apply_and_close():
            pares = []
            for idx, sb in enumerate(spins, start=1):
                try:
                    d = int(sb.get())
                    if d > 0:
                        pares.append(f"{idx}={d}")
                except Exception:
                    pass
            self.var_atrasos.set(";".join(pares))
            win.destroy()

        ttk.Button(btns, text="Aplicar", command=apply_and_close).pack(side="left")
        ttk.Button(btns, text="Cancelar", command=win.destroy).pack(side="right")

    # ---------- Utilidades GUI ----------
    def _log_to_panel(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.txt_log.insert("end", f"[{ts}] {msg}\n")
        self.txt_log.see("end")

    def _sel_carpeta(self):
        path = filedialog.askdirectory(title="Seleccione carpeta de salida")
        if path:
            self.var_carpeta.set(path)

    def _parse_params(self) -> Parametros:
        try:
            monto = float(self.var_monto.get())
            tipo_tasa = self.var_tipo_tasa.get().strip().upper()
            tasa = float(self.var_tasa.get())
            cadencia = self.var_cadencia.get().strip()
            n_cuotas = int(self.var_n_cuotas.get())
            fecha_inicio = datetime.fromisoformat(self.var_fecha_inicio.get().strip())
            ea_mora = float(self.var_ea_mora.get())
            cargo_fijo = float(self.var_cargo_fijo.get())
            atrasos_txt = self.var_atrasos.get().strip()
            atrasos: Dict[int, int] = {}
            if atrasos_txt:
                for par in atrasos_txt.replace(",", ";").split(";"):
                    if "=" in par:
                        k, v = par.split("=", 1)
                        atrasos[int(k.strip())] = int(v.strip())
            carpeta = self.var_carpeta.get().strip()
            exp_html = bool(self.var_out_html.get())
            exp_csv = bool(self.var_out_csv.get())
            exp_excel = bool(self.var_out_excel.get())
            exp_md = bool(self.var_out_md.get())
        except Exception as e:
            raise ValueError(f"Error leyendo parámetros: {e}")

        if tipo_tasa not in {"EA", "EM"}:
            raise ValueError("Tipo de tasa inválido. Use 'EA' o 'EM'.")
        if cadencia not in PERIODOS_ANIO:
            raise ValueError("Cadencia inválida.")
        if n_cuotas <= 0:
            raise ValueError("El número de cuotas debe ser > 0.")
        if monto <= 0:
            raise ValueError("El monto debe ser > 0.")
        if not (exp_html or exp_csv or exp_excel or exp_md):
            raise ValueError("Seleccione al menos un formato de salida.")

        return Parametros(
            monto=monto,
            tipo_tasa=tipo_tasa,
            tasa=tasa,
            cadencia=cadencia,
            n_cuotas=n_cuotas,
            fecha_inicio=fecha_inicio,
            ea_mora=ea_mora,
            cargo_fijo_mora=cargo_fijo,
            atrasos=atrasos,
            carpeta_salida=carpeta,
            export_html=exp_html,
            export_csv=exp_csv,
            export_excel=exp_excel,
            export_md=exp_md,
        )

    def _run_worker(self, params: Parametros):
        t0 = time.time()
        try:
            calc = AmortizacionCalculator(params, self.cancel_event, self.progress_q)
            df = calc.calcular()
            rutas = calc.exportar(df)
            self._update_preview(df.head(20))
            msg = "Exportación completada:\n" + "\n".join([f"- {k.upper()}: {v}" for k, v in rutas.items()])
            logger.info(msg.replace("\n", " | "))
            self._log_to_panel(msg)
            messagebox.showinfo("Éxito", msg)
        except Exception as e:
            logger.exception("Fallo en el proceso.")
            self._log_to_panel(f"ERROR: {e}")
            messagebox.showerror("Error", str(e))
        finally:
            dt = time.time() - t0
            self.progress_q.put(("progress", 100))
            self.var_eta.set(f"ETA: {dt:.2f}s")
            self.worker = None
            self.cancel_event.clear()

    def _run(self):
        if self.worker and self.worker.is_alive():
            messagebox.showwarning("En ejecución", "Ya hay un proceso en ejecución.")
            return
        try:
            params = self._parse_params()
        except Exception as e:
            messagebox.showerror("Parámetros inválidos", str(e))
            return
        self.cancel_event.clear()
        self.pb["value"] = 0
        self.var_eta.set("ETA: --")
        self._log_to_panel("Iniciando cálculo...")
        self.worker = threading.Thread(target=self._run_worker, args=(params,), daemon=True)
        self.worker.start()

    def _cancel(self):
        if self.worker and self.worker.is_alive():
            self.cancel_event.set()
            self._log_to_panel("Cancelando...")
        else:
            self._log_to_panel("No hay proceso activo.")

    def _poll_progress(self):
        try:
            while True:
                kind, val = self.progress_q.get_nowait()
                if kind == "progress":
                    self.pb["value"] = val
        except queue.Empty:
            pass
        self.after(100, self._poll_progress)

    def _update_preview(self, df: pd.DataFrame):
        for col in self.tree["columns"]:
            self.tree.heading(col, text="")
        self.tree.delete(*self.tree.get_children())
        cols = list(df.columns)
        self.tree["columns"] = cols
        for c in cols:
            self.tree.heading(c, text=c)
            self.tree.column(c, width=120, anchor="e")
        for _, row in df.iterrows():
            vals = [row[c] for c in cols]
            self.tree.insert("", "end", values=vals)


def main():
    try:
        app = App()
        app.mainloop()
    except Exception as e:
        logger.exception("Error fatal en la aplicación.")
        print(f"Error fatal: {e}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
