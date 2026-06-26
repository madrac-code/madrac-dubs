"""
Workspace Manager — Public high-level API for the MADRAC Shared Workspace.

Single authority for:
- ``workspace/``, ``.cache/``, ``plugins/`` directories
- Module discovery (M, A, D, R, WEB)
- Workspace resource registration
- Integration status

Usage::

    from madrac_dubbing.workspace_manager import get_manager

    mgr = get_manager()
    mgr.init_workspace()
    modules = mgr.discover_modules()
    print(mgr.is_integrated)
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from .workspace import get_workspace_manager as _get_ws_manager
from .workspace.manager import WorkspaceManager as _WorkspaceManager
from .workspace.manager import register_madrac_dubbing_resources
from .workspace.manager import register_madrac_subs_resources

logger = logging.getLogger(__name__)

_manager_instance: Optional["WorkspaceManager"] = None


class WorkspaceManager:
    """High-level convenience wrapper over the core WorkspaceManager.

    Attributes
    ----------
    app_dir : Path
        Root directory (where the executable lives).
    workspace_root : Path
        ``app_dir / "workspace"``
    cache_root : Path
        ``app_dir / ".cache"``
    plugins_root : Path
        ``app_dir / "plugins"``
    """

    def __init__(self, app_dir: Optional[Path] = None):
        self._inner = _get_ws_manager(app_dir)
        self.app_dir: Path = self._inner.app_dir
        self.workspace_root: Path = self._inner.workspace_root
        self.cache_root: Path = self._inner.cache_root
        self.plugins_root: Path = self._inner.plugins_root

    # ------------------------------------------------------------------
    # Initialisation
    # ------------------------------------------------------------------

    def init_workspace(self) -> bool:
        """One-shot workspace initialisation.

        1.  Create directory structure (``.cache/``, ``plugins/``, ``workspace/``).
        2.  Register DUBBING resources.
        3.  If other MADRAC modules are detected, register their resources too.
        4.  Persist state.

        Returns ``True`` on success, ``False`` on failure (never raises).
        """
        try:
            self._inner.ensure_structure()
            register_madrac_dubbing_resources(self._inner)

            modules = self.discover_modules()
            if modules.get("subs"):
                register_madrac_subs_resources(self._inner)
                logger.info("MADRAC-SUBS detected — SUBS resources registered.")

            self._inner.save_state()
            logger.info("Shared workspace ready at %s", self.workspace_root)
            return True
        except Exception as e:
            logger.error("Workspace initialisation failed: %s", e)
            return False

    # ------------------------------------------------------------------
    # Module discovery
    # ------------------------------------------------------------------

    def discover_modules(self) -> Dict[str, bool]:
        """Detect MADRAC executables in **app_dir**.

        Returns a dict: ``{"subs": bool, "dubbing": bool, "assistant": bool, "recognition": bool}``
        """
        return self._inner.discover_modules()

    def get_detected_modules(self) -> List[str]:
        """Human-readable list of detected modules, e.g. ``["MADRAC-SUBS (M)"]``."""
        return self._inner.get_detected_modules()

    @property
    def is_integrated(self) -> bool:
        """``True`` when a non-DUBBING MADRAC module is present."""
        return self._inner.is_integrated

    # ------------------------------------------------------------------
    # Delegated resource helpers
    # ------------------------------------------------------------------

    def ensure_shared_dirs(self) -> Dict[str, str]:
        """Return a dict of important workspace paths (all strings)."""
        return {
            "app_dir": str(self.app_dir),
            "workspace": str(self.workspace_root),
            "cache": str(self.cache_root),
            "plugins": str(self.plugins_root),
            "temporal": str(self.cache_root / "temporal"),
            "active": str(self.workspace_root / "active"),
            "events": str(self.workspace_root / "events"),
            "projects": str(self.workspace_root / "projects"),
            "sessions": str(self.workspace_root / "sessions"),
            "playback": str(self.workspace_root / "playback"),
            "resources": str(self.workspace_root / "resources"),
        }

    def get_integration_status(self) -> Dict[str, Any]:
        """Return a structured status dict for GUI / API consumption."""
        modules = self.discover_modules()
        return {
            "workspace_root": str(self.workspace_root),
            "is_integrated": self.is_integrated,
            "detected_modules": modules,
            "detected_labels": self.get_detected_modules(),
        }


def get_manager(app_dir: Optional[Path] = None) -> WorkspaceManager:
    """Return the global ``WorkspaceManager`` singleton."""
    global _manager_instance
    if _manager_instance is None:
        _manager_instance = WorkspaceManager(app_dir)
    return _manager_instance


def reset_manager():
    """Reset singleton (useful for testing)."""
    global _manager_instance
    _manager_instance = None
    from .workspace import reset_workspace_manager
    reset_workspace_manager()


__all__ = [
    "WorkspaceManager",
    "get_manager",
    "reset_manager",
]
