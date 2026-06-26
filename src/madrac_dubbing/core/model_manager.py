"""
MADRAC Model Manager — download & status for AI models.

Models are NOT auto-downloaded.  The user must explicitly trigger downloads
via the GUI settings dialog or the CLI command::

    python -m madrac_dubbing download-models demucs

This module provides status queries so the UI can show size, install state,
and progress.
"""

import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------------

@dataclass
class ModelInfo:
    """Description of a downloadable AI model."""
    name: str
    display_name: str
    description: str
    size_mb: int
    repo_id: str                  # HuggingFace repo or torch.hub path
    variant: str = ""             # Model variant (e.g. htdemucs_ft)
    installed: bool = False
    requires: List[str] = field(default_factory=list)  # pip packages


MODEL_REGISTRY: Dict[str, ModelInfo] = {
    "demucs": ModelInfo(
        name="demucs",
        display_name="Demucs HT",
        description="AI source separation (vocals, music, effects, ambience)",
        size_mb=500,
        repo_id="facebook/demucs",
        variant="htdemucs_ft",
        requires=["demucs", "torch"],
    ),
    # Future models will be added here:
    # "whisper": ModelInfo(...),
    # "marianmt": ModelInfo(...),
}


# ---------------------------------------------------------------------------
# Model manager
# ---------------------------------------------------------------------------

class ModelManager:
    """Query and download AI models for the MADRAC ecosystem."""

    _plugins_root: Optional[Path] = None

    @classmethod
    def init(cls, plugins_root: Path) -> None:
        """Set the workspace plugins root for model storage.

        Must be called once during application startup so that
        :meth:`storage_path` returns the correct path.
        """
        cls._plugins_root = plugins_root
        logger.info("ModelManager initialised — plugins root: %s", plugins_root)

    @classmethod
    def storage_path(cls, name: str) -> Path:
        """Return the expected storage path for a model's weights.

        ``<plugins_root>/models/<name>/`` — currently a *future* location;
        existing models still live in the torch hub cache until migration.
        """
        if cls._plugins_root is None:
            raise RuntimeError("ModelManager.init() not called — set plugins_root first")
        return cls._plugins_root / "models" / name

    @staticmethod
    def list_models() -> Dict[str, ModelInfo]:
        return dict(MODEL_REGISTRY)

    @staticmethod
    def get_model(name: str) -> Optional[ModelInfo]:
        return MODEL_REGISTRY.get(name)

    @staticmethod
    def is_installed(name: str) -> bool:
        """Check whether a model's runtime dependencies are available."""
        info = MODEL_REGISTRY.get(name)
        if info is None:
            return False
        if name == "demucs":
            return ModelManager._check_demucs()
        return False

    @staticmethod
    def status() -> Dict[str, dict]:
        """Return install status for all registered models."""
        result = {}
        for name, info in MODEL_REGISTRY.items():
            installed = ModelManager.is_installed(name)
            result[name] = {
                "name": info.display_name,
                "size_mb": info.size_mb,
                "installed": installed,
                "variant": info.variant,
                "description": info.description,
            }
        return result

    @staticmethod
    def download(
        name: str,
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> bool:
        """Download a model.  Currently only ``"demucs"`` is supported.

        Parameters
        ----------
        name:
            Model key from ``MODEL_REGISTRY``.
        progress_callback:
            Optional ``fn(percent: int, message: str)`` for UI updates.

        Returns
        -------
        ``True`` on success.
        """
        if name == "demucs":
            return ModelManager._download_demucs(progress_callback)
        raise ValueError(f"Unknown model: {name}")

    # ---- internal helpers ------------------------------------------------

    @staticmethod
    def _check_demucs() -> bool:
        try:
            import demucs  # noqa: F401
            import torch  # noqa: F401
            return True
        except ImportError:
            return False

    @staticmethod
    def _download_demucs(
        progress_callback: Optional[Callable[[int, str], None]] = None,
    ) -> bool:
        """Install pip deps + download Demucs model weights."""
        import subprocess
        import sys

        def _progress(pct: int, msg: str):
            if progress_callback:
                progress_callback(pct, msg)
            logger.info("[%d%%] %s", pct, msg)

        try:
            # Step 1: install pip packages
            _progress(10, "Installing Demucs and PyTorch...")
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "demucs", "torch", "xxhash", "-q"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )

            # Step 2: trigger model download by importing
            _progress(50, "Downloading model weights (htdemucs_ft)...")
            import torch
            torch.hub.set_trusted_repo_list(["facebook/demucs:main"])
            import torch.hub as hub
            hub.load("facebook/demucs:main", "htdemucs_ft")

            _progress(100, "Demucs installation complete.")
            return True

        except Exception as e:
            logger.error("Demucs download failed: %s", e)
            if progress_callback:
                progress_callback(0, f"Error: {e}")
            return False


__all__ = [
    "ModelManager",
    "ModelInfo",
    "MODEL_REGISTRY",
]
