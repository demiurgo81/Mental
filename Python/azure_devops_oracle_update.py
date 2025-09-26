"""
azure_devops_oracle_update.py

Descarga los Work Items de una consulta guardada en Azure DevOps y
actualiza la tabla PDB_CRONUS.DF_AZURE_PBIS en Oracle.
"""
from __future__ import annotations

import json
import re
import datetime
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Sequence
from urllib.parse import quote

import html
import pandas as pd
import requests
import unicodedata
from pandas import CategoricalDtype, DatetimeTZDtype
from pandas.api.types import is_datetime64_any_dtype, is_object_dtype, is_string_dtype

try:  # prefer oracledb (thin) but allow cx_Oracle fallback
    import oracledb as db  # type: ignore
except ImportError:  # pragma: no cover - dependencia opcional
    import cx_Oracle as db  # type: ignore

API_VERSION = "7.0"
MAX_BATCH = 200
GUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")
ISO_Z_REGEX = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")

CONFIG_FILE = Path(__file__).with_name("azure_devops_oracle_update_config.json")
TOKEN_ENV_VARS = (
    "AZDO_PERSONAL_ACCESS_TOKEN",
    "AZURE_DEVOPS_PAT",
)
ORACLE_HOST = "100.126.98.25"
ORACLE_PORT = 1850
ORACLE_SERVICE = "PDB_IVRCONV"
ORACLE_USER = "PDB_CRONUS"
ORACLE_PASSWORD = "C7ar0_2o2s"
ORACLE_TABLE = '"PDB_CRONUS"."DF_AZURE_PBIS"'

EXCLUDED_DB_COLUMNS = {"FECHACREACION", "FECHAMODIFICACION"}


IDENTIFIER_CLEAN_RE = re.compile(r"[^0-9A-Za-z]+")


def sanitize_db_identifier(name: str, fallback: str) -> str:
    normalized = unicodedata.normalize("NFKD", str(name or ""))
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_name = IDENTIFIER_CLEAN_RE.sub("_", ascii_name)
    ascii_name = re.sub(r"_+", "_", ascii_name)
    ascii_name = ascii_name.strip("_").upper()
    if not ascii_name:
        return fallback
    return ascii_name


def build_db_column_names(columns: Sequence[str]) -> List[str]:
    assigned: set[str] = set()
    counts: Dict[str, int] = {}
    result: List[str] = []
    for idx, column in enumerate(columns, start=1):
        base = sanitize_db_identifier(column, f"COL_{idx}")
        count = counts.get(base, 0)
        candidate = base if count == 0 else f"{base}_{count}"
        while candidate in assigned:
            count += 1
            candidate = f"{base}_{count}"
        counts[base] = count + 1
        assigned.add(candidate)
        result.append(candidate)
    return result


def parse_table_identifier(identifier: str) -> tuple[str | None, str]:
    matches = re.findall(r'"([^"]+)"', identifier)
    if matches:
        if len(matches) == 1:
            return None, matches[0].upper()
        return matches[0].upper(), matches[1].upper()
    parts = identifier.split(".")
    if len(parts) == 2:
        owner, table = parts
        return owner.strip('"').upper(), table.strip('"').upper()
    return None, identifier.strip('"').upper()


def fetch_table_columns(conn: db.Connection) -> Dict[str, str]:
    owner, table = parse_table_identifier(ORACLE_TABLE)
    query = (
        "SELECT column_name, data_type FROM all_tab_columns "
        "WHERE table_name = :tab"
    )
    params: Dict[str, str] = {"tab": table}
    if owner:
        query += " AND owner = :owner"
        params["owner"] = owner
    cursor = conn.cursor()
    try:
        cursor.execute(query, params)
        return {name: dtype.upper() for name, dtype in cursor}
    finally:
        cursor.close()


@dataclass
class QueryContext:
    organization: str
    project: str | None
    team_segments: Sequence[str]
    query_id: str

    def api_base(self) -> str:
        parts = [self.organization]
        if self.project:
            parts.append(self.project)
        parts.extend(self.team_segments)
        encoded = [quote(part, safe="") for part in parts if part]
        return f"https://dev.azure.com/{'/'.join(encoded)}"


