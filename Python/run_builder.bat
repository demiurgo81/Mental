@echo off
setlocal
pushd "%~dp0"
where py >nul 2>&1 && (py "%~dp0\py_2_exe.py" & goto :eof)
where python >nul 2>&1 && (python "%~dp0\py_2_exe.py" & goto :eof)
echo No se encontro Python. Instala desde https://www.python.org/downloads/windows/
pause
