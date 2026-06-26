from pathlib import Path
import sys


def get_app_dir() -> Path:
    """
    Devuelve la carpeta donde está el exe.
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent

    return Path(__file__).resolve().parents[3]


APP_DIR = get_app_dir()

MADRAC_SUBS_EXE = APP_DIR / "madrac-subs.exe"

FFMPEG_EXE = APP_DIR / "ffmpeg.exe"
FFPROBE_EXE = APP_DIR / "ffprobe.exe"