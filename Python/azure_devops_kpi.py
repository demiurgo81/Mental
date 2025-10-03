"""Genera un informe HTML de KPI de Azure DevOps a partir de la tabla Oracle DF_AZURE_PBIS."""

from __future__ import annotations

import copy
import datetime as dt
import html
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple, Callable

import pandas as pd
import pymongo
from pymongo import UpdateOne
from pymongo.collection import Collection
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from azure_devops_oracle_update import ORACLE_TABLE, connect_oracle, parse_table_identifier

MONGO_URI = "mongodb+srv://demiurgo:requiem@demiurgo.oqf9p2y.mongodb.net/?retryWrites=true&w=majority&appName=demiurgo"
MONGO_DB_NAME = "Cronos_AUX"
MONGO_COLLECTION_NAME = "azure_devops_kpis"
LEGACY_MONGO_DB_NAME = "financierosJP"

HTML_DEFAULT_FILENAME = "azure_devops_KPI.html"
CREATED_DATE_THRESHOLD_ISO = "2025-09-23"
ASSIGNED_NOT_ALLOWED = ("Juan Pablo Tellez Garay",)

DEFAULT_KPI_DEFINITIONS: List[Dict[str, Any]] = [
    {
        "codigo": "hut_total",
        "nombre": "Cantidad Total de HUT",
        "descripcion": "Numero total de HUT sin enlace y que siguen abiertas.",
        "tipo": "count",
        "filtros": [
            {"campo": "LINKTYPE", "operador": "es_nulo"},
            {"campo": "STATE", "operador": "no_en", "valores": ["Done", "Removed"]},
        ],
        "orden": 10,
        "categoria": "HUT",
        "version": 1,
    },
    {
        "codigo": "hut_nuevas",
        "nombre": "Cantidad HUT Nuevas",
        "descripcion": "Numero de HUT creadas despues de 23/09/2025 sin enlace y activas.",
        "tipo": "count",
        "filtros": [
            {"campo": "LINKTYPE", "operador": "es_nulo"},
            {"campo": "STATE", "operador": "no_en", "valores": ["Done", "Removed"]},
            {"campo": "CREATED_DATE", "operador": "mayor_fecha", "valor": CREATED_DATE_THRESHOLD_ISO},
        ],
        "orden": 20,
        "categoria": "HUT nuevas",
        "version": 1,
    },
    {
        "codigo": "hut_nuevas_bien_asignadas",
        "nombre": "Cantidad HUT Nuevas Bien Asignadas",
        "descripcion": "Comparacion de las HUT nuevas segun la asignacion realizada.",
        "tipo": "segmented_count",
        "filtros": [
            {"campo": "LINKTYPE", "operador": "es_nulo"},
            {"campo": "STATE", "operador": "no_en", "valores": ["Done", "Removed"]},
            {"campo": "CREATED_DATE", "operador": "mayor_fecha", "valor": CREATED_DATE_THRESHOLD_ISO},
        ],
        "segmentos": [
            {
                "codigo": "bien_asignadas",
                "nombre": "Bien asignadas",
                "descripcion": "Asignadas a integrantes distintos de Juan Pablo Tellez Garay.",
                "filtros": [
                    {"campo": "ASSIGNED_TO", "operador": "no_en", "valores": list(ASSIGNED_NOT_ALLOWED)},
                    {"campo": "ASSIGNED_TO", "operador": "no_es_nulo"},
                ],
                "orden": 10,
            },
            {
                "codigo": "mal_asignadas",
                "nombre": "Mal asignadas",
                "descripcion": "Asignadas a Juan Pablo Tellez Garay o sin responsable.",
                "complemento": True,
                "orden": 20,
            },
        ],
        "orden": 30,
        "categoria": "HUT nuevas",
        "version": 1,
    },
    {
        "codigo": "hut_nuevas_por_estado",
        "nombre": "Cantidad HUT Nuevas Asignadas Estado",
        "descripcion": "Distribucion porcentual de las HUT nuevas por estado.",
        "tipo": "group_count",
        "filtros": [
            {"campo": "LINKTYPE", "operador": "es_nulo"},
            {"campo": "STATE", "operador": "no_en", "valores": ["Done", "Removed"]},
            {"campo": "CREATED_DATE", "operador": "mayor_fecha", "valor": CREATED_DATE_THRESHOLD_ISO},
        ],
        "agrupar_por": "STATE",
        "orden": 40,
        "categoria": "HUT nuevas",
        "version": 1,
    },
    {
        "codigo": "hut_vencidas_por_estado",
        "nombre": "HUT Vencidas por Estado",
        "descripcion": "Distribucion de HUT vencidas por estado actual.",
        "tipo": "group_count",
        "filtros": [
            {"campo": "LINKTYPE", "operador": "es_nulo"},
            {"campo": "STATE", "operador": "no_en", "valores": ["Done", "Removed"]},
            {"campo": "COMPLETIONESTIMATEDATE", "operador": "menor_igual_hoy"},
        ],
        "agrupar_por": "STATE",
        "orden": 50,
        "categoria": "HUT vencidas",
        "version": 1,
    },
    {
        "codigo": "hut_vencidas_por_asignado",
        "nombre": "HUT Vencidas por Responsable",
        "descripcion": "Distribucion de HUT vencidas por responsable asignado.",
        "tipo": "group_count",
        "filtros": [
            {"campo": "LINKTYPE", "operador": "es_nulo"},
            {"campo": "STATE", "operador": "no_en", "valores": ["Done", "Removed"]},
            {"campo": "COMPLETIONESTIMATEDATE", "operador": "menor_igual_hoy"},
        ],
        "agrupar_por": "ASSIGNED_TO",
        "orden": 60,
        "categoria": "HUT vencidas",
        "version": 1,
    },
    {
        "codigo": "hut_vencidas_por_linea",
        "nombre": "HUT Vencidas por Linea de Producto",
        "descripcion": "Distribucion de HUT vencidas por linea de producto.",
        "tipo": "group_count",
        "filtros": [
            {"campo": "LINKTYPE", "operador": "es_nulo"},
            {"campo": "STATE", "operador": "no_en", "valores": ["Done", "Removed"]},
            {"campo": "COMPLETIONESTIMATEDATE", "operador": "menor_igual_hoy"},
        ],
        "agrupar_por": "LINEAPRODUCTO",
        "orden": 70,
        "categoria": "HUT vencidas",
        "version": 1,
    },
    {
        "codigo": "hut_vencidas_por_empresa",
        "nombre": "HUT Vencidas por Empresa",
        "descripcion": "Distribucion de HUT vencidas por empresa.",
        "tipo": "group_count",
        "filtros": [
            {"campo": "LINKTYPE", "operador": "es_nulo"},
            {"campo": "STATE", "operador": "no_en", "valores": ["Done", "Removed"]},
            {"campo": "COMPLETIONESTIMATEDATE", "operador": "menor_igual_hoy"},
        ],
        "agrupar_por": "EMPRESA",
        "orden": 80,
        "categoria": "HUT vencidas",
        "version": 1,
    },
]

