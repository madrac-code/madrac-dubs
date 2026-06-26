"""
MADRAC-DUBBING Launcher

Startup flow:
  1. Parse ``--gui`` flag (fast, no heavy imports)
  2. Initialize workspace (creates ``.cache/``, ``plugins/``, ``workspace/``)
  3. Detect operating mode
  4. If ``--gui`` → launch Qt GUI (validate_installation skipped — ffmpeg is
     checked at pipeline runtime)
  5. If no ``--gui`` → validate installation, then run CLI
"""

import sys
from pathlib import Path

# Allow running from source: `python launcher.py --gui`
_src = Path(__file__).resolve().parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def _init_workspace():
    """One-shot workspace initialisation."""
    from madrac_dubbing.workspace_manager import get_manager
    mgr = get_manager()
    mgr.init_workspace()
    # Also activate legacy facade for gui.py (tkinter fallback)
    from madrac_dubbing.shared_workspace import workspace
    workspace.is_available = True
    workspace.__post_init__()
    return mgr


def _detect_mode(launcher_args=None):
    """Detect operating mode from CLI flags + environment."""
    from madrac_dubbing.integration_layer import detect_capabilities, determine_mode
    launcher_args = launcher_args or {}
    cli_standalone = launcher_args.get('--standalone', False)
    cli_skip_validate = launcher_args.get('--skip-validate-madrac-subs', False)
    cli_integrated = launcher_args.get('--integrated', False)
    cli_mode = None
    if cli_standalone:
        cli_mode = 'standalone'
    elif cli_integrated:
        cli_mode = 'integrated'

    capabilities = detect_capabilities()
    mode, skip = determine_mode(capabilities, cli_mode=cli_mode,
                                cli_standalone=cli_standalone,
                                cli_skip_validate=cli_skip_validate)
    # Persist globally
    from madrac_dubbing.integration_layer import set_mode, reload_capabilities
    reload_capabilities()
    set_mode(mode, skip)
    return mode, skip


def _launch_gui(workspace_mgr):
    """Launch Qt GUI with tkinter fallback."""
    try:
        from madrac_dubbing.gui_qt import run_gui_qt
        run_gui_qt()
    except Exception as e:
        logger.warning("Qt GUI failed (%s), falling back to tkinter...", e)
        from madrac_dubbing.gui import run_gui
        run_gui()


def _validate_installation(mode, skip):
    """Validate ffmpeg etc.  Only called for non-GUI modes."""
    from madrac_dubbing.__main__ import validate_installation
    validate_installation(mode, skip)


def _run_cli():
    """Run the Click CLI group."""
    from madrac_dubbing.__main__ import cli
    cli()


if __name__ == "__main__":
    # Capture launcher-only flags BEFORE stripping them for Click
    has_gui = "--gui" in sys.argv
    _LAUNCHER_FLAGS = {"--gui", "--standalone", "--integrated",
                       "--skip-validate-madrac-subs"}
    _launcher_args = {f: (f in sys.argv) for f in _LAUNCHER_FLAGS}
    sys.argv = [a for a in sys.argv if a not in _LAUNCHER_FLAGS]

    try:
        # 1. Initialise workspace (creates dirs, detects modules)
        mgr = _init_workspace()

        # 2. Detect operating mode (using captured launcher flags)
        mode, skip = _detect_mode(_launcher_args)
        logger.info("MADRAC-DUBBING starting — mode: %s", mode)
        from madrac_dubbing.__main__ import _warn_inactive_mode
        _warn_inactive_mode(mode)

        # 3. Route to GUI or CLI
        if has_gui:
            _launch_gui(mgr)
        else:
            _validate_installation(mode, skip)
            _run_cli()

    except Exception as e:
        logger.error("Fatal error: %s", e, exc_info=True)
        sys.exit(1)
