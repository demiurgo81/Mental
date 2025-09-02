# build_exe.py
# -*- coding: utf-8 -*-
"""
Builder GUI para generar ejecutables Windows (x64) desde scripts .py con:
- Detección de dependencias (AST / pyproject.toml / requirements.txt)
- Entorno de build aislado (venv con CPython disponible; no bloqueado a 3.10)
- Backend por defecto: Nuitka (--onefile --standalone); fallback: PyInstaller
- Sugerencias para imports dinámicos (hidden imports)
- Inclusión de datos (--add-data) y carpetas comunes autodetectadas
- Opción de UPX, prueba del ejecutable y exporte de metadata.json
- GUI Tkinter sin modo CLI

Compatibilidad:
- Windows 10/11 x64
- Cualquier **CPython** 3.8+ instalado (se elige el más alto disponible con 'py -0p' o el intérprete activo)
"""
from __future__ import annotations

import ast
import hashlib
import io
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import Iterable, List, Optional, Set, Tuple

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

WIN = os.name == "nt"
MIN_PY = (3, 8)
DEFAULT_BACKEND = "nuitka"
STD_DIR_FALLBACK_38: Set[str] = {
    "abc","argparse","asyncio","base64","binascii","bisect","builtins","calendar","collections",
    "concurrent","contextlib","copy","csv","ctypes","dataclasses","datetime","decimal",
    "difflib","email","enum","ftplib","functools","gc","getopt","getpass","gettext","glob","gzip",
    "hashlib","heapq","hmac","html","http","imaplib","importlib","inspect","io","ipaddress","itertools",
    "json","logging","math","mimetypes","msilib","multiprocessing","ntpath","numbers","operator",
    "os","pathlib","pickle","pkgutil","platform","plistlib","queue","random","re","sched","secrets",
    "select","shlex","shelve","signal","site","smtplib","socket","sqlite3","ssl","statistics","string",
    "struct","subprocess","sys","tarfile","tempfile","textwrap","threading","time","tkinter","tokenize",
    "traceback","types","typing","unicodedata","urllib","uuid","venv","warnings","weakref","xml","zipfile","zoneinfo"
}
DATA_DIR_CANDIDATES = ["assets", "data", "resources", "static", "templates"]
C_EXT_PACKS = {"numpy", "pandas", "scipy", "matplotlib", "skimage", "numba"}

@dataclass
class BuildOptions:
    windowed: bool = True
    suggest_hidden: bool = True
    detailed_log: bool = False
    run_selftest: bool = True
    use_upx: bool = False
    icon_path: Optional[str] = None
    hidden_imports: List[str] = None
    add_data_pairs: List[Tuple[str, str]] = None
    include_dirs: List[str] = None
    backend: str = DEFAULT_BACKEND

@dataclass
class BuildContext:
    project_dir: Path
    script_path: Path
    build_dir: Path
    venv_dir: Path
    wheels_dir: Path
    pip_cache_dir: Path
    dist_dir: Path
    log_file: Path
    metadata_file: Path
    requirements_lock: Path
    selected_python: Optional[str] = None
    venv_python: Optional[str] = None
    used_backend: Optional[str] = None
    upx_path: Optional[str] = None
    env: dict = None
    selected_py_version: str = ""

class GuiLogger:
    def __init__(self, text_widget: tk.Text, verbose=False):
        self.text = text_widget
        self.lock = threading.Lock()
        self.verbose = verbose

    def log(self, msg: str, level: str = "INFO"):
        ts = time.strftime("%Y-%m-%d %H:%M:%S")
        line = f"{ts} [{level}] {msg}\n"
        with self.lock:
            self.text.insert("end", line)
            self.text.see("end")
        if self.verbose:
            try:
                sys.stdout.write(line)
            except Exception:
                pass

def _stdlib_names() -> Set[str]:
    try:
        return set(sys.stdlib_module_names)  # py>=3.10
    except Exception:
        return STD_DIR_FALLBACK_38

def is_stdlib(name: str) -> bool:
    root = (name.split(".")[0]).strip()
    return root in _stdlib_names()

