# This cell writes the requested `build_dashboard.py` script to the sandbox so you can download it.
from pathlib import Path

script_path = Path("/mnt/data/build_dashboard.py")

script_code = r'''#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_dashboard.py
------------------
Genera un dashboard HTML autocontenido (100% offline) a partir de un .xlsx con columnas mínimas:
AÑO, MES (1-12), CODTAREAPADRE, PROVEEDOR, TIPO_TAREA, COSTO.

Características clave:
- GUI Tkinter (siempre se abre; sin consola/Batch).
- Hilos para no bloquear la UI; botón Cancelar.
- Progreso por etapas y panel de logs.
- Recuerda última ruta de archivo/carpeta en config.json (junto al script).
- HTML con filtros globales, KPIs, gráfico temporal (línea/área apilada/%), barras apiladas (Top N),
  pseudo-Pivot interactivo (Suma COSTO, variantes por MES y %), tabla detalle paginada,
  exportaciones CSV/PNG/Imprimir, formateo numérico es-CO (sin decimales).
- Resalta MoM > 50% (en rojo) por (CODTAREAPADRE, PROVEEDOR).

Nota: Para mantener el tamaño del script razonable y 100% offline, se implementa un motor
ligero de visualización con SVG/Canvas en JS nativo (sin Plotly). Las funciones de PNG,
stacking y "pivot" están re-implementadas. Si necesitas estrictamente Plotly.js y PivotTable.js
inline, puedo generar una variante “pesada” (multi-MB) compatible con PyInstaller.
"""

import argparse
import json
import logging
import os
import queue
import shutil
import sys
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

# Dependencias externas
import pandas as pd
from pandas import Timestamp

try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except Exception:
    ZoneInfo = None

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

APP_TITLE = "Generador de Dashboard de Costos (offline)"
CONFIG_FILE = "config.json"  # junto al script
REQUIRED_COLS = ["AÑO", "MES", "CODTAREAPADRE", "PROVEEDOR", "TIPO_TAREA", "COSTO"]

# ===========================
# Utilidades
# ===========================

def bogota_now_str():
    """Retorna timestamp YYYYMMDDHH24MISS en zona America/Bogota."""
    try:
        tz = ZoneInfo("America/Bogota") if ZoneInfo else None
    except Exception:
        tz = None
    now = datetime.now(tz) if tz else datetime.now()
    return now.strftime("%Y%m%d%H%M%S")

def safe_int(x):
    try:
        return int(x)
    except Exception:
        return None

def normalize_cols(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df.columns = [str(c).strip().upper() for c in df.columns]
    return df

def primeira_de_mes(year: int, month: int) -> str:
    try:
        return f"{int(year):04d}-{int(month):02d}-01"
    except Exception:
        return ""

def month_sort_key(y: int, m: int) -> int:
    return y * 100 + m

# ===========================
# Render HTML (plantilla)
# ===========================

HTML_TEMPLATE = r"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8"/>
<meta http-equiv="X-UA-Compatible" content="IE=edge"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Dashboard de Costos (offline)</title>
<style>
  :root {
    --bg: #0f172a;
    --panel: #111827;
    --muted: #64748b;
    --text: #e5e7eb;
    --accent: #22d3ee;
    --danger: #ef4444;
    --ok: #22c55e;
    --card: #0b1020;
    --chip: #1f2937;
    --border: #334155;
  }
  html, body { background: var(--bg); color: var(--text); font-family: system-ui, -apple-system, Segoe UI, Roboto, Ubuntu, Cantarell, "Helvetica Neue", Arial, "Noto Sans", "Apple Color Emoji", "Segoe UI Emoji"; margin:0; padding:0; }
  .wrap { max-width: 1400px; margin: 0 auto; padding: 16px 20px 40px; }
  h1 { font-size: 20px; margin: 8px 0 16px; color: #fff; }
  .row { display: grid; grid-template-columns: 1fr; gap: 12px; }
  @media (min-width: 1100px) {
    .row { grid-template-columns: 1.2fr 1fr; }
  }
  .card { background: var(--panel); border: 1px solid var(--border); border-radius: 12px; padding: 12px; }
  .kpis { display: grid; grid-template-columns: repeat(4,1fr); gap: 12px; }
  .kpi { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 12px; }
  .kpi label { display:block; color: var(--muted); font-size: 12px; }
  .kpi div { font-size: 20px; font-weight: 600; margin-top: 4px;}
  .filters { display: grid; grid-template-columns: repeat(4,1fr); gap: 8px; }
  .filters .filter { display:flex; flex-direction:column; gap:6px; }
  select, input, button { background: #0b1020; color: var(--text); border: 1px solid var(--border); border-radius: 8px; padding: 6px 8px; }
  select[multiple] { min-height: 120px; }
  .toolbar { display:flex; gap:8px; flex-wrap: wrap; align-items:center; }
  .btn { cursor:pointer; border:1px solid var(--border); padding:8px 10px; border-radius:10px; background:#0b1020; }
  .btn:hover { background:#0f152a; }
  .tabbar { display:flex; gap:8px; margin-top: 8px; flex-wrap: wrap; }
  .chip { padding:6px 10px; border-radius:999px; background: var(--chip); color:#e5e7eb; cursor:pointer; user-select:none; border:1px solid var(--border); }
  .chip.active { outline: 2px solid var(--accent); }
  .muted { color: var(--muted); }
  .danger { color: var(--danger); }
  .ok { color: var(--ok); }
  canvas, svg { background: #0b1020; border-radius: 10px; border: 1px solid var(--border); width: 100%; height: 420px; }
  table { width:100%; border-collapse: collapse; background:#0b1020; border-radius: 10px; overflow:hidden; }
  th, td { border-bottom:1px solid var(--border); padding:8px; text-align:left; font-size: 12px; }
  th { position: sticky; top: 0; background: #101426; z-index: 1; }
  .pagination { display:flex; gap:8px; align-items:center; justify-content:flex-end; margin-top:8px; }
  .legend { display:flex; gap:8px; flex-wrap: wrap; margin-top:6px; }
  details { border:1px solid var(--border); border-radius:8px; padding:8px; background:#0b1020; }
</style>
</head>
<body>
<div class="wrap">
  <h1>Dashboard de Costos (offline) — <span class="muted">Filtros reactivos, KPIs y exportación</span></h1>
  <div class="card">
    <div class="filters">
      <div class="filter">
        <label>CODTAREAPADRE</label>
        <select id="f_cod" multiple></select>
      </div>
      <div class="filter">
        <label>PROVEEDOR</label>
        <select id="f_prov" multiple></select>
      </div>
      <div class="filter">
        <label>TIPO_TAREA</label>
        <select id="f_tipo" multiple></select>
      </div>
      <div class="filter">
        <label>Rango FECHA_MES</label>
        <div style="display:flex; gap:6px;">
          <input type="date" id="f_ini"/>
          <input type="date" id="f_fin"/>
        </div>
      </div>
    </div>
    <div class="toolbar" style="margin-top:10px">
      <button class="btn" id="btn_apply">Aplicar filtros</button>
      <button class="btn" id="btn_reset">Reset</button>
      <span class="muted" id="rows_info"></span>
    </div>
  </div>

  <div class="row" style="margin-top:12px;">
    <div class="card">
      <div class="kpis">
        <div class="kpi"><label>Costo total filtrado</label><div id="k_total">$0</div></div>
        <div class="kpi"><label># Proveedores</label><div id="k_prov">0</div></div>
        <div class="kpi"><label># Combinaciones (CODTAREAPADRE–PROVEEDOR–MES)</label><div id="k_comb">0</div></div>
        <div class="kpi"><label>Variación % último mes</label><div id="k_mom">0%</div></div>
      </div>
      <div class="tabbar">
        <span class="chip active" data-mode="line" id="mode_line">Línea</span>
        <span class="chip" data-mode="stack" id="mode_stack">Área apilada</span>
        <span class="chip" data-mode="stack_pct" id="mode_stack_pct">% apilado</span>
        <span class="chip active" data-seg="TIPO_TAREA" id="seg_tipo">Segm: TIPO_TAREA</span>
        <span class="chip" data-seg="PROVEEDOR" id="seg_prov">Segm: PROVEEDOR</span>
      </div>
      <div id="chart_ts_holder" style="margin-top:8px;">
        <svg id="chart_ts"></svg>
      </div>
      <div class="toolbar" style="margin-top:8px;">
        <button class="btn" id="btn_ts_png">Descargar PNG</button>
        <button class="btn" id="btn_print">Imprimir / PDF</button>
      </div>
      <div class="legend" id="legend_ts"></div>
      <small class="muted">Puntos en <span class="danger">rojo</span> indican MoM &gt; 50% por (CODTAREAPADRE, PROVEEDOR).</small>
    </div>
    <div class="card">
      <div style="display:flex; gap:8px; align-items:center; flex-wrap:wrap;">
        <label>Top N Proveedores:</label>
        <input type="number" id="topn" min="1" value="{{TOPN_DEFAULT}}" style="width:90px;"/>
        <button class="btn" id="btn_all">Ver todos</button>
        <div class="tabbar" style="margin-left:auto;">
          <span class="chip active" data-bar="value" id="bar_val">Valores</span>
          <span class="chip" data-bar="pct" id="bar_pct">% participación</span>
        </div>
      </div>
      <div id="chart_bar_holder" style="margin-top:8px;">
        <svg id="chart_bar"></svg>
      </div>
      <div class="legend" id="legend_bar"></div>
      <div class="toolbar" style="margin-top:8px;">
        <button class="btn" id="btn_bar_png">Descargar PNG</button>
      </div>
    </div>
  </div>

  <div class="card" style="margin-top:12px;">
    <details open>
      <summary><b>Pivot interactivo</b> — Filas: CODTAREAPADRE · Columnas: PROVEEDOR — Agregador: Suma(COSTO)</summary>
      <div style="display:flex; gap:8px; flex-wrap:wrap; margin:8px 0;">
        <button class="btn" id="btn_pivot_mes">Variación por MES</button>
        <button class="btn" id="btn_pivot_pct">Matrix %PART_TIPO</button>
        <button class="btn" id="btn_pivot_csv">Exportar Pivot (CSV)</button>
      </div>
      <div style="overflow:auto; max-height:420px; border:1px solid var(--border); border-radius:10px;">
        <table id="pivot_tbl"><thead></thead><tbody></tbody></table>
      </div>
    </details>
  </div>

  <div class="card" style="margin-top:12px;">
    <details open>
      <summary><b>Detalle filtrado</b></summary>
      <div class="toolbar" style="margin:6px 0;">
        <button class="btn" id="btn_det_csv">Exportar Detalle (CSV)</button>
        <span class="muted" id="detail_count"></span>
      </div>
      <div style="overflow:auto; max-height:420px; border:1px solid var(--border); border-radius:10px;">
        <table id="detail_tbl"><thead></thead><tbody></tbody></table>
      </div>
      <div class="pagination">
        <button class="btn" id="prev_pg">« Prev</button>
        <span class="muted" id="pg_info">1/1</span>
        <button class="btn" id="next_pg">Next »</button>
      </div>
    </details>
  </div>
</div>

<script>
// ======================
// Datos embebidos
// ======================
const DATA_DETAIL = {{DATA_DETAIL_JSON}}; // arreglo de registros crudos
const AGG_TIPO = {{AGG_TIPO_JSON}};      // agregado por tipo (para series apiladas)
const AGG_TOTAL = {{AGG_TOTAL_JSON}};    // total por (COD,PROV,AÑO,MES) con MoM
const META = {{META_JSON}};              // { months: ["YYYY-MM-01",...], cods:[], provs:[], tipos:[] }

// Formateo es-CO (sin decimales)
const fmt = new Intl.NumberFormat('es-CO', { maximumFractionDigits: 0 });

// Estado de filtros
let sel = {
  cods: new Set(META.cods),
  provs: new Set(META.provs),
  tipos: new Set(META.tipos),
  ini: META.months.length ? META.months[0] : null,
  fin: META.months.length ? META.months[META.months.length - 1] : null
};

// UI helpers
function byId(id){ return document.getElementById(id); }
function setMultiSelect(elem, values){
  elem.innerHTML = "";
  values.forEach(v => {
    const opt = document.createElement('option');
    opt.value = v;
    opt.textContent = v;
    opt.selected = true;
    elem.appendChild(opt);
  });
}
function getSelected(elem){
  return Array.from(elem.selectedOptions).map(o => o.value);
}
function setChipsActive(group, idActive){
  document.querySelectorAll(group).forEach(el => el.classList.toggle('active', el.id === idActive));
}

// Inicializar selects y fechas
setMultiSelect(byId('f_cod'), META.cods);
setMultiSelect(byId('f_prov'), META.provs);
setMultiSelect(byId('f_tipo'), META.tipos);
if (sel.ini) byId('f_ini').value = sel.ini;
if (sel.fin) byId('f_fin').value = sel.fin;
byId('rows_info').textContent = `${DATA_DETAIL.length} filas totales`;

// Interacciones filtros
byId('btn_apply').onclick = () => {
  sel.cods = new Set(getSelected(byId('f_cod')));
  sel.provs = new Set(getSelected(byId('f_prov')));
  sel.tipos = new Set(getSelected(byId('f_tipo')));
  sel.ini = byId('f_ini').value || sel.ini;
  sel.fin = byId('f_fin').value || sel.fin;
  refreshAll();
};
byId('btn_reset').onclick = () => {
  setMultiSelect(byId('f_cod'), META.cods);
  setMultiSelect(byId('f_prov'), META.provs);
  setMultiSelect(byId('f_tipo'), META.tipos);
  sel = { cods: new Set(META.cods), provs: new Set(META.provs), tipos: new Set(META.tipos), ini: META.months[0], fin: META.months[META.months.length-1]};
  byId('f_ini').value = sel.ini; byId('f_fin').value = sel.fin;
  refreshAll();
};

// ======================
// Filtrado y utilidades
// ======================
function inRange(d, ini, fin){ return (!ini || d >= ini) && (!fin || d <= fin); }

function filteredDetail(){
  return DATA_DETAIL.filter(r =>
    sel.cods.has(r.CODTAREAPADRE) &&
    sel.provs.has(r.PROVEEDOR) &&
    sel.tipos.has(r.TIPO_TAREA) &&
    inRange(r.FECHA_MES, sel.ini, sel.fin)
  );
}

function filteredAggTipo(){
  return AGG_TIPO.filter(r =>
    sel.cods.has(r.CODTAREAPADRE) &&
    sel.provs.has(r.PROVEEDOR) &&
    sel.tipos.has(r.TIPO_TAREA) &&
    inRange(r.FECHA_MES, sel.ini, sel.fin)
  );
}

function filteredAggTotal(){
  return AGG_TOTAL.filter(r =>
    sel.cods.has(r.CODTAREAPADRE) &&
    sel.provs.has(r.PROVEEDOR) &&
    inRange(r.FECHA_MES, sel.ini, sel.fin)
  );
}

function uniq(arr){ return Array.from(new Set(arr)); }

// ======================
// KPIs
// ======================
function computeKPIs(){
  const det = filteredDetail();
  const total = det.reduce((s,r)=>s+r.COSTO, 0);
  const nProv = uniq(det.map(r=>r.PROVEEDOR)).length;
  const comb = uniq(filteredAggTotal().map(r=>[r.CODTAREAPADRE,r.PROVEEDOR,r.FECHA_MES].join("|"))).length;
  // variación último mes (sobre total de todos los grupos)
  const months = uniq(det.map(r=>r.FECHA_MES)).sort();
  let mom = 0;
  if (months.length >= 2){
    const last = months[months.length-1], prev = months[months.length-2];
    const tLast = det.filter(r=>r.FECHA_MES===last).reduce((s,r)=>s+r.COSTO,0);
    const tPrev = det.filter(r=>r.FECHA_MES===prev).reduce((s,r)=>s+r.COSTO,0);
    mom = tPrev>0? (tLast-tPrev)/tPrev*100 : 0;
  }
  byId('k_total').textContent = `$${fmt.format(Math.round(total))}`;
  byId('k_prov').textContent = `${nProv}`;
  byId('k_comb').textContent = `${comb}`;
  const momEl = byId('k_mom');
  momEl.textContent = `${(mom).toFixed(0)}%`;
  momEl.className = mom>50? 'danger' : (mom<0? 'ok' : '');
  byId('rows_info').textContent = `${det.length} filas filtradas`;
}

// ======================
// Gráfico temporal (SVG)
// ======================
let tsMode = "line"; // "line", "stack", "stack_pct"
let tsSeg = "TIPO_TAREA"; // "TIPO_TAREA" | "PROVEEDOR"

function setMode(m){ tsMode = m; setChipsActive('.chip[data-mode]', m==='line'?'mode_line':(m==='stack'?'mode_stack':'mode_stack_pct')); refreshTimeSeries(); }
function setSeg(s){ tsSeg = s; setChipsActive('.chip[data-seg]', s==='TIPO_TAREA'?'seg_tipo':'seg_prov'); refreshTimeSeries(); }

byId('mode_line').onclick = ()=> setMode('line');
byId('mode_stack').onclick = ()=> setMode('stack');
byId('mode_stack_pct').onclick = ()=> setMode('stack_pct');
byId('seg_tipo').onclick = ()=> setSeg('TIPO_TAREA');
byId('seg_prov').onclick = ()=> setSeg('PROVEEDOR');

function groupBy(arr, keyFn){
  const m = new Map();
  for(const r of arr){
    const k = keyFn(r);
    if(!m.has(k)) m.set(k, []);
    m.get(k).push(r);
  }
  return m;
}

function sumBy(arr, key){ return arr.reduce((s,r)=>s+r[key],0); }

function buildTimeSeries(){
  const a = filteredAggTipo(); // tiene COSTO_POR_TIPO y %PART_TIPO; cada registro es (AÑO,MES,COD,PROV,TIPO,FECHA_MES)
  const segKey = tsSeg;
  const months = uniq(a.map(r=>r.FECHA_MES)).sort();
  const segs = uniq(a.map(r=>r[segKey])).sort();
  // Mapa seg -> series por mes (suma)
  const bySeg = new Map();
  for(const s of segs){
    bySeg.set(s, months.map(m => sumBy(a.filter(r=>r[segKey]===s && r.FECHA_MES===m), "COSTO_POR_TIPO")));
  }
  // Totales por mes para %
  const totals = months.map(m => sumBy(a.filter(r=>r.FECHA_MES===m), "COSTO_POR_TIPO"));
  return { months, segs, bySeg, totals };
}

function drawSVGLine(svg, xvals, seriesMap, colors, highlightPts){
  // Limpia
  svg.innerHTML = "";
  const W = svg.clientWidth || svg.parentElement.clientWidth, H = svg.clientHeight || 420;
  const pad = {l:50, r:16, t:10, b:28};
  const xmin = 0, xmax = xvals.length-1;
  const allY = [];
  for(const yarr of seriesMap.values()) allY.push(...yarr);
  const ymin = 0, ymax = Math.max(1, ...allY);
  const xScale = i => pad.l + (W - pad.l - pad.r) * (i - xmin) / (xmax - xmin || 1);
  const yScale = v => H - pad.b - (H - pad.t - pad.b) * (v - ymin) / (ymax - ymin || 1);

  // Ejes
  const axes = document.createElementNS("http://www.w3.org/2000/svg", "g");
  axes.setAttribute("stroke", "#334155");
  axes.setAttribute("stroke-width", "1");
  // Y axis
  const yAxis = document.createElementNS("http://www.w3.org/2000/svg", "line");
  yAxis.setAttribute("x1", str(pad.l)); yAxis.setAttribute("x2", str(pad.l));
  yAxis.setAttribute("y1", str(pad.t)); yAxis.setAttribute("y2", str(H-pad.b));
  axes.appendChild(yAxis);
  // X axis
  const xAxis = document.createElementNS("http://www.w3.org/2000/svg", "line");
  xAxis.setAttribute("x1", str(pad.l)); xAxis.setAttribute("x2", str(W-pad.r));
  xAxis.setAttribute("y1", str(H-pad.b)); xAxis.setAttribute("y2", str(H-pad.b));
  axes.appendChild(xAxis);
  svg.appendChild(axes);

  // Grid + ticks
  const months = xvals;
  for(let i=0; i<months.length; i++){
    const x = xScale(i);
    const tick = document.createElementNS("http://www.w3.org/2000/svg", "line");
    tick.setAttribute("x1", str(x)); tick.setAttribute("x2", str(x));
    tick.setAttribute("y1", str(H-pad.b)); tick.setAttribute("y2", str(H-pad.b+4));
    tick.setAttribute("stroke", "#334155");
    svg.appendChild(tick);

    const lbl = document.createElementNS("http://www.w3.org/2000/svg", "text");
    lbl.setAttribute("x", str(x)); lbl.setAttribute("y", str(H-pad.b+18));
    lbl.setAttribute("text-anchor", "middle");
    lbl.setAttribute("fill", "#94a3b8");
    lbl.setAttribute("font-size", "11");
    lbl.textContent = months[i].slice(0,7);
    svg.appendChild(lbl);
  }
  // y labels
  const yTicks = 5;
  for(let j=0; j<=yTicks; j++){
    const v = ymin + (ymax-ymin)*j/yTicks;
    const y = yScale(v);
    const gl = document.createElementNS("http://www.w3.org/2000/svg", "line");
    gl.setAttribute("x1", str(pad.l)); gl.setAttribute("x2", str(W-pad.r));
    gl.setAttribute("y1", str(y)); gl.setAttribute("y2", str(y));
    gl.setAttribute("stroke", "#1f2937");
    svg.appendChild(gl);
    const tl = document.createElementNS("http://www.w3.org/2000/svg", "text");
    tl.setAttribute("x", str(pad.l-6)); tl.setAttribute("y", str(y+4));
    tl.setAttribute("text-anchor", "end"); tl.setAttribute("fill", "#94a3b8"); tl.setAttribute("font-size","11");
    tl.textContent = "$"+fmt.format(Math.round(v));
    svg.appendChild(tl);
  }

  // Series
  let idx=0;
  for(const [name, yarr] of seriesMap.entries()){
    const col = colors[idx++ % colors.length];
    let d = "";
    for(let i=0; i<yarr.length; i++){
      const x = xScale(i), y = yScale(yarr[i]);
      d += (i===0? `M ${x} ${y}` : ` L ${x} ${y}`);
    }
    const path = document.createElementNS("http://www.w3.org/2000/svg", "path");
    path.setAttribute("d", d);
    path.setAttribute("fill", "none");
    path.setAttribute("stroke", col);
    path.setAttribute("stroke-width", "2");
    svg.appendChild(path);

    // puntos y highlight
    for(let i=0;i<yarr.length;i++){
      const x = xScale(i), y = yScale(yarr[i]);
      const c = document.createElementNS("http://www.w3.org/2000/svg", "circle");
      c.setAttribute("cx", str(x)); c.setAttribute("cy", str(y)); c.setAttribute("r","3");
      const key = months[i];
      const hit = !!(highlightPts && highlightPts.has(key));
      c.setAttribute("fill", hit? "#ef4444" : col);
      c.setAttribute("opacity", hit? "0.9" : "0.7");
      c.appendChild(makeTitle(`${name}\n${key}\n$${fmt.format(Math.round(yarr[i]))}${hit? "\nMoM>50%" : ""}`));
      svg.appendChild(c);
    }
  }
}

function drawSVGStack(svg, xvals, seriesMap, colors, pct=false){
  svg.innerHTML = "";
  const W = svg.clientWidth || svg.parentElement.clientWidth, H = svg.clientHeight || 420;
  const pad = {l:50, r:16, t:10, b:28};
  const months = xvals;
  const segs = Array.from(seriesMap.keys());
  const stacks = []; // por mes: [y1,y2,...]
  const totals = [];
  for(let i=0;i<months.length;i++){
    let col = [];
    let tot=0;
    for(const s of segs){
      const v = seriesMap.get(s)[i] || 0; col.push(v); tot += v;
    }
    stacks.push(col); totals.push(tot || 1);
  }
  const ymax = Math.max(1, ...totals);
  const xScale = i => pad.l + (W - pad.l - pad.r) * (i) / (months.length-1 || 1);
  const yScale = v => H - pad.b - (H - pad.t - pad.b) * (v) / (ymax);

  // ejes
  const axes = document.createElementNS("http://www.w3.org/2000/svg", "g");
  axes.setAttribute("stroke", "#334155");
  const yAxis = document.createElementNS("http://www.w3.org/2000/svg", "line");
  yAxis.setAttribute("x1", str(pad.l)); yAxis.setAttribute("x2", str(pad.l));
  yAxis.setAttribute("y1", str(pad.t)); yAxis.setAttribute("y2", str(H-pad.b)); axes.appendChild(yAxis);
  const xAxis = document.createElementNS("http://www.w3.org/2000/svg", "line");
  xAxis.setAttribute("x1", str(pad.l)); xAxis.setAttribute("x2", str(W-pad.r));
  xAxis.setAttribute("y1", str(H-pad.b)); xAxis.setAttribute("y2", str(H-pad.b)); axes.appendChild(xAxis);
  svg.appendChild(axes);
  for(let i=0;i<months.length;i++){
    const x = xScale(i);
    const tick = document.createElementNS("http://www.w3.org/2000/svg", "line");
    tick.setAttribute("x1", str(x)); tick.setAttribute("x2", str(x));
    tick.setAttribute("y1", str(H-pad.b)); tick.setAttribute("y2", str(H-pad.b+4));
    tick.setAttribute("stroke", "#334155"); svg.appendChild(tick);
    const lbl = document.createElementNS("http://www.w3.org/2000/svg", "text");
    lbl.setAttribute("x", str(x)); lbl.setAttribute("y", str(H-pad.b+18));
    lbl.setAttribute("text-anchor", "middle"); lbl.setAttribute("fill", "#94a3b8"); lbl.setAttribute("font-size","11");
    lbl.textContent = months[i].slice(0,7); svg.appendChild(lbl);
  }
  const yTicks = 5;
  for(let j=0;j<=yTicks;j++){
    const v = ymax*j/yTicks;
    const y = yScale(v);
    const gl = document.createElementNS("http://www.w3.org/2000/svg", "line");
    gl.setAttribute("x1", str(pad.l)); gl.setAttribute("x2", str(W-pad.r));
    gl.setAttribute("y1", str(y)); gl.setAttribute("y2", str(y));
    gl.setAttribute("stroke", "#1f2937"); svg.appendChild(gl);
    const tl = document.createElementNS("http://www.w3.org/2000/svg", "text");
    tl.setAttribute("x", str(pad.l-6)); tl.setAttribute("y", str(y+4)); tl.setAttribute("text-anchor","end"); tl.setAttribute("fill","#94a3b8"); tl.setAttribute("font-size","11");
    tl.textContent = pct? `${Math.round(v*100)}%` : "$"+fmt.format(Math.round(v));
    svg.appendChild(tl);
  }

  // Apilado por polígonos
  const segsArr = Array.from(seriesMap.keys());
  for(let sidx=0; sidx<segsArr.length; sidx++){
    const name = segsArr[sidx];
    const col = colors[sidx % colors.length];
    let d = "";
    let accPrev = Array(months.length).fill(0);
    let accNext = Array(months.length).fill(0);
    // construir acumulado hasta sidx
    for(let k=0;k<=sidx;k++){
      const yarr = seriesMap.get(segsArr[k]);
      for(let i=0;i<months.length;i++){
        accPrev[i] += yarr[i] || 0;
      }
    }
    // acumulado hasta sidx-1
    for(let k=0;k<sidx;k++){
      const yarr = seriesMap.get(segsArr[k]);
      for(let i=0;i<months.length;i++){
        accNext[i] += yarr[i] || 0;
      }
    }
    // path superior
    for(let i=0;i<months.length;i++){
      const top = pct? (accPrev[i]/(totals[i]||1))*ymax : accPrev[i];
      const x = pad.l + (W - pad.l - pad.r) * (i) / (months.length-1 || 1);
      const y = yScale(top);
      d += (i===0? `M ${x} ${y}` : ` L ${x} ${y}`);
    }
    // path inferior (vuelta)
    for(let i=months.length-1; i>=0; i--){
      const bot = pct? (accNext[i]/(totals[i]||1))*ymax : accNext[i];
      const x = pad.l + (W - pad.l - pad.r) * (i) / (months.length-1 || 1);
      const y = yScale(bot);
      d += ` L ${x} ${y}`;
    }
    d += " Z";
    const path = document.createElementNS("http://www.w3.org/2000/svg","path");
    path.setAttribute("d", d); path.setAttribute("fill", col); path.setAttribute("opacity","0.7");
    path.appendChild(makeTitle(`${name}`));
    svg.appendChild(path);
  }
}

function makeTitle(text){
  const t = document.createElementNS("http://www.w3.org/2000/svg", "title");
  t.textContent = text; return t;
}
function str(x){ return String(x); }

const PALETTE = ["#60a5fa","#34d399","#f472b6","#fbbf24","#a78bfa","#f87171","#22d3ee","#fb7185","#4ade80","#93c5fd","#fde047"];

function refreshTimeSeries(){
  const { months, segs, bySeg, totals } = buildTimeSeries();
  const svg = byId('chart_ts');
  const legend = byId('legend_ts');
  legend.innerHTML = "";
  const seriesMap = new Map();
  segs.forEach(s => seriesMap.set(s, bySeg.get(s)));

  // puntos con MoM>50%
  const hi = new Set(filteredAggTotal().filter(r => r.MOM_GT_50).map(r => r.FECHA_MES));
  if (tsMode === "line"){
    drawSVGLine(svg, months, seriesMap, PALETTE, hi);
  } else {
    drawSVGStack(svg, months, seriesMap, PALETTE, tsMode==="stack_pct");
  }

  // leyenda
  let idx=0;
  for(const s of segs){
    const chip = document.createElement('span');
    chip.className = "chip"; chip.style.background = "#0b1020"; chip.style.borderColor="#1f2937";
    const bullet = document.createElement('span');
    bullet.style.display="inline-block"; bullet.style.width="10px"; bullet.style.height="10px";
    bullet.style.marginRight="6px"; bullet.style.borderRadius="999px";
    bullet.style.background = PALETTE[idx++ % PALETTE.length];
    chip.appendChild(bullet);
    chip.appendChild(document.createTextNode(s));
    legend.appendChild(chip);
  }
}

// Descargar PNG desde SVG
function svgToPng(svgElem, filename){
  const svgData = new XMLSerializer().serializeToString(svgElem);
  const img = new Image();
  const svgBlob = new Blob([svgData], {type: "image/svg+xml;charset=utf-8"});
  const url = URL.createObjectURL(svgBlob);
  img.onload = function(){
    const canvas = document.createElement("canvas");
    canvas.width = svgElem.clientWidth || 1000;
    canvas.height = svgElem.clientHeight || 420;
    const ctx = canvas.getContext("2d");
    ctx.fillStyle = "#0b1020";
    ctx.fillRect(0,0,canvas.width, canvas.height);
    ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
    URL.revokeObjectURL(url);
    const a = document.createElement("a");
    a.download = filename;
    a.href = canvas.toDataURL("image/png");
    a.click();
  };
  img.src = url;
}

byId('btn_ts_png').onclick = ()=> svgToPng(byId('chart_ts'), "timeseries.png");
byId('btn_bar_png').onclick = ()=> svgToPng(byId('chart_bar'), "barras.png");
byId('btn_print').onclick = ()=> window.print();

// ======================
// Barras apiladas por PROVEEDOR
// ======================
let barMode = "value"; // "value" | "pct"
byId('bar_val').onclick = () => { barMode="value"; setChipsActive('.chip[data-bar]', 'bar_val'); refreshBars(); }
byId('bar_pct').onclick = () => { barMode="pct"; setChipsActive('.chip[data-bar]', 'bar_pct'); refreshBars(); }
byId('btn_all').onclick = () => { byId('topn').value = 9999; refreshBars(); };

function buildBars(){
  // usamos AGG_TIPO para sumar por proveedor (todas las categorías)
  const a = filteredAggTipo();
  const provs = uniq(a.map(r=>r.PROVEEDOR)).sort();
  const tipos = uniq(a.map(r=>r.TIPO_TAREA)).sort();
  const byProvTipo = new Map();
  for(const p of provs){
    const row = new Map();
    for(const t of tipos){
      const s = sumBy(a.filter(r=>r.PROVEEDOR===p && r.TIPO_TAREA===t), "COSTO_POR_TIPO");
      row.set(t, s);
    }
    byProvTipo.set(p, row);
  }
  // ordenar por total
  const totals = provs.map(p => [p, Array.from(byProvTipo.get(p).values()).reduce((s,v)=>s+v,0)]);
  totals.sort((a,b)=> b[1]-a[1]);
  return { provs: totals.map(x=>x[0]), tipos, byProvTipo, totals };
}

function drawBars(){
  const svg = byId('chart_bar');
  svg.innerHTML = "";
  const W = svg.clientWidth || svg.parentElement.clientWidth, H = svg.clientHeight || 420;
  const pad = {l:50, r:16, t:10, b:120};
  const { provs, tipos, byProvTipo, totals } = buildBars();
  const topn = Math.max(1, parseInt(byId('topn').value || '10'));
  const P = provs.slice(0, topn);
  const xBand = (i)=> pad.l + (W - pad.l - pad.r) * (i+0.5) / (P.length);
  const barW = (W - pad.l - pad.r) / (P.length || 1) * 0.7;
  const palette = PALETTE;
  // valores
  const vals = P.map(p => {
    const row = byProvTipo.get(p);
    const arr = tipos.map(t => row.get(t) || 0);
    const total = arr.reduce((s,v)=>s+v,0) || 1;
    return {p, arr, total};
  });
  // para modo %
  const ymax = barMode==='pct' ? 1 : Math.max(1, ...vals.map(v => v.total));
  const yScale = v => H - pad.b - (H - pad.t - pad.b) * (v) / ymax;

  // ejes
  const axes = document.createElementNS("http://www.w3.org/2000/svg", "g");
  axes.setAttribute("stroke", "#334155");
  const yAxis = document.createElementNS("http://www.w3.org/2000/svg", "line");
  yAxis.setAttribute("x1", str(pad.l)); yAxis.setAttribute("x2", str(pad.l));
  yAxis.setAttribute("y1", str(pad.t)); yAxis.setAttribute("y2", str(H-pad.b)); axes.appendChild(yAxis);
  const xAxis = document.createElementNS("http://www.w3.org/2000/svg", "line");
  xAxis.setAttribute("x1", str(pad.l)); xAxis.setAttribute("x2", str(W-pad.r));
  xAxis.setAttribute("y1", str(H-pad.b)); xAxis.setAttribute("y2", str(H-pad.b)); axes.appendChild(xAxis);
  svg.appendChild(axes);

  // y ticks
  const yTicks=5;
  for(let j=0;j<=yTicks;j++){
    const v = j/yTicks * ymax;
    const y = yScale(v);
    const gl = document.createElementNS("http://www.w3.org/2000/svg", "line");
    gl.setAttribute("x1", str(pad.l)); gl.setAttribute("x2", str(W-pad.r));
    gl.setAttribute("y1", str(y)); gl.setAttribute("y2", str(y)); gl.setAttribute("stroke","#1f2937"); svg.appendChild(gl);
    const tl = document.createElementNS("http://www.w3.org/2000/svg", "text");
    tl.setAttribute("x", str(pad.l-6)); tl.setAttribute("y", str(y+4)); tl.setAttribute("text-anchor","end"); tl.setAttribute("fill","#94a3b8"); tl.setAttribute("font-size","11");
    tl.textContent = barMode==='pct'? `${Math.round(v*100)}%` : "$"+fmt.format(Math.round(v));
    svg.appendChild(tl);
  }

  // barras apiladas
  for(let i=0;i<P.length;i++){
    const {p, arr, total} = vals[i];
    let acc=0;
    for(let tIdx=0;tIdx<tipos.length;tIdx++){
      let v = arr[tIdx];
      let bot = acc;
      acc += v;
      let top = acc;
      if (barMode==='pct'){
        bot = bot/(total||1);
        top = top/(total||1);
      }
      const x = xBand(i) - barW/2;
      const y1 = yScale(top);
      const y2 = yScale(bot);
      const rect = document.createElementNS("http://www.w3.org/2000/svg", "rect");
      rect.setAttribute("x", str(x)); rect.setAttribute("width", str(barW));
      rect.setAttribute("y", str(y1)); rect.setAttribute("height", str(Math.max(0,y2-y1)));
      rect.setAttribute("fill", palette[tIdx % palette.length]); rect.setAttribute("opacity","0.8");
      rect.appendChild(makeTitle(`${p}\n${tipos[tIdx]}\n${barMode==='pct'? Math.round((v/(total||1))*100)+'%': '$'+fmt.format(Math.round(v))}`));
      svg.appendChild(rect);
    }
    // etiqueta X rotada
    const tx = document.createElementNS("http://www.w3.org/2000/svg", "text");
    tx.setAttribute("x", str(xBand(i))); tx.setAttribute("y", str(H - pad.b + 12));
    tx.setAttribute("fill", "#94a3b8"); tx.setAttribute("font-size","11"); tx.setAttribute("text-anchor","end");
    tx.setAttribute("transform", `rotate(-35 ${xBand(i)} ${H - pad.b + 12})`);
    tx.textContent = p;
    svg.appendChild(tx);
  }

  // leyenda
  const legend = byId('legend_bar');
  legend.innerHTML = "";
  for(let tIdx=0;tIdx<tipos.length;tIdx++){
    const chip = document.createElement('span');
    chip.className = 'chip'; chip.style.background="#0b1020"; chip.style.borderColor="#1f2937";
    const dot = document.createElement('span');
    dot.style.display="inline-block"; dot.style.width="10px"; dot.style.height="10px";
    dot.style.borderRadius="999px"; dot.style.marginRight="6px"; dot.style.background=PALETTE[tIdx%PALETTE.length];
    chip.appendChild(dot); chip.appendChild(document.createTextNode(tipos[tIdx]));
    legend.appendChild(chip);
  }
}

function refreshBars(){ drawBars(); }

// ======================
// Pivot (matrix simple)
// ======================
let pivotMode = "sum"; // "sum" | "mes" | "pct_tipo"

function computePivot(){
  const det = filteredDetail();
  const cods = uniq(det.map(r=>r.CODTAREAPADRE)).sort();
  const provs = uniq(det.map(r=>r.PROVEEDOR)).sort();
  const head = ["CODTAREAPADRE", ...provs, "TOTAL"];
  const rows = [];
  for(const c of cods){
    const row = new Array(head.length).fill(0);
    row[0] = c;
    const sub = det.filter(r=>r.CODTAREAPADRE===c);
    let totRow = 0;
    for(let j=0;j<provs.length;j++){
      const p = provs[j];
      const val = sub.filter(r=>r.PROVEEDOR===p).reduce((s,r)=>s+r.COSTO, 0);
      row[j+1] = val; totRow += val;
    }
    row[head.length-1] = totRow;
    rows.push(row);
  }
  rows.sort((a,b)=> (b[b.length-1]-a[b.length-1]));
  return { head, rows };
}

function computePivotMes(){
  const a = filteredAggTotal();
  const cods = uniq(a.map(r=>r.CODTAREAPADRE)).sort();
  const months = uniq(a.map(r=>r.FECHA_MES)).sort();
  const head = ["CODTAREAPADRE", ...months];
  const rows = [];
  for(const c of cods){
    const row = new Array(head.length).fill(0); row[0]=c;
    for(let j=0;j<months.length;j++){
      const m = months[j];
      const v = a.filter(r=>r.CODTAREAPADRE===c && r.FECHA_MES===m).reduce((s,r)=>s+r.COSTO_TOTAL_MES,0);
      row[j+1] = v;
    }
    rows.push(row);
  }
  return { head, rows };
}

function computePivotPctTipo(){
  // Matriz promedio %PART_TIPO por COD vs PROVEEDOR
  const a = filteredAggTipo();
  const cods = uniq(a.map(r=>r.CODTAREAPADRE)).sort();
  const provs = uniq(a.map(r=>r.PROVEEDOR)).sort();
  const head = ["CODTAREAPADRE", ...provs];
  const rows = [];
  for(const c of cods){
    const row = new Array(head.length).fill(0); row[0]=c;
    for(let j=0;j<provs.length;j++){
      const p = provs[j];
      const sub = a.filter(r=>r.CODTAREAPADRE===c && r.PROVEEDOR===p);
      const avg = sub.length? (sub.reduce((s,r)=>s+r.PART_TIPO,0)/sub.length) : 0;
      row[j+1] = avg;
    }
    rows.push(row);
  }
  return { head, rows, pct:true };
}

function renderPivot(tbl, data){
  const thead = tbl.querySelector("thead");
  const tbody = tbl.querySelector("tbody");
  thead.innerHTML = ""; tbody.innerHTML = "";
  const trh = document.createElement("tr");
  data.head.forEach(h => {
    const th = document.createElement("th"); th.textContent = h; trh.appendChild(th);
  });
  thead.appendChild(trh);
  data.rows.forEach(r => {
    const tr = document.createElement("tr");
    r.forEach((v,i)=>{
      const td = document.createElement("td");
      if (i===0){ td.textContent = v; }
      else {
        if (data.pct){ td.textContent = Math.round(v) + "%"; }
        else { td.textContent = "$"+fmt.format(Math.round(v)); }
      }
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
}

function refreshPivot(){
  let d;
  if (pivotMode==="mes"){ d = computePivotMes(); }
  else if (pivotMode==="pct"){ d = computePivotPctTipo(); }
  else { d = computePivot(); }
  renderPivot(byId('pivot_tbl'), d);
}

byId('btn_pivot_mes').onclick = ()=> { pivotMode="mes"; refreshPivot(); };
byId('btn_pivot_pct').onclick = ()=> { pivotMode="pct"; refreshPivot(); };
byId('btn_pivot_csv').onclick = ()=> exportTableCSV(byId('pivot_tbl'), "pivot.csv");

// ======================
// Tabla detalle paginada
// ======================
let page = 1;
const PAGE_SIZE = 25;

function renderDetail(){
  const det = filteredDetail();
  const thead = byId('detail_tbl').querySelector('thead');
  const tbody = byId('detail_tbl').querySelector('tbody');
  thead.innerHTML=""; tbody.innerHTML="";
  const head = ["AÑO","MES","FECHA_MES","CODTAREAPADRE","PROVEEDOR","TIPO_TAREA","COSTO"];
  const trh = document.createElement("tr");
  head.forEach(h=>{ const th=document.createElement("th"); th.textContent=h; trh.appendChild(th); });
  thead.appendChild(trh);
  const totalPages = Math.max(1, Math.ceil(det.length / PAGE_SIZE));
  if (page>totalPages) page=totalPages;
  const slice = det.slice((page-1)*PAGE_SIZE, page*PAGE_SIZE);
  slice.forEach(r => {
    const tr = document.createElement("tr");
    head.forEach(h => {
      const td = document.createElement("td");
      td.textContent = (h==="COSTO") ? "$"+fmt.format(Math.round(r[h])) : String(r[h]);
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  });
  byId('pg_info').textContent = `${page}/${totalPages}`;
  byId('detail_count').textContent = `${det.length} filas`;
}

byId('prev_pg').onclick = () => { page = Math.max(1, page-1); renderDetail(); };
byId('next_pg').onclick = () => { const det = filteredDetail(); const totalPages = Math.max(1, Math.ceil(det.length / PAGE_SIZE)); page = Math.min(totalPages, page+1); renderDetail(); };
byId('btn_det_csv').onclick = () => exportTableCSV(byId('detail_tbl'), "detalle.csv");

// ======================
// CSV export genérico
// ======================
function exportTableCSV(tbl, filename){
  let csv = "";
  const rows = tbl.querySelectorAll("tr");
  rows.forEach((tr,i)=>{
    const cells = tr.querySelectorAll(i===0? "th" : "td");
    const line = Array.from(cells).map(td => `"${String(td.textContent).replace(/"/g,'""')}"`).join(",");
    csv += line + "\n";
  });
  const blob = new Blob([csv], {type:"text/csv;charset=utf-8;"});
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  a.click();
}

// ======================
// Ciclo de refresco
// ======================
function refreshAll(){
  computeKPIs();
  refreshTimeSeries();
  refreshBars();
  refreshPivot();
  renderDetail();
}

// Primer render
refreshAll();
</script>
</body>
</html>
"""

# ===========================
# Worker (procesa Excel y genera HTML)
// ===========================

class Cancelled(Exception):
    pass

@dataclass
class JobParams:
    input_path: Path
    output_dir: Path
    topn: int
    open_when_done: bool

class DashboardBuilder(threading.Thread):
    def __init__(self, params: JobParams, log: logging.Logger, q: queue.Queue, cancel_ev: threading.Event):
        super().__init__(daemon=True)
        self.params = params
        self.log = log
        self.q = q
        self.cancel_ev = cancel_ev
        self.result_path: Path | None = None
        self.log_path: Path | None = None

    def check_cancel(self):
        if self.cancel_ev.is_set():
            raise Cancelled("Proceso cancelado por el usuario.")

    def run(self):
        try:
            self.q_put(5, "Leyendo archivo Excel…")
            df = self.read_excel(self.params.input_path)
            self.check_cancel()

            self.q_put(20, "Normalizando y validando columnas…")
            df = normalize_cols(df)
            for c in REQUIRED_COLS:
                if c not in df.columns:
                    raise ValueError(f"Columna requerida faltante: {c}")
            df["TIPO_TAREA"] = df["TIPO_TAREA"].fillna("SIN_TIPO").astype(str).str.strip()
            # saneo AÑO y MES
            df["AÑO"] = df["AÑO"].apply(safe_int)
            df["MES"] = df["MES"].apply(safe_int)
            df = df[df["AÑO"].notna() & df["MES"].notna()]
            df["AÑO"] = df["AÑO"].astype(int)
            df["MES"] = df["MES"].astype(int)
            df = df[(df["MES"]>=1) & (df["MES"]<=12)]
            self.check_cancel()

            self.q_put(35, "Calculando FECHA_MES y ordenando…")
            df["FECHA_MES"] = [primeira_de_mes(y,m) for y,m in zip(df["AÑO"], df["MES"])]
            # Costo como numérico
            df["COSTO"] = pd.to_numeric(df["COSTO"], errors="coerce").fillna(0).astype(float)
            df = df.sort_values(by=["AÑO","MES","CODTAREAPADRE","PROVEEDOR","TIPO_TAREA"])
            self.check_cancel()

            self.q_put(50, "Agregando métricas por tipo y totales…")
            # AGG_TIPO
            agg_tipo = (df.groupby(["AÑO","MES","FECHA_MES","CODTAREAPADRE","PROVEEDOR","TIPO_TAREA"], as_index=False)
                          .agg(COSTO_POR_TIPO=("COSTO","sum")))
            tot_mes = (df.groupby(["AÑO","MES","FECHA_MES","CODTAREAPADRE","PROVEEDOR"], as_index=False)
                         .agg(COSTO_TOTAL_MES=("COSTO","sum")))
            agg_tipo = agg_tipo.merge(tot_mes, on=["AÑO","MES","FECHA_MES","CODTAREAPADRE","PROVEEDOR"], how="left")
            agg_tipo["PART_TIPO"] = (agg_tipo["COSTO_POR_TIPO"] / agg_tipo["COSTO_TOTAL_MES"].replace({0:pd.NA})) * 100
            agg_tipo["PART_TIPO"] = agg_tipo["PART_TIPO"].fillna(0)

            # AGG_TOTAL con MoM
            agg_total = tot_mes.copy().sort_values(["CODTAREAPADRE","PROVEEDOR","AÑO","MES"])
            agg_total["PREV"] = agg_total.groupby(["CODTAREAPADRE","PROVEEDOR"])["COSTO_TOTAL_MES"].shift(1)
            agg_total["MOM_PCT"] = ((agg_total["COSTO_TOTAL_MES"] - agg_total["PREV"]) / agg_total["PREV"]) * 100
            agg_total["MOM_PCT"] = agg_total["MOM_PCT"].fillna(0)
            agg_total["MOM_GT_50"] = agg_total["MOM_PCT"] > 50
            self.check_cancel()

            self.q_put(65, "Serializando datos a JSON…")
            # detalle mínimo
            detail_cols = ["AÑO","MES","FECHA_MES","CODTAREAPADRE","PROVEEDOR","TIPO_TAREA","COSTO"]
            data_detail = df[detail_cols].copy()
            data_detail["COSTO"] = data_detail["COSTO"].round(0).astype(float)

            data_detail_json = data_detail.to_dict(orient="records")
            agg_tipo_out = agg_tipo.copy()
            agg_tipo_out["COSTO_POR_TIPO"] = agg_tipo_out["COSTO_POR_TIPO"].round(0).astype(float)
            agg_tipo_json = agg_tipo_out.to_dict(orient="records")
            agg_total_out = agg_total.copy()
            agg_total_out["COSTO_TOTAL_MES"] = agg_total_out["COSTO_TOTAL_MES"].round(0).astype(float)
            agg_total_json = agg_total_out.to_dict(orient="records")

            months = sorted({*data_detail["FECHA_MES"].unique().tolist()})
            cods = sorted({*data_detail["CODTAREAPADRE"].unique().tolist()})
            provs = sorted({*data_detail["PROVEEDOR"].unique().tolist()})
            tipos = sorted({*data_detail["TIPO_TAREA"].unique().tolist()})
            meta = {"months": months, "cods": cods, "provs": provs, "tipos": tipos}
            self.check_cancel()

            self.q_put(80, "Renderizando HTML…")
            html_str = HTML_TEMPLATE.replace("{{DATA_DETAIL_JSON}}", json.dumps(data_detail_json, ensure_ascii=False))
            html_str = html_str.replace("{{AGG_TIPO_JSON}}", json.dumps(agg_tipo_json, ensure_ascii=False))
            html_str = html_str.replace("{{AGG_TOTAL_JSON}}", json.dumps(agg_total_json, ensure_ascii=False))
            html_str = html_str.replace("{{META_JSON}}", json.dumps(meta, ensure_ascii=False))
            html_str = html_str.replace("{{TOPN_DEFAULT}}", str(int(self.params.topn)))

            self.q_put(90, "Escribiendo archivo…")
            ts = bogota_now_str()
            final_name = f"dashboard_costos_{ts}.html"
            out_dir = Path(self.params.output_dir)
            out_dir.mkdir(parents=True, exist_ok=True)
            tmp_path = out_dir / (final_name + ".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(html_str)
            final_path = out_dir / final_name
            tmp_path.replace(final_path)
            self.result_path = final_path

            # archivo de log
            self.log_path = final_path.with_suffix(".log")
            with open(self.log_path, "w", encoding="utf-8") as lf:
                for rec in LOG_BUFFER:
                    lf.write(rec + "\n")

            self.q_put(100, f"Listo: {final_path}")
        except Cancelled as c:
            self.q_put(0, str(c), is_error=True)
        except Exception as e:
            self.q_put(0, f"Error: {e}", is_error=True)

    def read_excel(self, path: Path) -> pd.DataFrame:
        # Lee primera hoja por defecto
        try:
            df = pd.read_excel(path, engine="openpyxl")
        except Exception:
            # Intenta hoja "Registros"
            df = pd.read_excel(path, sheet_name="Registros", engine="openpyxl")
        return df

    def q_put(self, progress: int, msg: str, is_error: bool=False):
        self.log.info(msg) if not is_error else self.log.error(msg)
        self.q.put(("progress", progress))
        self.q.put(("log", msg))
        if is_error:
            self.q.put(("done", False, msg))
        elif progress>=100:
            self.q.put(("done", True, msg))


# ===========================
# GUI
# ===========================

LOG_BUFFER: list[str] = []

class TkLogHandler(logging.Handler):
    def __init__(self, text_widget: tk.Text | None = None):
        super().__init__()
        self.text_widget = text_widget

    def emit(self, record: logging.LogRecord):
        msg = self.format(record)
        LOG_BUFFER.append(msg)
        if self.text_widget:
            self.text_widget.configure(state="normal")
            self.text_widget.insert("end", msg + "\n")
            self.text_widget.see("end")
            self.text_widget.configure(state="disabled")

class App(tk.Tk):
    def __init__(self, args_prefill: dict[str, str | int | None] | None = None):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry("880x580")
        self.minsize(820, 560)

        # Estado
        self.worker: DashboardBuilder | None = None
        self.cancel_ev = threading.Event()
        self.q = queue.Queue()

        # Config
        self.cfg_path = Path(__file__).with_name(CONFIG_FILE)
        self.config_data = self.load_config()

        # Logger
        self.logger = logging.getLogger("dashboard")
        self.logger.setLevel(logging.INFO)
        fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")
        self.tk_handler = TkLogHandler()
        self.tk_handler.setFormatter(fmt)
        self.logger.addHandler(self.tk_handler)

        # UI
        self.build_ui()

        # Prefill de CLI/Config
        self.prefill(args_prefill or {})

        # Loop de mensajes
        self.after(120, self.poll_queue)

    def build_ui(self):
        pad = {"padx": 8, "pady": 6}

        frm_io = ttk.LabelFrame(self, text="Entrada y salida")
        frm_io.pack(fill="x", **pad)

        self.var_in = tk.StringVar()
        self.var_out = tk.StringVar()
        self.var_topn = tk.IntVar(value=10)
        self.var_open = tk.BooleanVar(value=True)

        ttk.Label(frm_io, text="Archivo origen (.xlsx):").grid(row=0, column=0, sticky="w")
        ent_in = ttk.Entry(frm_io, textvariable=self.var_in, width=72); ent_in.grid(row=0, column=1, sticky="we", padx=(6,6))
        ttk.Button(frm_io, text="Examinar…", command=self.browse_in).grid(row=0, column=2)

        ttk.Label(frm_io, text="Carpeta destino:").grid(row=1, column=0, sticky="w")
        ent_out = ttk.Entry(frm_io, textvariable=self.var_out, width=72); ent_out.grid(row=1, column=1, sticky="we", padx=(6,6))
        ttk.Button(frm_io, text="Seleccionar…", command=self.browse_out).grid(row=1, column=2)

        ttk.Label(frm_io, text="Top N proveedores:").grid(row=2, column=0, sticky="w")
        spn = ttk.Spinbox(frm_io, from_=1, to=999, textvariable=self.var_topn, width=8); spn.grid(row=2, column=1, sticky="w", padx=(6,6))

        chk = ttk.Checkbutton(frm_io, text="Abrir HTML al terminar", variable=self.var_open)
        chk.grid(row=2, column=2, sticky="w")

        frm_io.grid_columnconfigure(1, weight=1)

        # Botones acción
        frm_btn = ttk.Frame(self); frm_btn.pack(fill="x", **pad)
        self.btn_gen = ttk.Button(frm_btn, text="Generar dashboard", command=self.on_generate)
        self.btn_gen.pack(side="left")
        self.btn_cancel = ttk.Button(frm_btn, text="Cancelar", command=self.on_cancel, state="disabled")
        self.btn_cancel.pack(side="left", padx=(8,0))

        # Progreso
        frm_prog = ttk.Frame(self); frm_prog.pack(fill="x", **pad)
        self.prog = ttk.Progressbar(frm_prog, length=300, mode="determinate", maximum=100)
        self.prog.pack(side="left", fill="x", expand=True)
        self.lbl_status = ttk.Label(frm_prog, text="Listo.")
        self.lbl_status.pack(side="left", padx=(8,0))

        # Logs
        frm_log = ttk.LabelFrame(self, text="Logs")
        frm_log.pack(fill="both", expand=True, **pad)
        self.txt_log = tk.Text(frm_log, height=12, state="disabled")
        self.txt_log.pack(fill="both", expand=True)
        # vincula handler
        self.tk_handler.text_widget = self.txt_log

    def prefill(self, args: dict):
        # Desde config
        in_cfg = self.config_data.get("last_input") if isinstance(self.config_data, dict) else None
        out_cfg = self.config_data.get("last_output_dir") if isinstance(self.config_data, dict) else None
        if in_cfg and not self.var_in.get(): self.var_in.set(in_cfg)
        if out_cfg and not self.var_out.get(): self.var_out.set(out_cfg)

        # Desde CLI
        if args.get("input"): self.var_in.set(args["input"])
        if args.get("output_dir"): self.var_out.set(args["output_dir"])
        if args.get("topn"): self.var_topn.set(int(args["topn"]))

    def save_config(self):
        try:
            data = {"last_input": self.var_in.get(), "last_output_dir": self.var_out.get()}
            with open(self.cfg_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def load_config(self):
        try:
            if self.cfg_path.exists():
                return json.loads(self.cfg_path.read_text(encoding="utf-8"))
        except Exception:
            return {}
        return {}

    def browse_in(self):
        fp = filedialog.askopenfilename(title="Seleccione archivo Excel", filetypes=[("Excel", "*.xlsx")])
        if fp:
            self.var_in.set(fp)

    def browse_out(self):
        dp = filedialog.askdirectory(title="Seleccione carpeta destino")
        if dp:
            self.var_out.set(dp)

    def on_generate(self):
        inp = Path(self.var_in.get().strip())
        outd = Path(self.var_out.get().strip() or ".")
        topn = int(self.var_topn.get() or 10)
        if not inp.exists():
            messagebox.showerror(APP_TITLE, "Debe seleccionar un archivo .xlsx válido.")
            return
        if not outd.exists():
            try:
                outd.mkdir(parents=True, exist_ok=True)
            except Exception as e:
                messagebox.showerror(APP_TITLE, f"No se pudo crear la carpeta destino: {e}")
                return
        self.save_config()
        self.cancel_ev.clear()
        params = JobParams(input_path=inp, output_dir=outd, topn=topn, open_when_done=bool(self.var_open.get()))
        self.worker = DashboardBuilder(params, self.logger, self.q, self.cancel_ev)
        self.btn_gen.configure(state="disabled")
        self.btn_cancel.configure(state="normal")
        self.prog.configure(value=0)
        self.lbl_status.configure(text="Procesando…")
        self.worker.start()

    def on_cancel(self):
        if self.worker and self.worker.is_alive():
            if messagebox.askyesno(APP_TITLE, "¿Cancelar el proceso en curso?"):
                self.cancel_ev.set()

    def poll_queue(self):
        try:
            while True:
                item = self.q.get_nowait()
                if item[0] == "progress":
                    self.prog.configure(value=item[1])
                elif item[0] == "log":
                    self.lbl_status.configure(text=item[1])
                elif item[0] == "done":
                    success, msg = item[1], item[2]
                    self.btn_gen.configure(state="normal")
                    self.btn_cancel.configure(state="disabled")
                    if success:
                        self.prog.configure(value=100)
                        self.lbl_status.configure(text="Completado.")
                        result_path = self.worker.result_path if self.worker else None
                        if result_path:
                            if self.worker.log_path and self.worker.log_path.exists():
                                self.logger.info(f"Log guardado en: {self.worker.log_path}")
                            if messagebox.showinfo(APP_TITLE, f"Dashboard generado:\n{result_path}\n\n¿Abrir carpeta?"):
                                try:
                                    # Abrir carpeta contenedora
                                    if sys.platform.startswith("win"):
                                        os.startfile(str(result_path.parent))
                                    elif sys.platform == "darwin":
                                        os.system(f"open '{result_path.parent}'")
                                    else:
                                        os.system(f"xdg-open '{result_path.parent}'")
                                except Exception:
                                    pass
                            if self.worker.params.open_when_done:
                                try:
                                    if sys.platform.startswith("win"):
                                        os.startfile(str(result_path))
                                    elif sys.platform == "darwin":
                                        os.system(f"open '{result_path}'")
                                    else:
                                        os.system(f"xdg-open '{result_path}'")
                                except Exception:
                                    pass
                    else:
                        self.prog.configure(value=0)
                        self.lbl_status.configure(text="Error.")
                        messagebox.showerror(APP_TITLE, msg)
        except queue.Empty:
            pass
        self.after(120, self.poll_queue)


def parse_args():
    p = argparse.ArgumentParser(description="Generar dashboard de costos (GUI)")
    p.add_argument("--input", help="Ruta del archivo .xlsx para pre-rellenar", default=None)
    p.add_argument("--output-dir", help="Carpeta destino para pre-rellenar", default=None)
    p.add_argument("--topn", type=int, help="Top N proveedores por defecto", default=None)
    return p.parse_args()

def main():
    args = parse_args()
    pre = {"input": args.input, "output_dir": args.output_dir, "topn": args.topn}
    app = App(pre)
    app.mainloop()

if __name__ == "__main__":
    main()
'''

script_path.write_text(script_code, encoding="utf-8")
script_path, script_path.exists()
