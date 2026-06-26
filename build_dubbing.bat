@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM ============================================================
REM MADRAC-DUBBING V1 - BUILD SCRIPT (Windows)
REM ============================================================
REM  Empaqueta madrac-dubbing.exe con PyInstaller
REM ============================================================

cd /d "%~dp0"

echo ============================================
echo   MADRAC-DUBBING V1 - BUILD
echo   Directorio: %CD%
echo ============================================
echo.

REM ------------------------------------------------------------
REM 1. Variables de entorno seguras
REM ------------------------------------------------------------

set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8

set OMP_NUM_THREADS=1
set MKL_NUM_THREADS=1
set OPENBLAS_NUM_THREADS=1
set VECLIB_MAXIMUM_THREADS=1
set NUMEXPR_NUM_THREADS=1

REM ------------------------------------------------------------
REM 2. Verificar estructura
REM ------------------------------------------------------------

echo [1/8] Verificando estructura...

if not exist launcher.py (
    echo ERROR: launcher.py no encontrado
    pause
    exit /b 1
)

if not exist madrac-dubbing.spec (
    echo ERROR: madrac-dubbing.spec no encontrado
    pause
    exit /b 1
)

if not exist src\madrac_dubbing (
    echo ERROR: carpeta src\madrac_dubbing no encontrada
    pause
    exit /b 1
)

echo   [OK]

REM ------------------------------------------------------------
REM 3. Verificar/crear venv
REM ------------------------------------------------------------

echo.
echo [2/8] Verificando entorno virtual...

if not exist venv\Scripts\python.exe (
    echo   Creando venv...
    python -m venv venv
    if !errorlevel! neq 0 (
        echo   ERROR: No se pudo crear venv. Python 3.11+ requerido.
        python --version
        pause
        exit /b 1
    )
)
echo   [OK]

REM ------------------------------------------------------------
REM 4. Activar venv
REM ------------------------------------------------------------

echo.
echo [3/8] Activando venv...

call venv\Scripts\activate.bat

if !errorlevel! neq 0 (
    echo ERROR: No se pudo activar venv
    pause
    exit /b 1
)

python --version

REM ------------------------------------------------------------
REM 5. Verificar ffmpeg (requerido)
REM ------------------------------------------------------------

echo.
echo [4/8] Verificando ffmpeg...

if exist ffmpeg.exe (
    echo   [OK] ffmpeg.exe local
) else if exist ..\madrac-subs\ffmpeg.exe (
    echo   Copiando ffmpeg.exe desde ..\madrac-subs...
    copy ..\madrac-subs\ffmpeg.exe .
    copy ..\madrac-subs\ffprobe.exe .
) else (
    echo   [WARN] ffmpeg.exe no encontrado.
    echo   Descarga: https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip
    echo   Extrae ffmpeg.exe y ffprobe.exe en %CD%
)

REM ------------------------------------------------------------
REM 6. Instalar dependencias
REM ------------------------------------------------------------

echo.
echo [5/8] Instalando dependencias...

python -m pip install --upgrade pip -q

python -m pip install -r requirements.txt -q 2> pip_errors.log

if !errorlevel! neq 0 (
    echo   [WARN] pip reporto errores. Revisa pip_errors.log
) else (
    echo   [OK] dependencias instaladas
)

REM ------------------------------------------------------------
REM 7. Verificar imports
REM ------------------------------------------------------------

echo.
echo [6/8] Verificando imports...

set IMPORT_FAIL=0

python -c "import edge_tts; print('  edge-tts OK')" || set IMPORT_FAIL=1
python -c "import librosa; print('  librosa OK')"  || set IMPORT_FAIL=1
python -c "import soundfile; print('  soundfile OK')"  || set IMPORT_FAIL=1
python -c "import flask; print('  Flask OK')" || set IMPORT_FAIL=1
python -c "import click; print('  click OK')" || set IMPORT_FAIL=1
python -c "import pyloudnorm; print('  pyloudnorm OK')" || set IMPORT_FAIL=1
python -c "import numpy; print('  numpy OK')" || set IMPORT_FAIL=1

if "!IMPORT_FAIL!"=="1" (
    echo   [WARN] algunas importaciones fallaron, revisa pip_errors.log
) else (
    echo   [OK] todos los imports correctos
)

REM ------------------------------------------------------------
REM 8. Test de ejecucion desde codigo fuente
REM ------------------------------------------------------------

echo.
echo [7/8] Probando importacion del modulo...

set PYTHONPATH=%CD%\src

python -c "from madrac_dubbing.__main__ import cli; print('  [OK] import madrac_dubbing exitoso')"

if !errorlevel! neq 0 (
    echo.
    echo ERROR: No se puede importar madrac_dubbing
    pause
    exit /b 1
)

REM ------------------------------------------------------------
REM 9. PyInstaller
REM ------------------------------------------------------------

echo.
echo ============================================
echo  INICIANDO BUILD
echo  python -m PyInstaller madrac-dubbing.spec --clean
echo ============================================
echo  Inicio: %date% %time%
echo.

REM ------------------------------------------------------------
REM 10. Limpiar builds anteriores
REM ------------------------------------------------------------

if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo   [OK] Builds anteriores eliminados

REM ------------------------------------------------------------
REM 11. Build
REM ------------------------------------------------------------

echo.
python -m PyInstaller madrac-dubbing.spec --clean 2> build_errors.log

set BUILD_EXIT=!ERRORLEVEL!

echo  Fin: %date% %time%

if NOT "!BUILD_EXIT!"=="0" (
    echo.
    echo BUILD FALLIDO - Codigo: !BUILD_EXIT!
    echo Revisar build_errors.log
    type build_errors.log
    pause
    exit /b 1
)

REM ------------------------------------------------------------
REM 12. Validacion ejecutable
REM ------------------------------------------------------------

echo.
echo [8/8] Validando ejecutable...

if not exist dist\madrac-dubbing.exe (
    echo ERROR: no se genero dist\madrac-dubbing.exe
    pause
    exit /b 1
)

echo.
echo Test: --help
dist\madrac-dubbing.exe --help

if !errorlevel! neq 0 (
    echo ERROR: fallo --help
    pause
    exit /b 1
)

REM ------------------------------------------------------------
REM Resultado
REM ------------------------------------------------------------

echo.
echo ============================================
echo BUILD EXITOSO
echo ============================================

for %%I in ("dist\madrac-dubbing.exe") do (
    set FILE_SIZE=%%~zI
)

set /a SIZE_MB=!FILE_SIZE! / 1048576

echo.
echo Ejecutable: dist\madrac-dubbing.exe
echo Tamano:     !SIZE_MB! MB
echo.
echo Logs:
echo   build_errors.log
echo   pip_errors.log
echo.

pause