def analyze_imports(script: Path) -> Set[str]:
    src = script.read_text(encoding="utf-8", errors="ignore")
    tree = ast.parse(src, filename=str(script))
    pkgs: Set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name:
                    pkgs.add(alias.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module and node.level == 0:
                pkgs.add(node.module.split(".")[0])
    return {p for p in pkgs if not is_stdlib(p)}

DYN_PATTERNS = [
    r"importlib\.import_module\(\s*['\"]([a-zA-Z0-9_\.]+)['\"]\s*\)",
    r"__import__\(\s*['\"]([a-zA-Z0-9_\.]+)['\"]\s*\)",
    r"pkg_resources\.(?:iter_entry_points|require)\(\s*['\"]([a-zA-Z0-9_\-\.]+)['\"]",
]

def detect_dynamic_imports(script: Path) -> Set[str]:
    txt = script.read_text(encoding="utf-8", errors="ignore")
    found: Set[str] = set()
    for pat in DYN_PATTERNS:
        for m in re.finditer(pat, txt):
            mod = m.group(1)
            if mod:
                found.add(mod.split(".")[0])
    return {m for m in found if not is_stdlib(m)}

def _normalize_req_line(s: str) -> str:
    s = s.strip()
    s = s.split(";")[0].strip()
    s = re.sub(r"\s+", "", s)
    return s

def _parse_pyproject_toml(pyproject: Path) -> List[str]:
    try:
        try:
            import tomllib as toml
        except Exception:
            toml = None
        if toml:
            data = toml.loads(pyproject.read_text(encoding="utf-8", errors="ignore"))
            deps = []
            proj = data.get("project", {})
            if isinstance(proj.get("dependencies"), list):
                deps += list(proj["dependencies"])
            poetry = data.get("tool", {}).get("poetry", {})
            depmap = poetry.get("dependencies", {})
            for k, v in depmap.items():
                if k.lower() == "python":
                    continue
                if isinstance(v, str):
                    deps.append(f"{k}{v if v.strip().startswith(('>','<','=','!','~','^')) else f'=={v}'}")
                elif isinstance(v, dict):
                    ver = v.get("version")
                    if ver:
                        deps.append(f"{k}{ver if ver.strip().startswith(('>','<','=','!','~','^')) else f'=={ver}'}")
                    else:
                        deps.append(k)
                else:
                    deps.append(k)
            return sorted(set(_normalize_req_line(d) for d in deps if d))
    except Exception:
        pass
    txt = pyproject.read_text(encoding="utf-8", errors="ignore")
    deps: List[str] = []
    m = re.search(r"\[project\][\s\S]*?dependencies\s*=\s*\[(.*?)\]", txt, re.DOTALL)
    if m:
        arr = m.group(1)
        for s in re.findall(r"['\"]([^'\"]+)['\"]", arr):
            deps.append(_normalize_req_line(s))
    section = re.search(r"\[tool\.poetry\.dependencies\](.*?)(?:\n\[|$)", txt, re.DOTALL)
    if section:
        for line in section.group(1).splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = [x.strip() for x in line.split("=", 1)]
            key = key.strip('"\'')
            if key.lower() == "python":
                continue
            val = val.strip('"\'')
            if val:
                deps.append(_normalize_req_line(f"{key}{val if val[0] in '<>!=~^' else '=='+val}"))
            else:
                deps.append(key)
    return sorted(set(d for d in deps if d))

def _read_requirements_txt(req: Path) -> List[str]:
    lines = []
    for line in req.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("-"):
            continue
        lines.append(_normalize_req_line(line))
    return lines

def resolve_dependencies(script: Path, logger) -> List[str]:
    proj_dir = script.parent
    pyproject = proj_dir / "pyproject.toml"
    requirements = proj_dir / "requirements.txt"
    if pyproject.exists():
        logger.log("Usando pyproject.toml como fuente de verdad de dependencias.")
        return _parse_pyproject_toml(pyproject)
    if requirements.exists():
        logger.log("Usando requirements.txt como fuente de verdad de dependencias.")
        return _read_requirements_txt(requirements)
    logger.log("No se encontró pyproject.toml ni requirements.txt: detectando imports por AST.")
    imports = analyze_imports(script)
    logger.log(f"Imports detectados (no stdlib): {', '.join(sorted(imports)) or '(ninguno)'}")
    return sorted(imports)

def run_cmd(cmd: List[str], env: Optional[dict] = None, cwd: Optional[str] = None) -> Tuple[int, str, str]:
    p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, cwd=cwd, text=True)
    out_lines = []
    while True:
        line = p.stdout.readline()
        if not line and p.poll() is not None:
            break
        if line:
            out_lines.append(line)
    rc = p.returncode
    out = "".join(out_lines)
    return rc, out, out

