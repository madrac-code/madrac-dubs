@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM ============================================================
REM MADRAC-DUBBING V1 - RUN SCRIPT (desarrollo/pruebas)
REM ============================================================
REM  Ejemplo:
REM    run_dubbing.bat --help
REM    run_dubbing.bat dub --video video.mp4 --srt subs.srt --output out.mp4
REM    run_dubbing.bat api --port 5000
REM ============================================================

cd /d "%~dp0"

echo ============================================
echo   MADRAC-DUBBING V1 - RUN
echo   Directorio: %CD%
echo ============================================
echo.

REM ------------------------------------------------------------
REM 1. Variables de entorno
REM ------------------------------------------------------------

set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

REM ------------------------------------------------------------
REM 2. Verificar estructura
REM ------------------------------------------------------------

if not exist launcher.py (
    echo ERROR: launcher.py no encontrado
    pause
    exit /b 1
)

if not exist src\madrac_dubbing (
    echo ERROR: src\madrac_dubbing no encontrada
    pause
    exit /b 1
)

REM ------------------------------------------------------------
REM 3. Verificar/crear venv
REM ------------------------------------------------------------

echo [1/4] Verificando entorno virtual...

if not exist venv\Scripts\python.exe (
    echo   Creando venv...
    python -m venv venv
    if !errorlevel! neq 0 (
        echo   ERROR: No se pudo crear venv. Python 3.11+ requerido.
        python --version
        pause
        exit /b 1
    )
    echo   [OK] venv creado
) else (
    echo   [OK] venv detectado
)

REM ------------------------------------------------------------
REM 4. Activar venv
REM ------------------------------------------------------------

echo.
echo [2/4] Activando venv...

call venv\Scripts\activate.bat

if !errorlevel! neq 0 (
    echo ERROR: No se pudo activar venv
    pause
    exit /b 1
)

python --version

REM ------------------------------------------------------------
REM 5. Verificar dependencias (instalar si falta alguna)
REM ------------------------------------------------------------

echo.
echo [3/4] Verificando dependencias...

python -c "import edge_tts" 2>nul
if !errorlevel! neq 0 (
    echo   Instalando dependencias...
    pip install -r requirements.txt -q
    if !errorlevel! neq 0 (
        echo   [WARN] pip reporto errores
    ) else (
        echo   [OK] dependencias instaladas
    )
) else (
    echo   [OK] dependencias presentes
)

REM ------------------------------------------------------------
REM 6. Ejecutar
REM ------------------------------------------------------------

echo.
echo [4/4] Ejecutando MADRAC-DUBBING...
echo   python launcher.py %*
echo.

set PYTHONPATH=%CD%\src

python launcher.py %*

if !errorlevel! neq 0 (
    echo.
    echo ERROR: MADRAC-DUBBING termino con codigo !errorlevel!
    pause
    exit /b 1
)

echo.
echo [OK] MADRAC-DUBBING finalizo correctamente
echo.
pause
