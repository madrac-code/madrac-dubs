"""
MADRAC-DUBBING - Two-Mode Architecture Implementation (Legacy Compatibility)

This module is kept for backward compatibility.  New code should import
from ``madrac_dubbing.workspace_manager`` or ``madrac_dubbing.integration_layer``
instead.

Delegates module detection to ``WorkspaceManager`` internally.
"""

import sys
import os
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List

from .integration_layer import capabilities as _layer_caps
from .workspace_manager import get_manager as _get_ws_manager

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

CONFIG_DIR = Path.home() / ".madrac"
CONFIG_FILE = CONFIG_DIR / "madrac-dubbing.json"

DEFAULT_CONFIG = {
    "mode": "auto",
    "require_madrac_subs": False,
    "skip_validation": False,
    "shared_cache_enabled": True,
    "shared_segments_enabled": True,
    "shared_timeline_enabled": True,
    "shared_audio_enabled": True,
    "cache_dir": str(CONFIG_DIR / "cache"),
    "data_dir": str(CONFIG_DIR / "data")
}


class MADRACIntegration:
    """Manages MADRAC ecosystem integration (legacy API)."""

    def __init__(self):
        self.mode = "auto"
        self.madrac_subs_available = False
        self.integration_available = False
        self.config = self._load_config()
        self._detect_integration()

    def _load_config(self) -> Dict[str, Any]:
        try:
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE, 'r') as f:
                    user_config = json.load(f)
                    return {**DEFAULT_CONFIG, **user_config}
        except Exception as e:
            logger.warning(f"Failed to load config: {e}, using defaults")
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        with open(CONFIG_FILE, 'w') as f:
            json.dump(DEFAULT_CONFIG, f, indent=2)
        return DEFAULT_CONFIG.copy()

    def _detect_integration(self):
        if os.environ.get('MADRAC_INTEGRATION_AVAILABLE', '').lower() == 'true':
            self.madrac_subs_available = True
            self.integration_available = True
            self._determine_mode()
            return

        # Delegate to WorkspaceManager (preferred path)
        try:
            mgr = _get_ws_manager()
            modules = mgr.discover_modules()
            self.madrac_subs_available = modules.get("subs", False)
            self.integration_available = any(
                v for k, v in modules.items() if k != "dubbing"
            )
        except Exception:
            # Legacy fallback
            self.madrac_subs_available = _layer_caps.subs
            self.integration_available = _layer_caps.any_integration_available()

        self._determine_mode()

    def _determine_mode(self):
        env_mode = (
            os.environ.get('MADRAC_OPERATING_MODE')
            or os.environ.get('MADRAC_MODE')
        )
        if env_mode:
            mode = env_mode.lower()
        else:
            mode = self.config["mode"]

        if mode == "auto":
            self.mode = "integrated" if self.integration_available else "standalone"
        elif mode == "integrated":
            self.mode = "integrated" if self.integration_available else "standalone"
        elif mode == "standalone":
            self.mode = "standalone"
        else:
            self.mode = "standalone"

        logger.info(f"Mode determined: {self.mode}")
        logger.info(f"MADRAC-SUBS available: {self.madrac_subs_available}")
        logger.info(f"Integration available: {self.integration_available}")

    def get_mode_info(self) -> Dict[str, Any]:
        mode_info = {
            "mode": self.mode,
            "madrac_subs_available": self.madrac_subs_available,
            "integration_available": self.integration_available,
            "features": self._get_mode_features()
        }
        return mode_info

    def _get_mode_features(self) -> Dict[str, bool]:
        base_features = {
            "extraction": True,
            "transcription": True,
            "tts": True,
            "voice_reduction": True,
            "audio_mixing": True,
            "video_mux": True,
            "progress_tracking": True,
            "error_handling": True,
        }
        if self.integration_available:
            base_features.update({
                "shared_segment_reuse": True,
                "shared_audio_reuse": True,
                "shared_timeline_sync": True,
                "enhanced_workflow": True,
                "optimized_performance": True,
                "reduced_processing_time": True,
                "project_sharing": True,
                "collaborative_editing": True,
            })
        return base_features

    def integrate_with_madrac(self) -> Dict[str, Any]:
        if not self.integration_available:
            return {
                "status": "error",
                "message": "MADRAC integration not available"
            }
        result = {
            "status": "success",
            "message": "MADRAC integration established",
            "features": {}
        }
        try:
            if self._check_shared_segments():
                result["features"]["segments"] = "available"
            if self._check_shared_audio():
                result["features"]["audio"] = "available"
            if self._check_shared_timeline():
                result["features"]["timeline"] = "available"
            if self._check_shared_projects():
                result["features"]["projects"] = "available"
        except Exception as e:
            logger.error(f"Integration error: {e}")
            result["status"] = "error"
            result["message"] = f"Integration failed: {str(e)}"
        return result

    def _check_shared_segments(self) -> bool:
        return (Path(self.config["data_dir"]) / "shared_segments.json").exists()

    def _check_shared_audio(self) -> bool:
        return (Path(self.config["cache_dir"]) / "shared_audio.wav").exists()

    def _check_shared_timeline(self) -> bool:
        return (Path(self.config["data_dir"]) / "shared_timeline.json").exists()

    def _check_shared_projects(self) -> bool:
        projects_dir = Path(self.config["data_dir"]) / "projects"
        return projects_dir.exists() and any(projects_dir.glob("*.json"))