def detect_msvc() -> bool:
    if shutil.which("cl.exe"):
        return True
    vsw = r"C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe"
    if Path(vsw).exists():
        rc, out, _ = run_cmd([vsw, "-latest", "-requires", "Microsoft.VisualStudio.Component.VC.Tools.x86.x64", "-property", "installationPath"])
        if rc == 0 and out.strip():
            return True
    for k in ("VSINSTALLDIR", "VCToolsInstallDir", "VCINSTALLDIR"):
        if os.environ.get(k):
            return True
    return False

def detect_upx() -> Optional[str]:
    return shutil.which("upx")

def _list_py_launcher_interpreters() -> List[str]:
    """Devuelve rutas de 'py -0p' si está disponible (Windows)."""
    if not WIN:
        return []
    py = shutil.which("py")
    if not py:
        return []
    rc, out, _ = run_cmd([py, "-0p"])
    if rc != 0:
        return []
    paths = []
    for line in out.splitlines():
        line = line.strip()
        if not line:
            continue
        if line.startswith("-"):
            parts = line.split()
            p = parts[-1]
            if p.lower().endswith("python.exe"):
                paths.append(p)
    return paths

def _is_cpython(path: str) -> bool:
    lower = path.lower()
    return "pypy" not in lower and "jython" not in lower

def _version_of_python(path: str) -> tuple:
    rc, out, _ = run_cmd([path, "-c", "import sys;print('.'.join(map(str, sys.version_info[:3])))"])
    if rc == 0:
        try:
            parts = tuple(int(x) for x in out.strip().split("."))
            return parts
        except Exception:
            return (0,0,0)
    return (0,0,0)

def ensure_python_and_venv(ctx: BuildContext, logger) -> None:
    """
    Selecciona el mejor **CPython 3.8+** disponible para construir y crea un venv en .build/venv.
    Orden de preferencia:
      1) Mayor versión de 'py -0p' (si existe), CPython y >=3.8
      2) Intérprete actual (sys.executable) si es CPython >=3.8
    """
    candidates = []
    for p in _list_py_launcher_interpreters():
        if Path(p).exists() and _is_cpython(p):
            ver = _version_of_python(p)
            if ver >= MIN_PY:
                candidates.append((ver, p))
    if _is_cpython(sys.executable):
        ver = _version_of_python(sys.executable)
        if ver >= MIN_PY:
            candidates.append((ver, sys.executable))

    if not candidates:
        raise RuntimeError(
            "No se encontró un CPython 3.8+ instalado.\n"
            "Instala cualquier Python 3.8 o superior desde https://www.python.org/downloads/windows/"
        )

    candidates.sort(reverse=True)
    ver, chosen = candidates[0]
    ctx.selected_python = chosen
    ctx.selected_py_version = ".".join(map(str, ver))
    logger.log(f"Python seleccionado: {chosen} (v{ctx.selected_py_version})")

    if not ctx.venv_dir.exists():
        logger.log("Creando entorno virtual (venv)…")
        rc, out, _ = run_cmd([chosen, "-m", "venv", str(ctx.venv_dir)])
        if rc != 0:
            raise RuntimeError(f"Fallo creando venv:\n{out}")
    vpy = ctx.venv_dir / ("Scripts/python.exe" if WIN else "bin/python")
    if not vpy.exists():
        raise RuntimeError("No se encontró intérprete del venv.")
    ctx.venv_python = str(vpy)

    logger.log("Actualizando pip/setuptools/wheel en el venv…")
    env = os.environ.copy()
    env["PIP_CACHE_DIR"] = str(ctx.pip_cache_dir)
    ctx.env = env
    run_cmd([ctx.venv_python, "-m", "pip", "install", "--upgrade", "pip", "wheel", "setuptools"], env=env)

