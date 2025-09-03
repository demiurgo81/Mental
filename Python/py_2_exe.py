# py_2_exe.py
# -*- coding: utf-8 -*-
"""

Indispensable ejecutarlo en una ruta corta junto con runbuilder.bat (evita problemas de rutas largas).
v7 — Progreso visible y control de ejecución:
- Barra de progreso (determinada por etapas) + estado en vivo.
- Animación de actividad (heartbeat) para que se vea que "sigue trabajando".
- Botón **Detener** (solicitud de cancelación best-effort).
- Mantiene robustez v6 para venv (reintentos / virtualenv / sin venv).
"""
from __future__ import annotations

import ast
import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, List, Optional, Set, Tuple

import tkinter as tk
from tkinter import ttk, filedialog, messagebox

WIN = os.name == "nt"
MIN_PY = (3, 8)
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
    work_folder: Optional[str] = None

@dataclass
class BuildContext:
    project_dir: Path
    script_path: Path
    work_root: Path
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
    env: dict = None
    selected_py_version: str = ""
    no_venv_mode: bool = False

class GuiLogger:
    def __init__(self, text_widget: tk.Text, verbose=False):
        self.text = text_widget
        self.lock = threading.Lock()
        self.verbose = verbose
    def log(self, msg: str, level: str = "INFO"):
        line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} [{level}] {msg}\n"
        with self.lock:
            self.text.insert("end", line); self.text.see("end")
        if self.verbose:
            try: sys.stdout.write(line)
            except Exception: pass

def _stdlib_names() -> Set[str]:
    try: return set(sys.stdlib_module_names)
    except Exception: return STD_DIR_FALLBACK_38

def is_stdlib(name: str) -> bool:
    return (name.split(".")[0]).strip() in _stdlib_names()

def analyze_imports(script: Path) -> Set[str]:
    tree = ast.parse(script.read_text(encoding="utf-8", errors="ignore"), filename=str(script))
    pkgs: Set[str] = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            for a in n.names:
                if a.name: pkgs.add(a.name.split(".")[0])
        elif isinstance(n, ast.ImportFrom):
            if n.module and n.level == 0: pkgs.add(n.module.split(".")[0])
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
            if mod: found.add(mod.split(".")[0])
    return {m for m in found if not is_stdlib(m)}

def _normalize_req_line(s: str) -> str:
    s = s.strip().split(";", 1)[0].strip()
    return re.sub(r"\s+", "", s)

def _parse_pyproject_toml(pyproject: Path) -> List[str]:
    try:
        try: import tomllib as toml
        except Exception: toml = None
        if toml:
            data = toml.loads(pyproject.read_text(encoding="utf-8", errors="ignore"))
            deps = []
            proj = data.get("project", {})
            if isinstance(proj.get("dependencies"), list):
                deps += list(proj["dependencies"])
            poetry = data.get("tool", {}).get("poetry", {})
            depmap = poetry.get("dependencies", {})
            for k,v in depmap.items():
                if k.lower()=="python": continue
                if isinstance(v,str):
                    deps.append(f"{k}{v if v.strip().startswith(('>','<','=','!','~','^')) else f'=={v}'}")
                elif isinstance(v,dict):
                    ver=v.get("version")
                    deps.append(f"{k}{ver if (ver and ver.strip().startswith(('>','<','=','!','~','^'))) else (('=='+ver) if ver else '')}".rstrip("="))
                else:
                    deps.append(k)
            return sorted(set(_normalize_req_line(d) for d in deps if d))
    except Exception:
        pass
    txt = pyproject.read_text(encoding="utf-8", errors="ignore")
    deps: List[str] = []
    m = re.search(r"\[project\][\s\S]*?dependencies\s*=\s*\[(.*?)\]", txt, re.DOTALL)
    if m:
        for s in re.findall(r"['\"]([^'\"]+)['\"]", m.group(1)):
            deps.append(_normalize_req_line(s))
    section = re.search(r"\[tool\.poetry\.dependencies\](.*?)(?:\n\[|$)", txt, re.DOTALL)
    if section:
        for line in section.group(1).splitlines():
            line=line.strip()
            if not line or line.startswith("#") or "=" not in line: continue
            k,v=[x.strip() for x in line.split("=",1)]
            k=k.strip('"\'')
            if k.lower()=="python": continue
            v=v.strip('"\'')
            deps.append(_normalize_req_line(f"{k}{v if v and v[0] in '<>!=~^' else ('=='+v if v else '')}".rstrip("=")))
    return sorted(set(d for d in deps if d))