def load_config(path: Path = CONFIG_FILE) -> Dict[str, str]:
    if not path.exists():
        raise FileNotFoundError(f"No se encontro el archivo de configuracion: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    required = [
        "organization",
        "query_id",
    ]
    for key in required:
        if not data.get(key):
            raise ValueError(f"La clave '{key}' es obligatoria en el archivo de configuracion")
    token = str(data.get("personal_access_token") or "").strip()
    if not token:
        for env_key in TOKEN_ENV_VARS:
            env_val = os.getenv(env_key)
            if env_val:
                token = env_val.strip()
                if token:
                    break
    if not token:
        raise ValueError(
            "Proporciona 'personal_access_token' en el archivo de configuracion o define "
            "una variable de entorno AZDO_PERSONAL_ACCESS_TOKEN"
        )
    if not GUID_RE.match(data["query_id"]):
        raise ValueError("'query_id' debe ser un GUID valido")
    data["personal_access_token"] = token
    return data


def obtener_resultados(ctx: QueryContext, token: str) -> pd.DataFrame:
    print("Descargando definicion de la consulta...")
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
        print("La consulta no devolvio work items.")
        return pd.DataFrame()

    registros = recolectar_work_items(session, ctx, ids, field_order)
    if not registros:
        print("No fue posible recuperar los detalles de los work items.")
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
    df = limpiar_dataframe(df)
    return df


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
) -> List[Dict[str, object]]:
    registros: List[Dict[str, object]] = []
    url = f"{ctx.api_base()}/_apis/wit/workitemsbatch"
    total = len(ids)
    for chunk in dividir(ids, MAX_BATCH):
        payload = {"ids": chunk, "fields": list(fields)}
        resp = session.post(url, params={"api-version": API_VERSION}, json=payload, timeout=60)
        validar_respuesta(resp, "No fue posible recuperar los work items")
        data = cargar_json(resp, "No fue posible interpretar los work items")
        valores = data.get("value", [])
        registros.extend([item for item in valores if isinstance(item, dict)])
        print(f"  Procesados {min(len(registros), total)} de {total} work items...", end="\r")
    print()
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
    raise RuntimeError(f"{mensaje_error}. Detalle: {detalle}")


def cargar_json(resp: requests.Response, contexto: str):
    try:
        return resp.json()
    except ValueError as exc:
        snippet = resp.text[:500].strip()
        status = resp.status_code
        detalle = snippet if snippet else f'HTTP {status} sin contenido'
        raise RuntimeError(f"{contexto}. Respuesta no es JSON valido. Detalle: {detalle}") from exc


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


def formatear_fechas(df: pd.DataFrame) -> None:
    patrones_fecha = re.compile(r"(date|fecha)$", re.IGNORECASE)
    patrones_datetime = re.compile(r"(datetime|timestamp|hora|time)$", re.IGNORECASE)
    iso_z_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z$")
    iso_datetime_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?$")
    iso_basic_pattern = re.compile(r"^\d{4}-\d{2}-\d{2}$")

    for columna in df.columns:
        serie = df[columna]
        if not isinstance(serie, pd.Series):
            continue

        nombre = str(columna)
        es_datetime = is_datetime64_any_dtype(serie) or isinstance(serie.dtype, DatetimeTZDtype)
        es_textual = is_object_dtype(serie) or is_string_dtype(serie) or isinstance(serie.dtype, CategoricalDtype)
        forzar_por_nombre = bool(patrones_fecha.search(nombre) or patrones_datetime.search(nombre))

        if not (es_datetime or es_textual or forzar_por_nombre):
            continue

        formato = None
        usar_utc = True
        if es_textual or forzar_por_nombre:
            valores_no_nulos = serie.dropna().astype(str)
            if not valores_no_nulos.empty:
                if valores_no_nulos.map(iso_z_pattern.match).dropna().all():
                    formato = "%Y-%m-%dT%H:%M:%S.%fZ" if valores_no_nulos.str.contains(r"\.").any() else "%Y-%m-%dT%H:%M:%SZ"
                    usar_utc = True
                elif valores_no_nulos.map(iso_datetime_pattern.match).dropna().all():
                    formato = "%Y-%m-%dT%H:%M:%S.%f" if valores_no_nulos.str.contains(r"\.").any() else "%Y-%m-%dT%H:%M:%S"
                    usar_utc = False
                elif valores_no_nulos.map(iso_basic_pattern.match).dropna().all():
                    formato = "%Y-%m-%d"
                    usar_utc = False

        try:
            if formato:
                convertido = pd.to_datetime(serie, errors="coerce", utc=usar_utc, format=formato)
            else:
                convertido = pd.to_datetime(serie, errors="coerce", utc=True)
                usar_utc = True
        except (TypeError, ValueError):
            try:
                convertido = pd.to_datetime(serie, errors="coerce")
                usar_utc = False
            except Exception:
                continue

        if convertido.notna().sum() == 0:
            continue

        if usar_utc:
            try:
                convertido = convertido.dt.tz_convert(None)
            except (AttributeError, TypeError):
                pass
        elif getattr(convertido.dtype, "tz", None) is not None:
            convertido = convertido.dt.tz_convert(None)

        mask = convertido.notna()
        if not mask.any():
            continue

        formatted = serie.astype("object")
        formatted.loc[mask] = convertido.loc[mask].dt.strftime("%Y-%m-%d")
        df[columna] = formatted