def pip_install(ctx: BuildContext, reqs: List[str], logger) -> None:
    env = ctx.env
    if reqs:
        logger.log(f"Instalando dependencias: {', '.join(reqs)}")
        rc, out, _ = run_cmd([ctx.venv_python, "-m", "pip", "install", "--no-input", "--cache-dir", str(ctx.pip_cache_dir), *reqs], env=env)
        if rc != 0:
            logger.log(out)
            raise RuntimeError("Fallo instalando dependencias. Revisa el log.")
    else:
        logger.log("No hay dependencias a instalar (además de backends).")

    run_cmd([ctx.venv_python, "-m", "pip", "install", "--no-input", "--cache-dir", str(ctx.pip_cache_dir), "nuitka>=2.0"], env=env)
    run_cmd([ctx.venv_python, "-m", "pip", "install", "--no-input", "--cache-dir", str(ctx.pip_cache_dir), "pyinstaller>=6.0"], env=env)

def log_env_info(ctx: BuildContext, logger):
    logger.log(f"Windows: {platform.platform()}")
    logger.log(f"Arquitectura: {platform.machine()} / {platform.architecture()[0]}")
    rc, out, _ = run_cmd([ctx.venv_python, "-m", "pip", "--version"], env=ctx.env)
    logger.log(out.strip())
    rc, out, _ = run_cmd([ctx.venv_python, "-m", "nuitka", "--version"], env=ctx.env)
    logger.log(f"Nuitka: {out.strip() or 'no reporta versión'}")
    rc, out, _ = run_cmd([ctx.venv_python, "-m", "PyInstaller", "--version"], env=ctx.env)
    logger.log(f"PyInstaller: {out.strip() or 'no reporta versión'}")

def normalize_add_data_args(pairs: List[Tuple[str, str]], backend: str) -> List[str]:
    out = []
    for src, dst in pairs:
        if backend == "pyinstaller":
            out.append(f"{src};{dst}")
        else:
            out.append(f"{src}={dst}")
    return out

def gather_data_paths(script_path: Path, selected_dirs: Iterable[str]) -> List[Tuple[str, str]]:
    base = script_path.parent
    pairs: List[Tuple[str, str]] = []
    for d in selected_dirs:
        src = base / d
        if src.exists():
            pairs.append((str(src), d))
    return pairs

def write_requirements_lock(ctx: BuildContext, logger):
    rc, out, _ = run_cmd([ctx.venv_python, "-m", "pip", "freeze"], env=ctx.env)
    ctx.requirements_lock.write_text(out, encoding="utf-8")
    logger.log(f"requirements.lock generado en {ctx.requirements_lock}")

def maybe_use_upx(ctx: BuildContext, exe_path: Path, logger):
    upx = ctx.upx_path or detect_upx()
    if not upx:
        logger.log("UPX no detectado en PATH.", "WARN")
        return
    logger.log("Comprimiendo ejecutable con UPX (puede causar falsos positivos de antivirus).")
    rc, out, _ = run_cmd([upx, "--best", "--lzma", str(exe_path)])
    if rc != 0:
        logger.log(f"UPX fallo:\n{out}", "WARN")
    else:
        logger.log("UPX aplicado correctamente.")

def warn_long_paths(path: Path, logger):
    if len(str(path)) > 180:
        logger.log("Advertencia: la ruta es muy larga (>180). Sugiero mover el proyecto a una ruta más corta.", "WARN")