def _read_requirements_txt(req: Path) -> List[str]:
    res=[]
    for line in req.read_text(encoding="utf-8", errors="ignore").splitlines():
        line=line.strip()
        if not line or line.startswith("#") or line.startswith("-"): continue
        res.append(_normalize_req_line(line))
    return res

def resolve_dependencies(script: Path, logger) -> List[str]:
    proj=script.parent; pyproject=proj/"pyproject.toml"; rq=proj/"requirements.txt"
    if pyproject.exists():
        logger.log("Usando pyproject.toml como fuente de verdad de dependencias."); return _parse_pyproject_toml(pyproject)
    if rq.exists():
        logger.log("Usando requirements.txt como fuente de verdad de dependencias."); return _read_requirements_txt(rq)
    logger.log("No se encontró pyproject.toml ni requirements.txt: detectando imports por AST.")
    imports=analyze_imports(script); logger.log(f"Imports detectados (no stdlib): {', '.join(sorted(imports)) or '(ninguno)'}")
    return sorted(imports)

def run_cmd(cmd: List[str], env=None, cwd=None, cancel_event: Optional[threading.Event]=None, logger: Optional[GuiLogger]=None, label: str="cmd"):
    p=subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, env=env, cwd=cwd, text=True)
    out=[]
    while True:
        if cancel_event is not None and cancel_event.is_set():
            try:
                if WIN:
                    subprocess.run(["taskkill","/F","/T","/PID",str(p.pid)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    p.terminate()
            except Exception:
                pass
            return 1, ''.join(out)+"\n[CANCELADO]\n", ''.join(out)
        line=p.stdout.readline()
        if not line and p.poll() is not None: break
        if line:
            out.append(line)
            if logger: logger.log(line.rstrip())
    return p.returncode, ''.join(out), ''.join(out)

def _list_py_launcher_interpreters() -> List[str]:
    if not WIN: return []
    py=shutil.which("py")
    if not py: return []
    rc,out,_=run_cmd([py,"-0p"])
    if rc!=0: return []
    paths=[]
    for ln in out.splitlines():
        ln=ln.strip()
        if ln.startswith("-"):
            p=ln.split()[-1]
            if p.lower().endswith("python.exe"): paths.append(p)
    return paths

def _is_cpython(path:str)->bool:
    low=path.lower(); return "pypy" not in low and "jython" not in low

def _version_of_python(path:str)->tuple:
    rc,out,_=run_cmd([path,"-c","import sys;print('.'.join(map(str,sys.version_info[:3])))"])
    if rc==0:
        try: return tuple(int(x) for x in out.strip().split("."))
        except Exception: return (0,0,0)
    return (0,0,0)

def default_workdir(script: Path) -> Path:
    base = os.environ.get("LOCALAPPDATA") or str(Path.home() / "AppData" / "Local")
    root = Path(base) / "py2exe_builds" / f"{script.stem}_build"
    return root

def _venv_python_path(venv_dir: Path) -> Path:
    return venv_dir / ("Scripts/python.exe" if WIN else "bin/python")

def _poll_for_file(path: Path, timeout_s=75, logger=None, label="archivo"):
    t0=time.time()
    while time.time()-t0 < timeout_s:
        if path.exists(): return True
        time.sleep(0.5)
    if logger: logger.log(f"No apareció {label} tras {timeout_s}s.", "WARN")
    return False

def _safe_rename(path: Path) -> Optional[Path]:
    try:
        if not path.exists(): return None
        new = path.with_name(path.name + f"_corrupt_{int(time.time())}")
        path.rename(new)
        return new
    except Exception:
        return None

def ensure_python_and_venv(ctx, logger, cancel_event):
    # Elegir CPython 3.8+
    candidates=[]
    for p in _list_py_launcher_interpreters():
        if Path(p).exists() and _is_cpython(p):
            v=_version_of_python(p)
            if v>=MIN_PY: candidates.append((v,p))
    v=_version_of_python(sys.executable)
    if _is_cpython(sys.executable) and v>=MIN_PY: candidates.append((v, sys.executable))
    if not candidates:
        raise RuntimeError("No se encontró un CPython 3.8+ instalado. Descarga: https://www.python.org/downloads/windows/")
    candidates.sort(reverse=True); ver, chosen = candidates[0]
    ctx['selected_python']=chosen; ctx['selected_py_version']='.'.join(map(str,ver))
    logger.log(f"Python seleccionado: {chosen} (v{ctx['selected_py_version']})")

    venv_dir = ctx['venv_dir']
    vpy = _venv_python_path(venv_dir)

    if venv_dir.exists() and not vpy.exists():
        renamed = _safe_rename(venv_dir)
        if renamed:
            logger.log(f"Venv previo corrupto renombrado a: {renamed}", "WARN")

    if cancel_event.is_set(): return

    if not venv_dir.exists():
        logger.log(f"Creando venv en: {venv_dir}")
        rc, out, _ = run_cmd([chosen, "-m", "venv", str(venv_dir)], cancel_event=cancel_event, logger=logger, label="venv")
        if rc != 0:
            logger.log("venv stdlib devolvió error; se intentará con virtualenv.", "WARN")
            logger.log(out or "(sin salida de error)", "WARN")
    if not vpy.exists():
        if _poll_for_file(vpy, timeout_s=60, logger=logger, label="python.exe del venv"):
            logger.log("python.exe del venv disponible.")

    if not vpy.exists() and not cancel_event.is_set():
        logger.log("Creando venv con virtualenv (fallback)…", "WARN")
        run_cmd([chosen, "-m", "pip", "install", "--user", "virtualenv"], cancel_event=cancel_event, logger=logger, label="pip virtualenv")
        rc, out, _ = run_cmd([chosen, "-m", "virtualenv", str(venv_dir)], cancel_event=cancel_event, logger=logger, label="virtualenv")
        if rc != 0:
            logger.log("virtualenv también falló.", "WARN")
            logger.log(out or "(sin salida de error)", "WARN")
        else:
            _poll_for_file(vpy, timeout_s=45, logger=logger, label="python.exe del venv (virtualenv)")

    if not vpy.exists():
        logger.log("No se pudo crear venv. Usaré el Python seleccionado SIN venv (pip --user).", "WARN")
        ctx['venv_python'] = chosen
        ctx['no_venv_mode'] = True
    else:
        ctx['venv_python'] = str(vpy)
        ctx['no_venv_mode'] = False

    env=os.environ.copy()
    env["PIP_CACHE_DIR"]=str(ctx['pip_cache_dir'])
    ctx['env']=env

    rc, out, _ = run_cmd([ctx['venv_python'], "-m", "pip", "--version"], env=env, cancel_event=cancel_event, logger=logger, label="pip --version")
    if rc != 0 and not ctx['no_venv_mode']:
        logger.log("Instalando pip en el venv con ensurepip…", "WARN")
        run_cmd([ctx['venv_python'], "-m", "ensurepip", "--upgrade"], env=env, cancel_event=cancel_event, logger=logger, label="ensurepip")
    run_cmd([ctx['venv_python'], "-m", "pip", "install", "--upgrade", "pip", "wheel", "setuptools"], env=env, cancel_event=cancel_event, logger=logger, label="upgrade pip")

def pip_install(ctx, reqs:List[str], logger, cancel_event):
    env=ctx['env']
    base_cmd=[ctx['venv_python'],"-m","pip","install","--no-input","--cache-dir",str(ctx['pip_cache_dir'])]
    if ctx.get('no_venv_mode'):
        base_cmd=[ctx['venv_python'],"-m","pip","install","--user","--no-input","--cache-dir",str(ctx['pip_cache_dir'])]
    run_cmd(base_cmd + ["nuitka>=2.0","pyinstaller>=6.0"], env=env, cancel_event=cancel_event, logger=logger, label="install backends")
    if reqs:
        logger.log(f"Instalando dependencias: {', '.join(reqs)}")
        rc,out,_=run_cmd(base_cmd + reqs, env=env, cancel_event=cancel_event, logger=logger, label="install deps")
        if rc!=0 and not cancel_event.is_set():
            logger.log(out); raise RuntimeError("Fallo instalando dependencias.")
    else:
        logger.log("No hay dependencias a instalar (además de backends).")

def log_env_info(ctx, logger, cancel_event):
    logger.log(f"Windows: {platform.platform()}"); logger.log(f"Arquitectura: {platform.machine()} / {platform.architecture()[0]}")
    rc,out,_=run_cmd([ctx['venv_python'],"-m","pip","--version"], env=ctx['env'], cancel_event=cancel_event); logger.log(out.strip())
    rc,out,_=run_cmd([ctx['venv_python'],"-m","nuitka","--version"], env=ctx['env'], cancel_event=cancel_event); logger.log(f"Nuitka: {out.strip() or 'no reporta versión'}")
    rc,out,_=run_cmd([ctx['venv_python'],"-m","PyInstaller","--version"], env=ctx['env'], cancel_event=cancel_event); logger.log(f"PyInstaller: {out.strip() or 'no reporta versión'}")

def normalize_add_data_args(pairs, backend:str)->List[str]:
    return [f"{s};{d}" if backend=="pyinstaller" else f"{s}={d}" for s,d in pairs]

def gather_data_paths(script_path:Path, selected_dirs:Iterable[str])->List[Tuple[str,str]]:
    base=script_path.parent; pairs=[]
    for d in selected_dirs:
        src=base/d
        if src.exists(): pairs.append((str(src), d))
    return pairs

def write_requirements_lock(ctx, logger, cancel_event):
    rc,out,_=run_cmd([ctx['venv_python'],"-m","pip","freeze"], env=ctx['env'], cancel_event=cancel_event)
    ctx['requirements_lock'].write_text(out, encoding="utf-8"); logger.log(f"requirements.lock: {ctx['requirements_lock']}")

def maybe_use_upx(exe_path:Path, logger, cancel_event):
    upx=shutil.which("upx")
    if not upx:
        logger.log("UPX no detectado en PATH.","WARN"); return
    logger.log("Aplicando UPX (puede causar falsos positivos de antivirus).")
    rc,out,_=run_cmd([upx,"--best","--lzma",str(exe_path)], cancel_event=cancel_event, logger=logger, label="upx")
    if rc!=0: logger.log(f"UPX fallo:\n{out}","WARN")
    else: logger.log("UPX aplicado correctamente.")

def warn_long_paths(path:Path, logger):
    if len(str(path))>180: logger.log("Advertencia: ruta >180 caracteres; sugiere mover a una ruta más corta.","WARN")

def export_build_metadata(ctx, options, exe_path:Path, deps:List[str], logger):
    meta={"backend": ctx.get("used_backend"),"flags":{"windowed": options['windowed'],"use_upx": options['use_upx'],"hidden_imports": options['hidden_imports'] or [],"add_data": options['add_data_pairs'] or [],"include_dirs": options['include_dirs'] or [],"icon": options['icon_path'] or "","work_folder": str(ctx['work_root'])}, "script_hash_sha256": hashlib.sha256(Path(ctx['script_path']).read_bytes()).hexdigest(),"python": ctx.get("selected_py_version",""),"os": platform.platform(),"arch": platform.machine(),"time": time.strftime("%Y-%m-%d %H:%M:%S"),"deps_requested": deps,"requirements_lock_file": str(ctx['requirements_lock']),"exe":{"path": str(exe_path),"size_bytes": exe_path.stat().st_size if exe_path.exists() else None}}
    ctx['metadata_file'].write_text(json.dumps(meta, indent=2), encoding="utf-8"); logger.log(f"Metadata exportada: {ctx['metadata_file']}")

def _list2cmd(cmd_list:List[str])->str:
    try:
        if WIN:
            from subprocess import list2cmdline; return list2cmdline(cmd_list)
        import shlex; return " ".join(shlex.quote(x) for x in cmd_list)
    except Exception: return " ".join(cmd_list)

def detect_msvc()->bool:
    if shutil.which("cl.exe"): return True
    vsw=r"C:\Program Files (x86)\Microsoft Visual Studio\Installer\vswhere.exe"
    if Path(vsw).exists():
        rc,out,_=run_cmd([vsw,"-latest","-requires","Microsoft.VisualStudio.Component.VC.Tools.x86.x64","-property","installationPath"])
        if rc==0 and out.strip(): return True
    for k in ("VSINSTALLDIR","VCToolsInstallDir","VCINSTALLDIR"):
        if os.environ.get(k): return True
    return False

def _nuitka_cmd(ctx, options, add_data_norm:List[str], out_dir:Path)->List[str]:
    cmd=[ctx['venv_python'],"-m","nuitka","--onefile","--standalone","--assume-yes-for-downloads",f"--output-dir={out_dir}"]
    if options['windowed']: cmd+=["--windows-disable-console"]
    cmd+=["--enable-plugin=tk-inter"]
    if options['icon_path']: cmd+=["--windows-icon-from-ico", options['icon_path']]
    for spec in add_data_norm:
        src,dst=spec.split("=",1)
        if Path(src).is_dir(): cmd+=["--include-data-dir", spec]
        else: cmd+=["--include-data-files", spec]
    for h in options['hidden_imports'] or []: cmd+=["--include-module", h]
    for heavy in C_EXT_PACKS:
        if heavy in (options['hidden_imports'] or []):
            if heavy=="numpy": cmd+=["--enable-plugin=numpy"]
            if heavy=="pandas": cmd+=["--enable-plugin=pandas"]
            if heavy=="matplotlib": cmd+=["--enable-plugin=matplotlib"]
    cmd+=[str(ctx['script_path'])]
    return cmd

def build_with_nuitka(ctx, options, logger, add_data_norm:List[str], cancel_event)->Path:
    if not detect_msvc():
        logger.log("MSVC no detectado → cambio automático a PyInstaller.","WARN")
        ctx['used_backend']="pyinstaller"
        return build_with_pyinstaller(ctx, options, logger, normalize_add_data_args(options['add_data_pairs'] or [], "pyinstaller"), cancel_event)
    ctx['used_backend']="nuitka"
    out_dir=ctx['build_dir']/"nuitka-out"; out_dir.mkdir(parents=True, exist_ok=True)
    cmd=_nuitka_cmd(ctx, options, add_data_norm, out_dir); logger.log("Ejecutando Nuitka…"); logger.log(_list2cmd(cmd))
    rc,out,_=run_cmd(cmd, env=ctx['env'], cwd=str(ctx['project_dir']), cancel_event=cancel_event, logger=logger, label="nuitka")
    if rc!=0: raise RuntimeError("Nuitka terminó con error.")
    exe_name=Path(ctx['script_path']).with_suffix(".exe").name
    produced=out_dir/exe_name
    if not produced.exists():
        cand=list(out_dir.glob("*.exe"))
        if cand: produced=max(cand, key=lambda p:p.stat().st_mtime)
    if not produced.exists(): raise RuntimeError("No se encontró el ejecutable producido por Nuitka.")
    return produced

def build_with_pyinstaller(ctx, options, logger, add_data_norm:List[str], cancel_event)->Path:
    ctx['used_backend']="pyinstaller"
    distpath=ctx['build_dir']/"pyinstaller-dist"; workpath=ctx['build_dir']/"pyinstaller-build"; specpath=ctx['build_dir']
    distpath.mkdir(parents=True, exist_ok=True); workpath.mkdir(parents=True, exist_ok=True)
    cmd=[ctx['venv_python'],"-m","PyInstaller","--onefile","--noconfirm","--clean","--distpath",str(distpath),"--workpath",str(workpath),"--specpath",str(specpath)]
    if options['windowed']: cmd+=["--windowed"]
    if options['icon_path']: cmd+=["--icon", options['icon_path']]
    for spec in add_data_norm: cmd+=["--add-data", spec.replace("=", ";")]
    for h in options['hidden_imports'] or []: cmd+=["--hidden-import", h]
    script_str=str(ctx['script_path'])
    if not Path(script_str).exists(): raise RuntimeError(f"Script no encontrado: {script_str}")
    cmd.append(script_str)
    logger.log("Ejecutando PyInstaller…"); logger.log(_list2cmd(cmd))
    rc,out,_=run_cmd(cmd, env=ctx['env'], cwd=str(ctx['project_dir']), cancel_event=cancel_event, logger=logger, label="pyinstaller")
    if rc!=0: raise RuntimeError("PyInstaller terminó con error.")
    exe_name=Path(ctx['script_path']).stem + ".exe"
    produced=distpath/exe_name
    if not produced.exists():
        cand=list(distpath.glob("*.exe"))
        if cand: produced=max(cand, key=lambda p:p.stat().st_mtime)
    if not produced.exists(): raise RuntimeError("No se encontró el ejecutable producido por PyInstaller.")
    return produced

def run_self_test(exe_path:Path, logger, cancel_event):
    logger.log("Ejecutando self-test del ejecutable…")
    try:
        rc,out,_=run_cmd([str(exe_path),"--self-test"], cancel_event=cancel_event, logger=logger, label="self-test")
        if rc==0:
            logger.log("Self-test (--self-test) OK."); logger.log(out.strip()); return
    except Exception: pass
    rc,out,_=run_cmd([str(exe_path)], cancel_event=cancel_event, logger=logger, label="run exe")
    logger.log(out.strip() if out else "(sin salida)"); logger.log(f"Proceso terminó con código {rc}.")

class App:
    def __init__(self, root:tk.Tk):
        self.root=root; self.root.title("Python → EXE (autónomo) — Windows x64")
        self.root.geometry("1100x800")
        self.script_var=tk.StringVar(); self.icon_var=tk.StringVar(); self.workdir_var=tk.StringVar()
        self.hidden_imports_text=tk.Text(self.root, height=4); self.add_data_text=tk.Text(self.root, height=4)
        self.upx_var=tk.BooleanVar(value=False); self.windowed_var=tk.BooleanVar(value=True)
        self.suggest_var=tk.BooleanVar(value=True); self.detailed_var=tk.BooleanVar(value=False); self.selftest_var=tk.BooleanVar(value=True)
        self.dir_vars={d: tk.BooleanVar(value=False) for d in DATA_DIR_CANDIDATES}
        self.logger=None
        self.pb=None; self.status_var=tk.StringVar(value="Listo."); self._heartbeat=0; self._building=False
        self.cancel_event=threading.Event()
        self._build_ui()
        self._tick()

    def _build_ui(self):
        pad=dict(padx=8,pady=6)
        frm_top=ttk.LabelFrame(self.root, text="Script origen (.py)"); frm_top.pack(fill="x", **pad)
        ttk.Entry(frm_top, textvariable=self.script_var).pack(side="left", fill="x", expand=True, padx=6, pady=6)
        ttk.Button(frm_top, text="Seleccionar .py", command=self._select_script).pack(side="right", padx=6, pady=6)

        frm_work=ttk.LabelFrame(self.root, text="Carpeta de trabajo (venv, caches, dist, logs)"); frm_work.pack(fill="x", **pad)
        ttk.Entry(frm_work, textvariable=self.workdir_var).pack(side="left", fill="x", expand=True, padx=6, pady=6)
        ttk.Button(frm_work, text="Elegir carpeta…", command=self._select_workdir).pack(side="right", padx=6, pady=6)
        ttk.Label(frm_work, text="Si se deja vacío, se usará %LOCALAPPDATA%\\py2exe_builds\\<script>_build.").pack(anchor="w", padx=6)

        frm_opts=ttk.LabelFrame(self.root, text="Opciones"); frm_opts.pack(fill="x", **pad)
        left=ttk.Frame(frm_opts); left.pack(side="left", fill="x", expand=True, padx=6, pady=6)
        ttk.Checkbutton(left, text="Sin consola (windowed)", variable=self.windowed_var).grid(row=0,column=0,sticky="w")
        ttk.Checkbutton(left, text="Sugerir hidden imports", variable=self.suggest_var).grid(row=1,column=0,sticky="w")
        ttk.Checkbutton(left, text="Generar log detallado", variable=self.detailed_var).grid(row=2,column=0,sticky="w")
        ttk.Checkbutton(left, text="Probar ejecutable al finalizar (self-test)", variable=self.selftest_var).grid(row=3,column=0,sticky="w")
        ttk.Checkbutton(left, text="Usar UPX si está disponible", variable=self.upx_var).grid(row=4,column=0,sticky="w")

        right=ttk.Frame(frm_opts); right.pack(side="left", fill="x", expand=True, padx=6, pady=6)
        ttk.Label(right, text="Icono (.ico) opcional:").grid(row=0,column=0,sticky="w")
        ttk.Entry(right, textvariable=self.icon_var, width=50).grid(row=0,column=1,sticky="we",padx=(6,0))
        ttk.Button(right, text="Elegir", command=self._select_icon).grid(row=0,column=2,padx=6)

        frm_data=ttk.LabelFrame(self.root, text="Datos y recursos"); frm_data.pack(fill="x", **pad)
        c=0
        for d in DATA_DIR_CANDIDATES:
            ttk.Checkbutton(frm_data, text=f"Incluir '{d}' si existe", variable=self.dir_vars[d]).grid(row=0,column=c,sticky="w"); c+=1

        frm_hi=ttk.LabelFrame(self.root, text="--hidden-import (uno por línea)"); frm_hi.pack(fill="x", **pad)
        self.hidden_imports_text.pack(in_=frm_hi, fill="x", padx=6, pady=6)

        frm_ad=ttk.LabelFrame(self.root, text="--add-data (origen -> destino_relativo), uno por línea"); frm_ad.pack(fill="x", **pad)
        self.add_data_text.pack(in_=frm_ad, fill="x", padx=6, pady=6)

        frm_btns=ttk.Frame(self.root); frm_btns.pack(fill="x", **pad)
        ttk.Button(frm_btns, text="Analizar dependencias", command=self._analyze).pack(side="left")
        ttk.Button(frm_btns, text="Construir EXE", command=self._build).pack(side="left", padx=8)
        ttk.Button(frm_btns, text="Abrir carpeta de salida", command=self._open_dist).pack(side="left")
        self.btn_cancel = ttk.Button(frm_btns, text="Detener", command=self._cancel, state="disabled")
        self.btn_cancel.pack(side="right")

        frm_prog=ttk.LabelFrame(self.root, text="Progreso"); frm_prog.pack(fill="x", **pad)
        self.pb=ttk.Progressbar(frm_prog, mode="determinate", maximum=100); self.pb.pack(fill="x", padx=6, pady=6)
        ttk.Label(frm_prog, textvariable=self.status_var).pack(anchor="w", padx=6)

        frm_log=ttk.LabelFrame(self.root, text="Log de build"); frm_log.pack(fill="both", expand=True, **pad)
        self.txt_log=tk.Text(frm_log, wrap="word"); self.txt_log.pack(side="left", fill="both", expand=True)
        sb=ttk.Scrollbar(frm_log, orient="vertical", command=self.txt_log.yview); self.txt_log.configure(yscrollcommand=sb.set); sb.pack(side="right", fill="y")
        self.logger=GuiLogger(self.txt_log, verbose=False)

    def _tick(self):
        # Animación de actividad
        if self._building:
            dots="⠁⠃⠇⠧⠷⠿⠟⠏"
            self._heartbeat=(self._heartbeat+1)%len(dots)
            s=self.status_var.get()
            s=re.sub(r"[\s⠁⠃⠇⠧⠷⠿⠟⠏]+$", "", s)
            self.status_var.set(s+" "+dots[self._heartbeat])
        self.root.after(300, self._tick)

    def _set_progress(self, step:int, total:int, msg:str):
        pct = int((step/total)*100) if total>0 else 0
        self.pb["maximum"]=100; self.pb["value"]=pct
        self.status_var.set(f"{msg}  [{step}/{total}]")
        self.logger.log(f"[{step}/{total}] {msg}")

    def _cancel(self):
        self.cancel_event.set()
        self.btn_cancel["state"]="disabled"
        self.status_var.set("Cancelación solicitada. Esperando a que termine el proceso en curso…")
        self.logger.log("Cancelación solicitada por el usuario.","WARN")

    def _select_script(self):
        path=filedialog.askopenfilename(title="Seleccionar script .py", filetypes=[("Python","*.py")])
        if path:
            self.script_var.set(path)
            base=Path(path).parent
            for d,var in self.dir_vars.items(): var.set((base/d).exists())
            if not self.workdir_var.get():
                self.workdir_var.set(str(default_workdir(Path(path))))

    def _select_icon(self):
        ico=filedialog.askopenfilename(title="Seleccionar icono .ico", filetypes=[("Icono","*.ico")])
        if ico: self.icon_var.set(ico)

    def _select_workdir(self):
        d=filedialog.askdirectory(title="Elegir carpeta de trabajo")
        if d: self.workdir_var.set(d)

    def _parse_hidden_imports(self)->List[str]:
        return [ln.strip() for ln in self.hidden_imports_text.get("1.0","end").splitlines() if ln.strip()]

    def _parse_add_data(self)->List[Tuple[str,str]]:
        pairs=[]; 
        for ln in self.add_data_text.get("1.0","end").splitlines():
            if "->" in ln:
                src,dst=[x.strip().strip('"').strip("'") for x in ln.split("->",1)]
                if src and dst: pairs.append((src,dst))
        return pairs

    def _analyze(self):
        script=Path(self.script_var.get())
        if not script.exists():
            messagebox.showwarning("Archivo","Selecciona primero un .py válido."); return
        try:
            deps=resolve_dependencies(script, self.logger)
            dyn=detect_dynamic_imports(script)
            if dyn:
                existing=set(self._parse_hidden_imports())
                new=sorted(existing.union(dyn))
                self.hidden_imports_text.delete("1.0","end"); self.hidden_imports_text.insert("1.0","\n".join(new))
                self.logger.log(f"Sugerencias de hidden-import: {', '.join(sorted(dyn))}")
            else:
                self.logger.log("No se detectaron imports dinámicos relevantes.")
            self.logger.log(f"Dependencias estimadas: {', '.join(deps) if deps else '(ninguna)'}")
        except Exception as e:
            messagebox.showerror("Análisis", str(e))

    def _open_dist(self):
        script=Path(self.script_var.get())
        if not script.exists(): return
        work=Path(self.workdir_var.get() or default_workdir(script))
        out=work / "dist"
        out.mkdir(parents=True, exist_ok=True)
        try: os.startfile(str(out))
        except Exception: pass

    def _build(self):
        if not self.script_var.get():
            self._select_script()
            if not self.script_var.get():
                return
        self.cancel_event.clear()
        self.btn_cancel["state"]="normal"
        self._building=True
        self.pb["value"]=0
        script=Path(self.script_var.get())
        work = Path(self.workdir_var.get().strip() or default_workdir(script))
        options={"windowed": self.windowed_var.get(),"suggest_hidden": self.suggest_var.get(),"detailed_log": self.detailed_var.get(),"run_selftest": self.selftest_var.get(),"use_upx": self.upx_var.get(),"icon_path": (self.icon_var.get() or None),"hidden_imports": self._parse_hidden_imports(),"add_data_pairs": self._parse_add_data(),"include_dirs": [d for d,var in self.dir_vars.items() if var.get()],"work_folder": str(work)}
        threading.Thread(target=self._build_worker, args=(script, options), daemon=True).start()

    def _build_worker(self, script:Path, options:dict):
        try:
            steps = ["Crear/validar venv","Resolver dependencias","Instalar dependencias","Info de entorno","requirements.lock","Compilación","Copiar .exe","UPX (opcional)","Exportar metadata","Self-test (opcional)"]
            total = len(steps) - (0 if options["use_upx"] else 1) - (0 if options["run_selftest"] else 1)
            curr=0
            project_dir=script.parent
            work_root=Path(options['work_folder'] or default_workdir(script))
            build_dir=work_root / ".build"
            venv_dir=build_dir / "venv"
            wheels_dir=build_dir / "wheels"
            pip_cache_dir=build_dir / "pip-cache"
            dist_dir=work_root / "dist"
            for d in (work_root, build_dir, venv_dir, wheels_dir, pip_cache_dir, dist_dir):
                d.mkdir(parents=True, exist_ok=True)
            ctx={"project_dir": project_dir,"script_path": script,"work_root": work_root,"build_dir": build_dir,"venv_dir": venv_dir,"wheels_dir": wheels_dir,"pip_cache_dir": pip_cache_dir,"dist_dir": dist_dir,"log_file": build_dir/"build.log","metadata_file": build_dir/"metadata.json","requirements_lock": build_dir/"requirements.lock"}

            self.logger.log("==== INICIO BUILD ===="); self.logger.log(f"Workdir: {work_root}")
            warn_long_paths(work_root, self.logger); warn_long_paths(project_dir, self.logger)

            curr+=1; self._set_progress(curr,total,steps[0])
            ensure_python_and_venv(ctx, self.logger, self.cancel_event); 
            if self.cancel_event.is_set(): raise RuntimeError("Cancelado por el usuario")

            curr+=1; self._set_progress(curr,total,steps[1])
            deps=resolve_dependencies(script, self.logger)

            curr+=1; self._set_progress(curr,total,steps[2])
            pip_install(ctx, deps, self.logger, self.cancel_event); 
            if self.cancel_event.is_set(): raise RuntimeError("Cancelado por el usuario")

            curr+=1; self._set_progress(curr,total,steps[3])
            log_env_info(ctx, self.logger, self.cancel_event)

            curr+=1; self._set_progress(curr,total,steps[4])
            write_requirements_lock(ctx, self.logger, self.cancel_event)

            auto_pairs=gather_data_paths(script, options['include_dirs']); all_pairs=list(auto_pairs)+list(options['add_data_pairs'] or [])
            add_data_nk=normalize_add_data_args(all_pairs,"nuitka")

            curr+=1; self._set_progress(curr,total,steps[5])
            try:
                produced=build_with_nuitka(ctx, options, self.logger, add_data_nk, self.cancel_event)
            except Exception as e:
                self.logger.log(f"Fallo en Nuitka: {e}","WARN")
                add_data_pi=normalize_add_data_args(all_pairs,"pyinstaller")
                produced=build_with_pyinstaller(ctx, options, self.logger, add_data_pi, self.cancel_event)
            if self.cancel_event.is_set(): raise RuntimeError("Cancelado por el usuario")

            curr+=1; self._set_progress(curr,total,steps[6])
            final_exe=dist_dir/produced.name
            if produced!=final_exe: shutil.copy2(str(produced), str(final_exe))
            self.logger.log(f"Ejecutable copiado a: {final_exe}")
            self.logger.log(f"Salida final: {final_exe}")

            if options['use_upx']:
                curr+=1; self._set_progress(curr,total,steps[7])
                self.logger.log("Aviso: UPX puede disparar falsos positivos de antivirus.","WARN")
                maybe_use_upx(final_exe, self.logger, self.cancel_event)

            curr+=1; self._set_progress(curr,total,steps[8])
            export_build_metadata(ctx, options, final_exe, deps, self.logger)

            if options['run_selftest']:
                curr+=1; self._set_progress(curr,total,steps[-1])
                run_self_test(final_exe, self.logger, self.cancel_event)

            self._set_progress(total,total,"Completado")
            self.logger.log("==== BUILD COMPLETADO ====")
            try: os.startfile(str(dist_dir))
            except Exception: pass

        except Exception as e:
            self.logger.log(f"ERROR: {e}","ERROR")
            messagebox.showerror("Build fallido", str(e))
        finally:
            self._building=False
            self.btn_cancel["state"]="disabled"

def main():
    root=tk.Tk(); App(root); root.mainloop()

if __name__=="__main__":
    main()