def normalizar_iso_fecha(valor: object) -> object:
    if not isinstance(valor, str):
        return valor
    dato = valor.strip()
    if not ISO_Z_REGEX.match(dato):
        return valor
    try:
        convertido = pd.to_datetime(dato, utc=True, errors="coerce")
    except Exception:
        return valor
    if pd.isna(convertido):
        return valor
    try:
        convertido = convertido.tz_convert(None)
    except (AttributeError, TypeError):
        pass
    return convertido.strftime("%Y-%m-%d")


def limpiar_texto(valor: object) -> object:
    if valor is None:
        return None
    if isinstance(valor, float) and pd.isna(valor):
        return valor
    if not isinstance(valor, str):
        return valor
    texto = html.unescape(valor)
    texto = re.sub(r"<\s*br\s*/?>", " ", texto, flags=re.IGNORECASE)
    texto = re.sub(r"<\s*/?p\s*>", " ", texto, flags=re.IGNORECASE)
    texto = re.sub(r"<\s*/?li\s*>", " ", texto, flags=re.IGNORECASE)
    texto = re.sub(r"<\s*/?div\s*>", " ", texto, flags=re.IGNORECASE)
    texto = re.sub(r"<[^>]+>", " ", texto)
    texto = texto.replace("\r", " ").replace("\n", " ")
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode("ascii")
    texto = re.sub(r"\s+", " ", texto)
    return texto.strip()


def limpiar_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    for columna in df.columns:
        df[columna] = df[columna].apply(limpiar_texto)
    formatear_fechas(df)
    for columna in df.columns:
        df[columna] = df[columna].apply(normalizar_iso_fecha)
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


def connect_oracle() -> db.Connection:
    dsn = db.makedsn(ORACLE_HOST, ORACLE_PORT, service_name=ORACLE_SERVICE)
    return db.connect(user=ORACLE_USER, password=ORACLE_PASSWORD, dsn=dsn)