def export_build_metadata(ctx: BuildContext, options: BuildOptions, exe_path: Path, deps: List[str], logger):
    meta = {
        "backend": ctx.used_backend,
        "flags": {
            "windowed": options.windowed,
            "use_upx": options.use_upx,
            "hidden_imports": options.hidden_imports or [],
            "add_data": options.add_data_pairs or [],
            "include_dirs": options.include_dirs or [],
            "icon": options.icon_path or ""
        },
        "script_hash_sha256": hashlib.sha256(ctx.script_path.read_bytes()).hexdigest(),
        "python": ctx.selected_py_version,
        "os": platform.platform(),
        "arch": platform.machine(),
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "deps_requested": deps,
        "requirements_lock_file": str(ctx.requirements_lock),
        "exe": {
            "path": str(exe_path),
            "size_bytes": exe_path.stat().st_size if exe_path.exists() else None
        }
    }
    ctx.metadata_file.write_text(json.dumps(meta, indent=2), encoding="utf-8")
    logger.log(f"Metadata exportada: {ctx.metadata_file}")

def _nuitka_cmd(ctx: BuildContext, options: BuildOptions, add_data_norm: List[str]) -> List[str]:
    cmd = [ctx.venv_python, "-m", "nuitka", "--onefile", "--standalone", "--assume-yes-for-downloads"]
    if options.windowed:
        cmd += ["--windows-disable-console"]
    cmd += ["--enable-plugin=tk-inter"]
    if options.icon_path:
        cmd += ["--windows-icon-from-ico", options.icon_path]
    for spec in add_data_norm:
        src, dst = spec.split("=", 1)
        if Path(src).is_dir():
            cmd += ["--include-data-dir", spec]
        else:
            cmd += ["--include-data-files", spec]
    for h in options.hidden_imports or []:
        cmd += ["--include-module", h]
    for heavy in C_EXT_PACKS:
        if heavy in (options.hidden_imports or []):
            if heavy == "numpy":
                cmd += ["--enable-plugin=numpy"]
            if heavy == "pandas":
                cmd += ["--enable-plugin=pandas"]
            if heavy == "matplotlib":
                cmd += ["--enable-plugin=matplotlib"]
    cmd += [str(ctx.script_path)]
    return cmd

def build_with_nuitka(ctx: BuildContext, options: BuildOptions, logger, add_data_norm: List[str]) -> Path:
    if not detect_msvc():
        ok = messagebox.askyesno(
            "MSVC no detectado",
            "No se detectó MSVC Build Tools (requerido por Nuitka).\n"
            "¿Deseas cambiar a PyInstaller (fallback) para este build?\n\n"
            "Puedes instalar MSVC en paralelo desde:\n"
            "https://visualstudio.microsoft.com/visual-cpp-build-tools/"
        )
        if ok:
            ctx.used_backend = "pyinstaller"
            return build_with_pyinstaller(ctx, options, logger, normalize_add_data_args(options.add_data_pairs or [], "pyinstaller"))
        else:
            raise RuntimeError("Nuitka requiere MSVC. Instálalo o acepta fallback a PyInstaller.")

    ctx.used_backend = "nuitka"
    cmd = _nuitka_cmd(ctx, options, add_data_norm)
    logger.log("Ejecutando Nuitka…")
    logger.log(" ".join(cmd))
    rc, out, _ = run_cmd(cmd, env=ctx.env, cwd=str(ctx.project_dir))
    logger.log(out)
    if rc != 0:
        raise RuntimeError("Nuitka terminó con error.")
    exe_name = ctx.script_path.with_suffix(".exe").name
    produced = ctx.project_dir / exe_name
    if not produced.exists():
        found = list(ctx.project_dir.glob("*.exe"))
        if found:
            produced = max(found, key=lambda p: p.stat().st_mtime)
    if not produced.exists():
        raise RuntimeError("No se encontró el ejecutable producido por Nuitka.")
    return produced

