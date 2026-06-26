# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for MADRAC Dubbing Extension"""

import sys
from pathlib import Path

block_cipher = None

# ---------------------------------------------------------------------------
# Collect data files
# ---------------------------------------------------------------------------
# Qt .ui files must be bundled alongside the executable
_project_root = Path.cwd()
_ui_src = _project_root / "src" / "madrac_dubbing" / "ui"
_ui_datas = []
if _ui_src.exists():
    for f in _ui_src.rglob("*"):
        if f.is_file() and f.suffix in (".ui",):
            _ui_datas.append((str(f), "madrac_dubbing/ui"))

a = Analysis(
    ['launcher.py'],
    pathex=['src'],
    binaries=[],
    datas=_ui_datas,
    hiddenimports=[
        # Core dependencies
        'edge_tts',
        'librosa',
        'scipy.signal',
        'scipy.fft',
        'soundfile',
        'flask',
        'click',
        'numpy',
        'pyloudnorm',
        # Qt / GUI
        'PySide6',
        'PySide6.QtUiTools',
        'qdarkstyle',
        # Workspace
        'madrac_dubbing.workspace',
        'madrac_dubbing.workspace.resources',
        'madrac_dubbing.workspace.manager',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludedimports=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='madrac-dubbing',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