REQUIRED_COLUMNS = [
    "ID",
    "LINKTYPE",
    "STATE",
    "CREATED_DATE",
    "ASSIGNED_TO",
    "COMPLETIONESTIMATEDATE",
    "LINEAPRODUCTO",
    "EMPRESA",
]


@contextmanager
def mongo_collection() -> Iterable[Collection]:
    client = pymongo.MongoClient(MONGO_URI)
    try:
        yield client[MONGO_DB_NAME][MONGO_COLLECTION_NAME]
    finally:
        client.close()


def ensure_default_definitions(collection: Collection) -> None:
    timestamp = dt.datetime.now(dt.timezone.utc)

    try:
        if collection.estimated_document_count() == 0 and LEGACY_MONGO_DB_NAME:
            legacy_collection = collection.database.client[LEGACY_MONGO_DB_NAME][MONGO_COLLECTION_NAME]
            legacy_docs = list(legacy_collection.find({}, {"_id": False}))
            if legacy_docs:
                collection.insert_many(legacy_docs, ordered=False)
    except Exception as exc:
        print(f"Advertencia migracion KPI Mongo: {exc}")

    operations: List[UpdateOne] = []
    for definition in DEFAULT_KPI_DEFINITIONS:
        codigo = definition.get("codigo")
        if not codigo:
            continue
        document = copy.deepcopy(definition)
        document.setdefault("actualizado_en", timestamp)
        operations.append(
            UpdateOne(
                {"codigo": codigo},
                {"$set": document, "$setOnInsert": {"creado_en": timestamp}},
                upsert=True,
            )
        )
    if operations:
        collection.bulk_write(operations, ordered=False)


def load_kpi_definitions() -> List[Dict[str, Any]]:
    try:
        with mongo_collection() as collection:
            ensure_default_definitions(collection)
            cursor = collection.find({}, {"_id": False}).sort([
                ("orden", pymongo.ASCENDING),
                ("nombre", pymongo.ASCENDING),
            ])
            documentos = list(cursor)
    except Exception as exc:
        print(f"Advertencia carga KPI Mongo: {exc}")
        documentos = []

    if not documentos:
        documentos = copy.deepcopy(DEFAULT_KPI_DEFINITIONS)

    return documentos


def get_table_reference() -> str:
    owner, table = parse_table_identifier(ORACLE_TABLE)
    if owner:
        return f'"{owner}"."{table}"'
    return f'"{table}"'


def fetch_oracle_dataframe(
    columns: Sequence[str],
    logger: Optional[Callable[[str], None]] = None,
) -> pd.DataFrame:
    start_time = time.perf_counter()

    def emit(message: str) -> None:
        if logger is None:
            return
        try:
            logger(message)
        except Exception:
            pass

    table_ref = get_table_reference()
    select_clause = ", ".join(columns)
    query = f"SELECT {select_clause} FROM {table_ref}"
    emit(f"Consulta generada: {query}")
    emit("Conectando a Oracle...")
    conn = connect_oracle()
    emit("Conexion establecida. Creando cursor...")
    rows: List[Tuple[Any, ...]] = []
    column_names: List[str] = list(columns)
    try:
        cursor = conn.cursor()
        emit("Cursor listo. Ejecutando consulta...")
        try:
            cursor.execute(query)
            emit("Consulta ejecutada. Recuperando filas...")
            rows = cursor.fetchall()
            column_names = [desc[0] for desc in cursor.description]
            emit(f"Filas recuperadas: {len(rows)}")
        finally:
            cursor.close()
            emit("Cursor cerrado.")
    finally:
        conn.close()
        elapsed = time.perf_counter() - start_time
        emit(f"Conexion cerrada. Duracion total de la consulta: {elapsed:.2f} s.")
    return pd.DataFrame(rows, columns=column_names)