def build_with_pyinstaller(ctx: BuildContext, options: BuildOptions, logger, add_data_norm: List[str]) -> Path:
    ctx.used_backend = "pyinstaller"
    cmd = [ctx.venv_python, "-m", "PyInstaller", "--onefile", "--noconfirm", "--clean"]
    if options.windowed:
        cmd += ["--windowed"]
    if options.icon_path:
        cmd += ["--icon", options.icon_path]
    for spec in add_data_norm:
        cmd += ["--add-data", spec.replace("=", ";")]
    for h in options.hidden_imports or []:
        cmd += ["--hidden-import", h]
    logger.log("Ejecutando PyInstaller…")
    logger.log(" ".join(cmd))
    rc, out, _ = run_cmd(cmd, env=ctx.env, cwd=str(ctx.project_dir))
    logger.log(out)
    if rc != 0:
        raise RuntimeError("PyInstaller terminó con error.")
    exe_name = ctx.script_path.stem + (".exe" if WIN else "")
    produced = ctx.project_dir / "dist" / exe_name
    if not produced.exists():
        candidates = list((ctx.project_dir / "dist").glob("*.exe"))
        if candidates:
            produced = max(candidates, key=lambda p: p.stat().st_mtime)
    if not produced.exists():
        raise RuntimeError("No se encontró el ejecutable producido por PyInstaller.")
    return produced

def run_self_test(exe_path: Path, logger):
    logger.log("Ejecutando self-test del ejecutable…")
    try:
        rc, out, _ = run_cmd([str(exe_path), "--self-test"])
        if rc == 0:
            logger.log("Self-test (--self-test) OK.")
            logger.log(out.strip())
            return
    except Exception:
        pass
    rc, out, _ = run_cmd([str(exe_path)])
    logger.log(out.strip() if out else "(sin salida)")
    logger.log(f"Proceso terminó con código {rc}.")