def merge_dataframe_into_table(conn: db.Connection, df: pd.DataFrame) -> None:
    if df.empty:
        print("DataFrame vacio; no se enviaron cambios.")
        return

    id_col = next((col for col in df.columns if col.lower() == "id"), None)
    if id_col is None:
        raise ValueError("El DataFrame no contiene la columna 'ID'.")

    original_columns = list(df.columns)
    db_columns_all = build_db_column_names(original_columns)
    table_columns = fetch_table_columns(conn)

    column_pairs: list[tuple[str, str]] = []
    skipped_columns: list[str] = []

    for original, db_col in zip(original_columns, db_columns_all):
        if db_col in EXCLUDED_DB_COLUMNS:
            skipped_columns.append(str(original))
            continue
        if db_col in table_columns:
            column_pairs.append((original, db_col))
        else:
            skipped_columns.append(str(original))

    if skipped_columns:
        print(
            "Advertencia: se omiten columnas sin correspondencia en "
            f"{ORACLE_TABLE}: {', '.join(skipped_columns)}"
        )

    if not column_pairs:
        raise ValueError(
            f"No hay columnas en comun entre el DataFrame y {ORACLE_TABLE}"
        )

    columns = [original for original, _ in column_pairs]
    db_columns = [db_col for _, db_col in column_pairs]

    if id_col not in columns:
        raise ValueError(
            "La columna 'ID' no tiene correspondencia en la tabla destino."
        )

    df = df.loc[:, columns].copy()

    id_index = columns.index(id_col)
    id_db_col = db_columns[id_index]

    update_db_cols = [db_columns[idx] for idx in range(len(columns)) if idx != id_index]

    bind_markers = [f":b{idx}" for idx in range(len(columns))]
    quoted_cols = [f'"{col}"' for col in db_columns]
    select_clause = ", ".join(
        f'{marker} AS "{db_col}"'
        for marker, db_col in zip(bind_markers, db_columns)
    )

    sql_parts = [
        f"MERGE INTO {ORACLE_TABLE} tgt",
        "USING (",
        f"    SELECT {select_clause}",
        "    FROM dual",
        ") src",
        f'ON (tgt."{id_db_col}" = src."{id_db_col}")',
    ]

    if update_db_cols:
        set_clause = ",\n        ".join(
            f'tgt."{db_col}" = src."{db_col}"' for db_col in update_db_cols
        )
        sql_parts.append('WHEN MATCHED THEN UPDATE SET')
        sql_parts.append('        ' + set_clause)

    insert_cols = ", ".join(quoted_cols)
    values_clause = ", ".join(f'src."{db_col}"' for db_col in db_columns)
    sql_parts.append('WHEN NOT MATCHED THEN INSERT (' + insert_cols + ')')
    sql_parts.append('    VALUES (' + values_clause + ')')

    merge_sql = "\n".join(sql_parts)

    type_map = {db_col: table_columns.get(db_col, "") for db_col in db_columns}

    def normalize_cell(value: object, db_col: str) -> object:
        if value is None:
            return None
        try:
            if pd.isna(value):
                return None
        except TypeError:
            pass
        dtype = type_map.get(db_col, "")
        if dtype == "DATE":
            return to_date(value)
        if dtype.startswith("TIMESTAMP"):
            return to_datetime(value)
        if dtype == "NUMBER":
            return to_number(value)
        return value

    def to_date(value: object) -> object:
        if isinstance(value, pd.Timestamp):
            return value.to_pydatetime().date()
        if isinstance(value, datetime.datetime):
            return value.date()
        if isinstance(value, datetime.date):
            return value
        if isinstance(value, str):
            parsed = pd.to_datetime(value, errors="coerce")
            if parsed is not None and not pd.isna(parsed):
                return parsed.to_pydatetime().date()
            return None
        return value

    def to_datetime(value: object) -> object:
        if isinstance(value, pd.Timestamp):
            return value.to_pydatetime()
        if isinstance(value, datetime.datetime):
            return value
        if isinstance(value, datetime.date):
            return datetime.datetime.combine(value, datetime.time())
        if isinstance(value, str):
            parsed = pd.to_datetime(value, errors="coerce")
            if parsed is not None and not pd.isna(parsed):
                return parsed.to_pydatetime()
            return None
        return value

    def to_number(value: object) -> object:
        if isinstance(value, (int, float)):
            return value
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped:
                return None
            try:
                return float(stripped) if "." in stripped else int(stripped)
            except ValueError:
                return None
        return value

    records = [
        tuple(
            normalize_cell(cell, db_col)
            for cell, db_col in zip(row, db_columns)
        )
        for row in df.itertuples(index=False, name=None)
    ]

    cursor = conn.cursor()
    print(f"Aplicando MERGE sobre {ORACLE_TABLE} ({len(records)} filas)...")
    cursor.executemany(merge_sql, records)
    conn.commit()
    cursor.close()



def run_pipeline() -> None:
    config = load_config()
    team_text = config.get("team_path") or ""
    team_segments = [segment.strip() for segment in team_text.split("/") if segment.strip()]
    ctx = QueryContext(
        organization=config["organization"],
        project=config.get("project"),
        team_segments=team_segments,
        query_id=config["query_id"],
    )

    print("Ejecutando consulta en Azure DevOps...")
    df = obtener_resultados(ctx, config["personal_access_token"])
    print(f"Filas recibidas: {len(df)}")

    conn = connect_oracle()
    try:
        merge_dataframe_into_table(conn, df)
    finally:
        conn.close()
    print("Proceso completado.")


def main() -> None:
    try:
        run_pipeline()
    except Exception as exc:  # pragma: no cover - logging simple
        print(f"ERROR: {exc}")


if __name__ == "__main__":
    main()