def prepare_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    prepared = df.copy()
    for column in ("CREATED_DATE", "COMPLETIONESTIMATEDATE"):
        if column in prepared.columns:
            prepared[column] = pd.to_datetime(prepared[column], errors="coerce")
    for column in ("LINKTYPE", "STATE", "ASSIGNED_TO", "LINEAPRODUCTO", "EMPRESA"):
        if column in prepared.columns:
            prepared[column] = prepared[column].astype("string").str.strip()
    return prepared


def parse_iso_date(value: str) -> pd.Timestamp:
    if not value:
        raise ValueError("Se requiere un valor de fecha en formato ISO (YYYY-MM-DD).")
    timestamp = pd.to_datetime(value, format="%Y-%m-%d", errors="coerce")
    if pd.isna(timestamp):
        timestamp = pd.to_datetime(value, errors="coerce")
    if pd.isna(timestamp):
        raise ValueError(f"No se pudo interpretar la fecha '{value}'.")
    python_dt = pd.Timestamp(timestamp).to_pydatetime().replace(tzinfo=None)
    return pd.Timestamp(python_dt)


def format_int(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def format_pct(value: float) -> str:
    return f"{value:0.1f}".replace(".", ",")


def format_date(value: Optional[pd.Timestamp]) -> str:
    if value is None or pd.isna(value):
        return "Sin datos"
    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()
    return value.strftime("%d/%m/%Y")


def format_datetime(value: dt.datetime) -> str:
    if isinstance(value, pd.Timestamp):
        value = value.to_pydatetime()
    return value.strftime("%d/%m/%Y %H:%M")


def apply_filters(df: pd.DataFrame, filtros: Sequence[Dict[str, Any]]) -> pd.DataFrame:
    if not filtros:
        return df.copy()
    mask = pd.Series(True, index=df.index)
    for filtro in filtros:
        campo = filtro.get("campo")
        operador = filtro.get("operador")
        if not campo:
            raise ValueError("Filtro sin campo definido.")
        if campo not in df.columns:
            raise KeyError(f"La columna '{campo}' no existe en los datos consultados.")
        serie = df[campo]
        if operador == "es_nulo":
            mask &= serie.isna()
        elif operador == "no_en":
            valores = filtro.get("valores") or []
            mask &= ~serie.isin(valores)
        elif operador == "en":
            valores = filtro.get("valores") or []
            mask &= serie.isin(valores)
        elif operador == "no_es_nulo":
            mask &= serie.notna()
        elif operador == "mayor_fecha":
            valor = filtro.get("valor")
            if not valor:
                raise ValueError("El operador 'mayor_fecha' requiere un valor.")
            referencia = parse_iso_date(str(valor))
            serie_dt = pd.to_datetime(serie, errors="coerce")
            mask &= serie_dt > referencia
        elif operador == "menor_igual_hoy":
            serie_dt = pd.to_datetime(serie, errors="coerce")
            ahora = pd.Timestamp.now(tz=None)
            mask &= serie_dt.notna() & (serie_dt <= ahora)
        else:
            raise ValueError(f"Operador de filtro no soportado: {operador}")
    return df.loc[mask].copy()


def describe_filters(filtros: Sequence[Dict[str, Any]]) -> str:
    if not filtros:
        return ""
    fragments: List[str] = []
    for filtro in filtros:
        campo = filtro.get("campo", "")
        operador = filtro.get("operador")
        if operador == "es_nulo":
            fragments.append(f"{campo} es nulo")
        elif operador == "no_en":
            valores = ", ".join(str(val) for val in filtro.get("valores", []))
            fragments.append(f"{campo} no en ({valores})")
        elif operador == "en":
            valores = ", ".join(str(val) for val in filtro.get("valores", []))
            fragments.append(f"{campo} en ({valores})")
        elif operador == "no_es_nulo":
            fragments.append(f"{campo} no es nulo")
        elif operador == "mayor_fecha":
            valor = filtro.get("valor")
            if valor:
                fecha = format_date(parse_iso_date(str(valor)))
                fragments.append(f"{campo} > {fecha}")
        elif operador == "menor_igual_hoy":
            fragments.append(f"{campo} <= hoy")
        else:
            fragments.append(f"{campo} {operador}")
    return "; ".join(fragments)

def evaluate_kpi(df: pd.DataFrame, definition: Dict[str, Any]) -> Dict[str, Any]:
    filtros = definition.get("filtros") or []
    base_df = apply_filters(df, filtros)
    base_total = int(len(base_df))
    tipo = definition.get("tipo", "count")
    result: Dict[str, Any] = {
        "codigo": definition.get("codigo"),
        "nombre": definition.get("nombre"),
        "descripcion": definition.get("descripcion", ""),
        "tipo": tipo,
        "base_total": base_total,
        "descripcion_filtros": describe_filters(filtros),
    }
    if tipo == "count":
        result["data"] = {"total": base_total}
        return result
    if tipo == "segmented_count":
        segmentos_conf = definition.get("segmentos") or []
        segmentos_result: List[Dict[str, Any]] = []
        used_indices: Set[Any] = set()
        for segmento in sorted(segmentos_conf, key=lambda item: item.get("orden", 0)):
            segment_filters = segmento.get("filtros") or []
            complemento = bool(segmento.get("complemento"))
            if complemento:
                segment_df = base_df.loc[~base_df.index.isin(used_indices)]
            else:
                segment_df = apply_filters(base_df, segment_filters)
                if used_indices:
                    segment_df = segment_df.loc[~segment_df.index.isin(used_indices)]
            cantidad = int(len(segment_df))
            porcentaje = (cantidad / base_total * 100.0) if base_total else 0.0
            segmentos_result.append(
                {
                    "codigo": segmento.get("codigo"),
                    "nombre": segmento.get("nombre"),
                    "descripcion": segmento.get("descripcion", ""),
                    "cantidad": cantidad,
                    "porcentaje": porcentaje,
                }
            )
            used_indices.update(segment_df.index.tolist())
        result["data"] = {
            "total": base_total,
            "segmentos": segmentos_result,
        }
        return result
    if tipo == "group_count":
        campo = definition.get("agrupar_por")
        if not campo:
            raise ValueError(f"KPI '{definition.get('codigo')}' requiere el atributo 'agrupar_por'.")
        if campo not in base_df.columns:
            raise KeyError(f"La columna '{campo}' no existe en los datos filtrados.")
        series = base_df[campo].fillna("Sin valor")
        conteos = series.value_counts(dropna=False)
        items: List[Dict[str, Any]] = []
        for valor, cantidad in conteos.items():
            porcentaje = (cantidad / base_total * 100.0) if base_total else 0.0
            items.append(
                {
                    "valor": str(valor),
                    "conteo": int(cantidad),
                    "porcentaje": porcentaje,
                }
            )
        items.sort(key=lambda item: item["conteo"], reverse=True)
        result["data"] = {"total": base_total, "items": items, "campo": campo}
        return result
    raise ValueError(f"Tipo de KPI no soportado: {tipo}")


def evaluate_kpis(df: pd.DataFrame, definitions: Sequence[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[str]]:
    results: List[Dict[str, Any]] = []
    issues: List[str] = []
    for definition in definitions:
        codigo = definition.get("codigo", "<sin_codigo>")
        try:
            results.append(evaluate_kpi(df, definition))
        except Exception as exc:
            issues.append(f"{codigo}: {exc}")
    return results, issues


def get_date_range(df: pd.DataFrame, column: str) -> Tuple[Optional[pd.Timestamp], Optional[pd.Timestamp]]:
    if column not in df.columns:
        return None, None
    series = pd.to_datetime(df[column], errors="coerce").dropna()
    if series.empty:
        return None, None
    return series.min(), series.max()


def render_kpi_section(result: Dict[str, Any]) -> str:
    nombre = html.escape(result.get("nombre", "KPI"))
    descripcion = result.get("descripcion", "")
    filtros = result.get("descripcion_filtros", "")
    tipo = result.get("tipo")
    base_total = result.get("base_total", 0)

    tooltip_parts: List[str] = []
    if descripcion:
        tooltip_parts.append(html.escape(descripcion).replace("\n", "<br />"))
    if filtros:
        tooltip_parts.append(f"<strong>Filtros base:</strong> {html.escape(filtros)}")
    tooltip_html = "<br />".join(part for part in tooltip_parts if part)

    parts: List[str] = ["<section class=\"kpi-card\">", "  <div class=\"kpi-header\">", f"    <h2>{nombre}</h2>"]
    if tooltip_html:
        parts.append("    <span class=\"info-icon\" tabindex=\"0\" aria-label=\"Ver detalle del KPI\">i</span>")
        parts.append(f"    <div class=\"kpi-tooltip\">{tooltip_html}</div>")
    parts.append("  </div>")

    if tipo == "count":
        total = result.get("data", {}).get("total", 0)
        parts.append("  <div class=\"metric-highlight\">")
        parts.append(f"    <span class=\"metric-value\">{format_int(total)}</span>")
        parts.append("    <span class=\"metric-label\">Registros</span>")
        parts.append("  </div>")
    elif tipo == "segmented_count":
        data = result.get("data", {})
        segmentos = data.get("segmentos", [])
        parts.append("  <div class=\"metric-highlight\">")
        parts.append(f"    <span class=\"metric-value\">{format_int(base_total)}</span>")
        parts.append("    <span class=\"metric-label\">Total base</span>")
        parts.append("  </div>")
        parts.append("  <table class=\"data-table\">")
        parts.append("    <thead><tr><th>Segmento</th><th class=\"num\">Cantidad</th><th class=\"num\">% sobre total</th></tr></thead>")
        parts.append("    <tbody>")
        for segmento in segmentos:
            seg_nombre = html.escape(segmento.get("nombre", "Segmento"))
            cantidad_txt = format_int(segmento.get("cantidad", 0))
            porcentaje_val = segmento.get("porcentaje", 0.0)
            porcentaje_txt = format_pct(porcentaje_val)
            parts.append(f"      <tr><td>{seg_nombre}</td><td class=\"num\">{cantidad_txt}</td><td class=\"num\">{porcentaje_txt}%</td></tr>")
        parts.append("    </tbody>")
        parts.append("  </table>")
        if segmentos:
            parts.append("  <div class=\"chart-block\">")
            for segmento in segmentos:
                seg_nombre = html.escape(segmento.get("nombre", "Segmento"))
                porcentaje_val = segmento.get("porcentaje", 0.0)
                porcentaje_txt = format_pct(porcentaje_val)
                cantidad_txt = format_int(segmento.get("cantidad", 0))
                width = max(min(porcentaje_val, 100.0), 0.0)
                parts.append("    <div class=\"chart-row\">")
                parts.append(f"      <span class=\"chart-label\">{seg_nombre}</span>")
                parts.append("      <div class=\"chart-bar\">")
                parts.append(f"        <span class=\"chart-fill\" style=\"width: {width:.2f}%;\">{cantidad_txt}</span>")
                parts.append("      </div>")
                parts.append(f"      <span class=\"chart-pct\">{porcentaje_txt}%</span>")
                parts.append("    </div>")
            parts.append("  </div>")
    elif tipo == "group_count":
        data = result.get("data", {})
        items = data.get("items", [])
        campo = html.escape(str(data.get("campo", "")))
        parts.append("  <div class=\"metric-highlight\">")
        parts.append(f"    <span class=\"metric-value\">{format_int(base_total)}</span>")
        parts.append(f"    <span class=\"metric-label\">Registros evaluados por {campo}</span>")
        parts.append("  </div>")
        parts.append("  <table class=\"data-table\">")
        parts.append("    <thead><tr><th>Categoria</th><th class=\"num\">Cantidad</th><th class=\"num\">% sobre total</th></tr></thead>")
        parts.append("    <tbody>")
        for item in items:
            categoria = html.escape(item.get("valor", ""))
            cantidad = format_int(item.get("conteo", 0))
            porcentaje = item.get("porcentaje", 0.0)
            porcentaje_txt = format_pct(porcentaje)
            parts.append(f"      <tr><td>{categoria}</td><td class=\"num\">{cantidad}</td><td class=\"num\">{porcentaje_txt}%</td></tr>")
        parts.append("    </tbody>")
        parts.append("  </table>")
        if items:
            parts.append("  <div class=\"chart-block\">")
            for item in items:
                categoria = html.escape(item.get("valor", ""))
                porcentaje = item.get("porcentaje", 0.0)
                porcentaje_txt = format_pct(porcentaje)
                cantidad_txt = format_int(item.get("conteo", 0))
                width = max(min(porcentaje, 100.0), 0.0)
                parts.append("    <div class=\"chart-row\">")
                parts.append(f"      <span class=\"chart-label\">{categoria}</span>")
                parts.append("      <div class=\"chart-bar\">")
                parts.append(f"        <span class=\"chart-fill\" style=\"width: {width:.2f}%;\">{cantidad_txt}</span>")
                parts.append("      </div>")
                parts.append(f"      <span class=\"chart-pct\">{porcentaje_txt}%</span>")
                parts.append("    </div>")
            parts.append("  </div>")
    else:
        parts.append("  <p>No hay visualizacion disponible para este tipo de KPI.</p>")
    parts.append("</section>")
    return "\n".join(parts)


def render_html_report(context: Dict[str, Any]) -> str:
    generated_at: dt.datetime = context["generated_at"]
    total_records: int = context["total_records"]
    oracle_table: str = context["oracle_table"]
    warnings = context.get("warnings") or []
    kpi_results = context.get("kpi_results") or []
    date_range = context.get("date_range") or (None, None)
    selected_names = context.get("selected_names") or []

    generated_txt = format_datetime(generated_at)
    total_txt = format_int(total_records)
    if any(date_range):
        rango_txt = f"{format_date(date_range[0])} - {format_date(date_range[1])}"
    else:
        rango_txt = "Sin datos"
    kpi_count_txt = str(len(kpi_results))
    if selected_names:
        header_note = "KPIs incluidos: " + ", ".join(html.escape(name) for name in selected_names)
    else:
        header_note = ""

    warnings_html = ""
    if warnings:
        items = "".join(f"<li>{html.escape(msg)}</li>" for msg in warnings)
        warnings_html = (
            "<section class=\"warning-card\">"
            "<h2>Advertencias</h2>"
            f"<ul>{items}</ul>"
            "</section>"
        )

    kpi_html = "\n".join(render_kpi_section(result) for result in kpi_results)

    return f"""<!DOCTYPE html>
<html lang="es">
<head>
    <meta charset="utf-8" />
    <meta http-equiv="X-UA-Compatible" content="IE=edge" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Informe KPI Azure DevOps</title>
    <style>
        body {{
            font-family: "Segoe UI", Arial, sans-serif;
            background-color: #f5f7fb;
            color: #1f2a44;
            margin: 0;
        }}
        header {{
            background: linear-gradient(135deg, #112d60 0%, #2156a5 100%);
            color: #ffffff;
            padding: 28px 36px;
        }}
        header h1 {{
            margin: 0;
            font-size: 26px;
        }}
        header p {{
            margin: 8px 0 0 0;
            font-size: 14px;
            opacity: 0.85;
        }}
        main {{
            padding: 28px 36px 48px 36px;
        }}
        .summary {{
            display: flex;
            flex-wrap: wrap;
            gap: 18px;
            margin-bottom: 24px;
        }}
        .summary-card {{
            background: #ffffff;
            border-radius: 14px;
            padding: 18px 22px;
            box-shadow: 0 8px 20px rgba(18, 38, 95, 0.12);
            min-width: 220px;
        }}
        .summary-card span {{
            display: block;
        }}
        .summary-card .label {{
            font-size: 13px;
            color: #5b6d86;
            margin-bottom: 6px;
            text-transform: uppercase;
            letter-spacing: 0.06em;
        }}
        .summary-card .value {{
            font-size: 22px;
            font-weight: 600;
        }}
        .summary-card .secondary {{
            font-size: 12px;
            color: #6c7c96;
            margin-top: 6px;
        }}
        .kpi-card {{
            background: #ffffff;
            border-radius: 14px;
            padding: 24px 26px;
            box-shadow: 0 10px 24px rgba(15, 32, 86, 0.12);
            margin-bottom: 26px;
        }}
        .kpi-header {{
            display: flex;
            align-items: center;
            gap: 10px;
            position: relative;
            flex-wrap: wrap;
        }}
        .kpi-header h2 {{
            margin: 0;
            font-size: 20px;
            color: #152347;
        }}
        .info-icon {{
            display: inline-flex;
            align-items: center;
            justify-content: center;
            width: 22px;
            height: 22px;
            border-radius: 50%;
            background: #2156a5;
            color: #ffffff;
            font-size: 12px;
            font-weight: 600;
            cursor: pointer;
        }}
        .info-icon:focus {{
            outline: none;
            box-shadow: 0 0 0 3px rgba(33, 86, 165, 0.35);
        }}
        .kpi-tooltip {{
            position: absolute;
            top: calc(100% + 12px);
            left: 0;
            background: #ffffff;
            color: #2b3a5b;
            border-radius: 10px;
            padding: 12px 16px;
            box-shadow: 0 14px 30px rgba(17, 45, 96, 0.22);
            font-size: 13px;
            line-height: 1.45;
            max-width: 360px;
            opacity: 0;
            visibility: hidden;
            transform: translateY(-8px);
            transition: all 0.18s ease-in-out;
            z-index: 20;
        }}
        .kpi-header:hover .kpi-tooltip,
        .info-icon:hover + .kpi-tooltip,
        .info-icon:focus + .kpi-tooltip {{
            opacity: 1;
            visibility: visible;
            transform: translateY(0);
        }}
        .metric-highlight {{
            display: inline-flex;
            flex-direction: column;
            align-items: flex-start;
            background: #112d60;
            color: #ffffff;
            border-radius: 12px;
            padding: 16px 20px;
            margin-bottom: 18px;
        }}
        .metric-value {{
            font-size: 30px;
            font-weight: 700;
            line-height: 1;
        }}
        .metric-label {{
            margin-top: 4px;
            font-size: 13px;
            opacity: 0.9;
            letter-spacing: 0.04em;
        }}
        .data-table {{
            width: 100%;
            border-collapse: collapse;
            margin-bottom: 16px;
        }}
        .data-table th,
        .data-table td {{
            border-bottom: 1px solid #e2e8f4;
            padding: 9px 12px;
            text-align: left;
            font-size: 14px;
        }}
        .data-table th {{
            background: #f0f4ff;
            color: #1c335f;
            font-weight: 600;
        }}
        .data-table td.num {{
            text-align: right;
            font-variant-numeric: tabular-nums;
        }}
        .chart-block {{
            margin-top: 12px;
            display: flex;
            flex-direction: column;
            gap: 10px;
        }}
        .chart-row {{
            display: grid;
            grid-template-columns: 160px 1fr 70px;
            align-items: center;
            gap: 12px;
        }}
        .chart-label {{
            font-size: 14px;
            color: #21345a;
        }}
        .chart-bar {{
            background: #e5ecfb;
            border-radius: 999px;
            overflow: hidden;
            position: relative;
            height: 28px;
        }}
        .chart-fill {{
            display: inline-block;
            height: 100%;
            background: linear-gradient(135deg, #1c6dd0 0%, #33a3ff 100%);
            color: #ffffff;
            font-size: 13px;
            font-weight: 600;
            padding: 0 12px;
            line-height: 28px;
            min-width: 36px;
        }}
        .chart-pct {{
            text-align: right;
            font-size: 14px;
            font-variant-numeric: tabular-nums;
            color: #21345a;
        }}
        .warning-card {{
            background: #fff4e5;
            border-left: 4px solid #f1a33c;
            padding: 18px 22px;
            border-radius: 12px;
            margin-bottom: 26px;
        }}
        .warning-card h2 {{
            margin: 0 0 8px 0;
            font-size: 18px;
            color: #b86a15;
        }}
        .warning-card ul {{
            margin: 0;
            padding-left: 20px;
            color: #935c17;
            font-size: 14px;
        }}
        footer {{
            margin-top: 32px;
            font-size: 12px;
            color: #6f7d92;
            text-align: center;
        }}
    </style>
</head>
<body>
    <header>
        <h1>Informe KPI Azure DevOps</h1>
        <p>Generado el {html.escape(generated_txt)}. Fuente Oracle: {html.escape(oracle_table)}.</p>
        <p>{html.escape(header_note)}</p>
    </header>
    <main>
        <section class="summary">
            <article class="summary-card">
                <span class="label">Registros analizados</span>
                <span class="value">{html.escape(total_txt)}</span>
            </article>
            <article class="summary-card">
                <span class="label">Rango de fechas (CREATED_DATE)</span>
                <span class="value">{html.escape(rango_txt)}</span>
            </article>
            <article class="summary-card">
                <span class="label">Cantidad de KPI</span>
                <span class="value">{html.escape(kpi_count_txt)}</span>
                <span class="secondary">Informe compatible con navegadores modernos.</span>
            </article>
        </section>
        {warnings_html}
        {kpi_html}
    </main>
    <footer>
        Informe generado autom&aacute;ticamente. Formato UTF-8 y compatible con los principales navegadores.
    </footer>
</body>
</html>"""

class KPIApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Generador de KPI Azure DevOps")
        self.root.geometry("820x720")
        self.root.minsize(780, 640)

        self.output_path = tk.StringVar(value=str(Path.cwd() / HTML_DEFAULT_FILENAME))
        self.kpi_vars: Dict[str, tk.BooleanVar] = {}
        self.kpi_checkbuttons: List[ttk.Checkbutton] = []
        self.generate_button: Optional[ttk.Button] = None
        self.browse_button: Optional[ttk.Button] = None
        self.log_text: Optional[tk.Text] = None
        self.progress: Optional[ttk.Progressbar] = None

        try:
            self.definitions = load_kpi_definitions()
        except Exception as exc:
            messagebox.showerror("Conexion MongoDB", f"No fue posible cargar las definiciones de KPI:\n{exc}")
            self.definitions = []

        self.generate_button = self._build_ui()

        if self.definitions:
            self.log(f"{len(self.definitions)} KPI disponibles.")
        else:
            self.log("No hay definiciones de KPI disponibles. Revise la conexion a MongoDB.")
            if self.generate_button:
                self.generate_button["state"] = "disabled"

        self.log(f"Archivo de salida: {self.output_path.get()}")

    def _build_ui(self) -> ttk.Button:
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Header.TLabel", font=("Segoe UI", 18, "bold"))
        style.configure("Body.TLabel", font=("Segoe UI", 10))
        style.configure("KpiCheck.TCheckbutton", font=("Segoe UI", 11, "bold"))
        style.configure("KpiDesc.TLabel", font=("Segoe UI", 9), foreground="#556479")

        main_frame = ttk.Frame(self.root, padding="24 20 24 24")
        main_frame.pack(fill="both", expand=True)

        header = ttk.Label(
            main_frame,
            text="Generador de informe KPI Azure DevOps",
            style="Header.TLabel",
        )
        header.pack(anchor="w")

        subtitle = ttk.Label(
            main_frame,
            text="Seleccione el destino del archivo y los KPI que desea incluir.",
            style="Body.TLabel",
        )
        subtitle.pack(anchor="w", pady=(4, 18))

        output_frame = ttk.Frame(main_frame)
        output_frame.pack(fill="x", pady=(0, 18))

        ttk.Label(output_frame, text="Archivo HTML de salida:", style="Body.TLabel").pack(side="left")
        output_entry = ttk.Entry(output_frame, textvariable=self.output_path)
        output_entry.pack(side="left", fill="x", expand=True, padx=(12, 12))
        self.browse_button = ttk.Button(output_frame, text="Seleccionar...", command=self.ask_output_path)
        self.browse_button.pack(side="left")

        kpi_frame = ttk.LabelFrame(main_frame, text="KPI disponibles", padding="12 10 12 12")
        kpi_frame.pack(fill="x", pady=(0, 18))

        kpi_inner = ttk.Frame(kpi_frame)
        kpi_inner.pack(fill="x")

        for definition in self.definitions:
            codigo = definition.get("codigo")
            if not codigo:
                continue
            var = tk.BooleanVar(value=True)
            self.kpi_vars[codigo] = var

            row_frame = ttk.Frame(kpi_inner, padding="4 6 4 6")
            row_frame.pack(fill="x", expand=True, pady=2)

            check = ttk.Checkbutton(
                row_frame,
                text=definition.get("nombre", codigo),
                variable=var,
                style="KpiCheck.TCheckbutton",
            )
            check.pack(anchor="w")
            self.kpi_checkbuttons.append(check)

            descripcion = definition.get("descripcion")
            if descripcion:
                ttk.Label(
                    row_frame,
                    text=descripcion,
                    style="KpiDesc.TLabel",
                    wraplength=720,
                    justify="left",
                ).pack(anchor="w", padx=(28, 0))

        control_frame = ttk.Frame(main_frame)
        control_frame.pack(fill="x", pady=(0, 12))

        generate_button = ttk.Button(
            control_frame,
            text="Generar informe",
            command=self.generate_report,
        )
        generate_button.pack(side="right")
        self.generate_button = generate_button

        self.progress = ttk.Progressbar(main_frame, mode="indeterminate")
        self.progress.pack(fill="x", pady=(0, 16))

        log_frame = ttk.LabelFrame(main_frame, text="Progreso", padding="12 10 12 12")
        log_frame.pack(fill="both", expand=True)

        self.log_text = tk.Text(
            log_frame,
            height=12,
            state="disabled",
            wrap="word",
            background="#0f172a",
            foreground="#e2e8f0",
            font=("Consolas", 10),
        )
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=scrollbar.set)
        self.log_text.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        return generate_button

    def get_generate_button(self) -> Optional[ttk.Button]:
        return self.generate_button if self.generate_button else None

    def ask_output_path(self) -> None:
        selected = filedialog.asksaveasfilename(
            title="Seleccione el archivo de salida",
            defaultextension=".html",
            initialfile=HTML_DEFAULT_FILENAME,
            filetypes=[("Archivo HTML", "*.html"), ("Todos los archivos", "*.*")],
        )
        if selected:
            self.output_path.set(selected)
            self.log(f"Destino actualizado: {selected}")

    def generate_report(self) -> None:
        selected_codes = [code for code, var in self.kpi_vars.items() if var.get()]
        if not selected_codes:
            messagebox.showwarning("KPI no seleccionados", "Seleccione al menos un KPI para generar el informe.")
            self.log("Generacion cancelada: no se seleccionaron KPI.")
            return

        self.log(f"KPI seleccionados ({len(selected_codes)}): {', '.join(selected_codes)}")

        raw_path = self.output_path.get().strip()
        if not raw_path:
            raw_path = str(Path.cwd() / HTML_DEFAULT_FILENAME)
            self.output_path.set(raw_path)
            self.log(f"Ruta de salida vacia. Se usara: {raw_path}")
        path = Path(raw_path)
        if path.suffix.lower() != ".html":
            path = path.with_suffix(".html")
            self.output_path.set(str(path))
            self.log(f"Extension ajustada a HTML: {path}")

        self._toggle_controls(enabled=False)
        if self.progress:
            self.progress.start(12)

        self.log(f"Iniciando generacion del informe: {path}")
        worker = threading.Thread(target=self._worker, args=(path, selected_codes), daemon=True)
        worker.start()

    def _toggle_controls(self, enabled: bool) -> None:
        state = "normal" if enabled else "disabled"
        if self.generate_button:
            self.generate_button["state"] = state
        if self.browse_button:
            self.browse_button["state"] = state
        for check in self.kpi_checkbuttons:
            check["state"] = state

    def log(self, message: str) -> None:
        if not self.log_text:
            return
        timestamp = dt.datetime.now().strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"[{timestamp}] {message}\n")
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def log_async(self, message: str) -> None:
        self.root.after(0, self.log, message)

    def _worker(self, path: Path, selected_codes: Sequence[str]) -> None:
        warnings: List[str] = []
        try:
            self.log_async("Consultando definiciones de KPI en MongoDB...")
            all_definitions = load_kpi_definitions()
            self.log_async(f"Definiciones obtenidas: {len(all_definitions)}")
            definition_map = {item.get("codigo"): item for item in all_definitions}
            definitions: List[Dict[str, Any]] = []
            for code in selected_codes:
                definition = definition_map.get(code)
                if definition:
                    definitions.append(definition)
                else:
                    warning = f"Definicion no encontrada para el KPI '{code}'."
                    warnings.append(warning)
                    self.log_async(f"Advertencia: {warning}")
            if not definitions:
                raise RuntimeError("No hay definiciones de KPI disponibles para la seleccion.")
            self.log_async(f"KPI activos para el informe: {len(definitions)}")

            self.log_async("Iniciando consulta a Oracle...")
            query_start = time.perf_counter()
            df = fetch_oracle_dataframe(REQUIRED_COLUMNS, logger=self.log_async)
            query_elapsed = time.perf_counter() - query_start
            self.log_async(f"Consulta completada en {query_elapsed:.2f} s. Registros recuperados: {len(df)}")

            self.log_async("Normalizando datos recibidos...")
            prepared_df = prepare_dataframe(df)
            self.log_async(f"Datos preparados: {prepared_df.shape[0]} filas x {prepared_df.shape[1]} columnas.")

            self.log_async("Evaluando KPI seleccionados...")
            eval_start = time.perf_counter()
            results, evaluation_warnings = evaluate_kpis(prepared_df, definitions)
            eval_elapsed = time.perf_counter() - eval_start
            self.log_async(f"KPI evaluados en {eval_elapsed:.2f} s. Resultados generados: {len(results)}")
            for warning in evaluation_warnings:
                self.log_async(f"Advertencia de calculo: {warning}")
            warnings.extend(evaluation_warnings)

            date_range = get_date_range(prepared_df, "CREATED_DATE")
            context = {
                "generated_at": dt.datetime.now(),
                "oracle_table": get_table_reference(),
                "total_records": int(len(prepared_df)),
                "kpi_results": results,
                "warnings": warnings,
                "date_range": date_range,
                "selected_names": [
                    definition_map[code].get("nombre", code)
                    for code in selected_codes
                    if code in definition_map
                ],
            }
            if not results:
                raise RuntimeError("No se pudo calcular ningun KPI con los datos recibidos.")

            self.log_async("Construyendo informe HTML...")
            html_content = render_html_report(context)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(html_content, encoding="utf-8")
            try:
                size_bytes = path.stat().st_size
                self.log_async(f"Informe generado correctamente en {path} ({size_bytes} bytes)")
            except Exception:
                self.log_async(f"Informe generado correctamente en {path}")
            self._worker_done(success=True, path=path, warnings=warnings)
        except Exception as exc:
            self.log_async(f"Error durante la generacion: {exc}")
            self._worker_done(success=False, error=str(exc))

    def _worker_done(
        self,
        success: bool,
        path: Optional[Path] = None,
        error: Optional[str] = None,
        warnings: Optional[Sequence[str]] = None,
    ) -> None:
        def finalize() -> None:
            if self.progress:
                self.progress.stop()
            self._toggle_controls(enabled=True)
            if success:
                message = "Informe generado correctamente."
                if path:
                    message += f"\nUbicacion: {path}"
                if warnings:
                    message += "\n\nAdvertencias detectadas:\n- " + "\n- ".join(warnings)
                self.log("Proceso completado correctamente.")
                messagebox.showinfo("Proceso completado", message)
            else:
                message = error or "Error desconocido durante la generacion."
                self.log(f"Proceso interrumpido: {message}")
                messagebox.showerror("Proceso interrumpido", message)

        self.root.after(0, finalize)

def main() -> None:
    root = tk.Tk()
    KPIApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