class App:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Python → EXE (Nuitka/PyInstaller) — Windows x64")
        self.root.geometry("1024x720")

        self.script_var = tk.StringVar()
        self.icon_var = tk.StringVar()
        self.hidden_imports_text = tk.Text(self.root, height=4)
        self.add_data_text = tk.Text(self.root, height=4)
        self.upx_var = tk.BooleanVar(value=False)
        self.windowed_var = tk.BooleanVar(value=True)
        self.suggest_var = tk.BooleanVar(value=True)
        self.detailed_var = tk.BooleanVar(value=False)
        self.selftest_var = tk.BooleanVar(value=True)

        self.dir_vars = {d: tk.BooleanVar(value=False) for d in DATA_DIR_CANDIDATES}

        self.logger = None
        self._build_ui()

    def _build_ui(self):
        pad = dict(padx=8, pady=6)

        frm_top = ttk.LabelFrame(self.root, text="Script origen (.py)")
        frm_top.pack(fill="x", **pad)
        ttk.Entry(frm_top, textvariable=self.script_var).pack(side="left", fill="x", expand=True, padx=6, pady=6)
        ttk.Button(frm_top, text="Seleccionar .py", command=self._select_script).pack(side="right", padx=6, pady=6)

        frm_opts = ttk.LabelFrame(self.root, text="Opciones")
        frm_opts.pack(fill="x", **pad)

        left = ttk.Frame(frm_opts)
        left.pack(side="left", fill="x", expand=True, padx=6, pady=6)
        ttk.Checkbutton(left, text="Sin consola (windowed)", variable=self.windowed_var).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(left, text="Sugerir hidden imports", variable=self.suggest_var).grid(row=1, column=0, sticky="w")
        ttk.Checkbutton(left, text="Generar log detallado", variable=self.detailed_var).grid(row=2, column=0, sticky="w")
        ttk.Checkbutton(left, text="Probar ejecutable al finalizar (self-test)", variable=self.selftest_var).grid(row=3, column=0, sticky="w")
        ttk.Checkbutton(left, text="Usar UPX si está disponible", variable=self.upx_var).grid(row=4, column=0, sticky="w")

        right = ttk.Frame(frm_opts)
        right.pack(side="left", fill="x", expand=True, padx=6, pady=6)
        ttk.Label(right, text="Icono (.ico) opcional:").grid(row=0, column=0, sticky="w")
        ttk.Entry(right, textvariable=self.icon_var, width=50).grid(row=0, column=1, sticky="we", padx=(6,0))
        ttk.Button(right, text="Elegir", command=self._select_icon).grid(row=0, column=2, padx=6)

        frm_data = ttk.LabelFrame(self.root, text="Datos y recursos")
        frm_data.pack(fill="x", **pad)
        c = 0
        for d in DATA_DIR_CANDIDATES:
            ttk.Checkbutton(frm_data, text=f"Incluir '{d}' si existe", variable=self.dir_vars[d]).grid(row=0, column=c, sticky="w")
            c += 1

        frm_hi = ttk.LabelFrame(self.root, text="--hidden-import (uno por línea)")
        frm_hi.pack(fill="x", **pad)
        self.hidden_imports_text.pack(in_=frm_hi, fill="x", padx=6, pady=6)

        frm_ad = ttk.LabelFrame(self.root, text="--add-data (formato: origen -> destino_relativo) — uno por línea")
        frm_ad.pack(fill="x", **pad)
        self.add_data_text.pack(in_=frm_ad, fill="x", padx=6, pady=6)

        frm_btns = ttk.Frame(self.root)
        frm_btns.pack(fill="x", **pad)
        ttk.Button(frm_btns, text="Analizar dependencias", command=self._analyze).pack(side="left")
        ttk.Button(frm_btns, text="Construir EXE", command=self._build).pack(side="left", padx=8)
        ttk.Button(frm_btns, text="Abrir carpeta de salida", command=self._open_dist).pack(side="left")

        frm_log = ttk.LabelFrame(self.root, text="Log de build")
        frm_log.pack(fill="both", expand=True, **pad)
        self.txt_log = tk.Text(frm_log, wrap="word")
        self.txt_log.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(frm_log, orient="vertical", command=self.txt_log.yview)
        self.txt_log.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")

        self.logger = GuiLogger(self.txt_log, verbose=False)

    def _select_script(self):
        path = filedialog.askopenfilename(title="Seleccionar script .py", filetypes=[("Python", "*.py")])
        if path:
            self.script_var.set(path)
            base = Path(path).parent
            for d, var in self.dir_vars.items():
                var.set((base / d).exists())

    def _select_icon(self):
        ico = filedialog.askopenfilename(title="Seleccionar icono .ico", filetypes=[("Icono", "*.ico")])
        if ico:
            self.icon_var.set(ico)

    def _parse_hidden_imports(self) -> List[str]:
        lines = [ln.strip() for ln in self.hidden_imports_text.get("1.0", "end").splitlines()]
        return [ln for ln in lines if ln]

    def _parse_add_data(self) -> List[Tuple[str, str]]:
        pairs: List[Tuple[str, str]] = []
        for ln in self.add_data_text.get("1.0", "end").splitlines():
            if "->" in ln:
                src, dst = [x.strip().strip('"').strip("'") for x in ln.split("->", 1)]
                if src and dst:
                    pairs.append((src, dst))
        return pairs

    def _analyze(self):
        script = Path(self.script_var.get())
        if not script.exists():
            messagebox.showwarning("Archivo", "Selecciona primero un .py válido.")
            return
        try:
            deps = resolve_dependencies(script, self.logger)
            dyn = detect_dynamic_imports(script)
            if self.suggest_var.get() and dyn:
                existing = set(self._parse_hidden_imports())
                new = sorted(existing.union(dyn))
                self.hidden_imports_text.delete("1.0", "end")
                self.hidden_imports_text.insert("1.0", "\n".join(new))
                self.logger.log(f"Sugerencias de hidden-import: {', '.join(sorted(dyn))}")
            else:
                self.logger.log("No se detectaron imports dinámicos relevantes." if not dyn else "Sugerencias desactivadas.")
            if deps:
                self.logger.log(f"Dependencias estimadas: {', '.join(deps)}")
            else:
                self.logger.log("No se encontraron dependencias externas (solo stdlib).")
        except Exception as e:
            messagebox.showerror("Análisis", str(e))

    def _open_dist(self):
        script = Path(self.script_var.get())
        if not script.exists():
            return
        dist_dir = script.parent / "dist"
        dist_dir.mkdir(exist_ok=True)
        try:
            os.startfile(str(dist_dir))
        except Exception:
            pass

    def _build(self):
        script = Path(self.script_var.get())
        if not script.exists():
            messagebox.showwarning("Archivo", "Selecciona primero un .py válido.")
            return

        options = BuildOptions(
            windowed=self.windowed_var.get(),
            suggest_hidden=self.suggest_var.get(),
            detailed_log=self.detailed_var.get(),
            run_selftest=self.selftest_var.get(),
            use_upx=self.upx_var.get(),
            icon_path=self.icon_var.get() or None,
            hidden_imports=self._parse_hidden_imports(),
            add_data_pairs=self._parse_add_data(),
            include_dirs=[d for d, var in self.dir_vars.items() if var.get()],
            backend=DEFAULT_BACKEND
        )

        t = threading.Thread(target=self._build_worker, args=(script, options), daemon=True)
        t.start()

    def _build_worker(self, script: Path, options: BuildOptions):
        try:
            start = time.time()
            proj_dir = script.parent
            build_dir = proj_dir / ".build"
            venv_dir = build_dir / "venv"
            wheels_dir = build_dir / "wheels"
            pip_cache_dir = build_dir / "pip-cache"
            dist_dir = proj_dir / "dist"
            build_dir.mkdir(exist_ok=True)
            wheels_dir.mkdir(exist_ok=True, parents=True)
            pip_cache_dir.mkdir(exist_ok=True, parents=True)
            dist_dir.mkdir(exist_ok=True)

            ctx = BuildContext(
                project_dir=proj_dir,
                script_path=script,
                build_dir=build_dir,
                venv_dir=venv_dir,
                wheels_dir=wheels_dir,
                pip_cache_dir=pip_cache_dir,
                dist_dir=dist_dir,
                log_file=(build_dir / "build.log"),
                metadata_file=(build_dir / "metadata.json"),
                requirements_lock=(build_dir / "requirements.lock"),
            )

            self.logger.log("==== INICIO BUILD ====")
            warn_long_paths(script, self.logger)
            ensure_python_and_venv(ctx, self.logger)
            log_env_info(ctx, self.logger)
            deps = resolve_dependencies(script, self.logger)
            pip_install(ctx, deps, self.logger)
            write_requirements_lock(ctx, self.logger)

            auto_pairs = gather_data_paths(script, options.include_dirs)
            all_pairs = list(auto_pairs) + list(options.add_data_pairs or [])
            add_data_nk = normalize_add_data_args(all_pairs, "nuitka")

            try:
                produced = build_with_nuitka(ctx, options, self.logger, add_data_nk)
            except Exception as e:
                self.logger.log(f"Fallo en Nuitka: {e}", "WARN")
                ok = messagebox.askyesno("Fallback a PyInstaller", "¿Intentar con PyInstaller?")
                if not ok:
                    raise
                add_data_pi = normalize_add_data_args(all_pairs, "pyinstaller")
                produced = build_with_pyinstaller(ctx, options, self.logger, add_data_pi)

            final_exe = dist_dir / produced.name
            if produced != final_exe:
                shutil.copy2(str(produced), str(final_exe))
            self.logger.log(f"Ejecutable copiado a: {final_exe}")

            if options.use_upx:
                self.logger.log("Aviso: UPX puede disparar falsos positivos de antivirus.", "WARN")
                maybe_use_upx(ctx, final_exe, self.logger)

            export_build_metadata(ctx, options, final_exe, deps, self.logger)

            if options.run_selftest:
                run_self_test(final_exe, self.logger)

            dur = time.time() - start
            self.logger.log(f"==== BUILD COMPLETADO en {dur:0.1f}s ====")
            try:
                os.startfile(str(dist_dir))
            except Exception:
                pass

        except Exception as e:
            self.logger.log(f"ERROR: {e}", "ERROR")
            messagebox.showerror("Build fallido", str(e))

def main():
    root = tk.Tk()
    app = App(root)
    root.mainloop()

if __name__ == "__main__":
    main()
