"""
Workspace Manager

Central manager for the MADRAC Shared Workspace.
Handles filesystem operations, resource registration, lifecycle management,
and module discovery across the MADRAC ecosystem.
"""

import json
import os
import shutil
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
import logging

from .resources import (
    WorkspaceResource,
    ResourceType,
    ResourceStatus,
    DEFAULT_RESOURCES,
)

logger = logging.getLogger(__name__)


class WorkspaceManager:
    """
    Manages the MADRAC Shared Workspace.
    
    The workspace is rooted at APP_DIR (where the executable lives) and provides
    a unified filesystem structure shared by all MADRAC modules.
    """
    
    def __init__(self, app_dir: Optional[Path] = None, auto_create: bool = True):
        """
        Initialize the workspace manager.
        
        Args:
            app_dir: Root directory for the workspace (defaults to APP_DIR)
            auto_create: Whether to create directory structure on init
        """
        if app_dir is None:
            from ..utils.paths import APP_DIR
            app_dir = APP_DIR
        
        self.app_dir = Path(app_dir).resolve()
        self.workspace_root = self.app_dir / "plugins"
        self.cache_root = self.app_dir / ".cache"
        self.plugins_root = self.app_dir / "plugins"
        self.stems_root = self.cache_root / "stems"
        
        # Thread-safe resource registry
        self._resources: Dict[ResourceType, WorkspaceResource] = {}
        self._lock = threading.RLock()
        self._modules_cache: Optional[Dict[str, bool]] = None
        
        # Initialize default resources
        self._initialize_default_resources()
        
        if auto_create:
            self.ensure_structure()
    
    def _initialize_default_resources(self):
        """Initialize the resource registry with default resources."""
        with self._lock:
            for rtype, config in DEFAULT_RESOURCES.items():
                resource = WorkspaceResource(
                    resource_type=rtype,
                    path=config["path"],
                    status=ResourceStatus.MISSING,
                    metadata={"description": config.get("description", "")},
                )
                self._resources[rtype] = resource
    
    def ensure_structure(self) -> bool:
        """
        Create the complete workspace directory structure.
        
        Creates:
        - .cache/
        - plugins/
        - workspace/ with all subdirectories
        
        Idempotent — safe to call multiple times.
        
        Returns:
            True if successful, False otherwise
        """
        try:
            directories = [
                self.cache_root,
                self.cache_root / "temporal",
                self.plugins_root,
                self.workspace_root,
            ]

            for rtype, config in DEFAULT_RESOURCES.items():
                full_path = self.workspace_root / config["path"]
                if full_path.suffix:
                    directories.append(full_path.parent)
                else:
                    directories.append(full_path)

            for dir_path in directories:
                dir_path.mkdir(parents=True, exist_ok=True)

            logger.debug("Workspace structure at %s", self.workspace_root)
            return True

        except Exception as e:
            logger.error("Failed to create workspace structure: %s", e)
            return False

    # -------------------------------------------------------------------
    # Module discovery — detect MADRAC executables in APP_DIR
    # -------------------------------------------------------------------

    MADRAC_EXECUTABLES = [
        "madrac-subs.exe",
        "madrac-dubbing.exe",
        "madrac-asistente.exe",
        "madrac-recognition.exe",
        "madrac-subs-web.exe",
    ]

    def discover_modules(self, force: bool = False) -> Dict[str, bool]:
        """Scan APP_DIR for known MADRAC executables.

        Results are cached after the first call.  Pass ``force=True`` to
        re-scan the filesystem.

        Returns:
            Dict mapping short module names to availability::

                {"subs": True, "dubbing": True, "assistant": False, "recognition": False}
        """
        if not force and self._modules_cache is not None:
            return self._modules_cache

        result: Dict[str, bool] = {}
        for exe in self.MADRAC_EXECUTABLES:
            name = exe.replace("madrac-", "").replace("-web", "_web").replace(".exe", "")
            result[name] = (self.app_dir / exe).exists()

        self._modules_cache = result
        logger.debug(
            "Module discovery: %s",
            ", ".join(f"{k}={v}" for k, v in result.items()),
        )
        return result

    def get_detected_modules(self) -> List[str]:
        """Return list of detected module display names."""
        modules = self.discover_modules()
        names = []
        mapping = {
            "subs": "MADRAC-SUBS (M)",
            "dubbing": "MADRAC-DUBBING (D)",
            "asistente": "MADRAC-ASISTENTE (A)",
            "recognition": "MADRAC-RECOGNITION (R)",
            "subs_web": "MADRAC-SUBS-WEB (W)",
        }
        for key, label in mapping.items():
            if modules.get(key):
                names.append(label)
        return names

    @property
    def is_integrated(self) -> bool:
        """True when any external MADRAC module (other than self) is detected."""
        modules = self.discover_modules()
        # dubbing always detects itself, so check for others
        return any(v for k, v in modules.items() if k != "dubbing")
    
    def register_resource(
        self,
        resource_type: ResourceType,
        path: Union[str, Path],
        metadata: Optional[Dict[str, Any]] = None,
        status: ResourceStatus = ResourceStatus.AVAILABLE,
    ) -> WorkspaceResource:
        """
        Register a resource in the workspace.
        
        Args:
            resource_type: Type of resource
            path: Relative path within workspace root
            metadata: Optional metadata
            status: Initial status
            
        Returns:
            The registered WorkspaceResource
        """
        full_path = self.workspace_root / path
        full_path.parent.mkdir(parents=True, exist_ok=True)
        
        with self._lock:
            resource = WorkspaceResource(
                resource_type=resource_type,
                path=str(path),
                status=status,
                metadata=metadata or {},
            )
            resource.mark_available(metadata)
            self._resources[resource_type] = resource
            logger.debug(f"Registered resource: {resource_type.value} -> {path}")
            return resource
    
    def get_resource(self, resource_type: ResourceType) -> Optional[WorkspaceResource]:
        """Get a resource by type."""
        with self._lock:
            return self._resources.get(resource_type)
    
    def get_resource_path(self, resource_type: ResourceType) -> Optional[Path]:
        """Get the absolute filesystem path for a resource."""
        with self._lock:
            resource = self._resources.get(resource_type)
            if resource:
                return self.workspace_root / resource.path
        return None
    
    def update_resource(
        self,
        resource_type: ResourceType,
        metadata: Optional[Dict[str, Any]] = None,
        status: Optional[ResourceStatus] = None,
    ) -> bool:
        """Update an existing resource's metadata or status."""
        with self._lock:
            resource = self._resources.get(resource_type)
            if not resource:
                return False
            
            if metadata:
                resource.metadata.update(metadata)
            if status:
                resource.status = status
            resource.updated_at = time.time()
            return True
    
    def mark_resource_available(
        self,
        resource_type: ResourceType,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """Mark a resource as available."""
        return self.update_resource(resource_type, metadata, ResourceStatus.AVAILABLE)
    
    def mark_resource_outdated(
        self,
        resource_type: ResourceType,
        reason: str = "",
    ) -> bool:
        """Mark a resource as outdated."""
        with self._lock:
            resource = self._resources.get(resource_type)
            if resource:
                resource.mark_outdated(reason)
                return True
        return False
    
    def list_resources(self, status_filter: Optional[ResourceStatus] = None) -> List[WorkspaceResource]:
        """List all registered resources, optionally filtered by status."""
        with self._lock:
            resources = list(self._resources.values())
            if status_filter:
                resources = [r for r in resources if r.status == status_filter]
            return resources
    
    def get_available_resources(self) -> List[str]:
        """Get names of available resources."""
        with self._lock:
            return [
                r.resource_type.value
                for r in self._resources.values()
                if r.is_available
            ]
    
    def save_state(self, path: Optional[Path] = None) -> bool:
        """
        Save workspace state to a JSON file.
        
        Args:
            path: Optional path (defaults to .cache/workspace_state.json)
            
        Returns:
            True if successful
        """
        if path is None:
            path = self.cache_root / "workspace_state.json"
        
        path.parent.mkdir(parents=True, exist_ok=True)
        
        try:
            with self._lock:
                state = {
                    "version": "1.0",
                    "timestamp": time.time(),
                    "resources": {
                        rtype.value: resource.to_dict()
                        for rtype, resource in self._resources.items()
                    },
                }
            
            # Atomic write
            temp_path = path.with_suffix(".tmp")
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(state, f, indent=2, ensure_ascii=False)
            
            os.replace(temp_path, path)
            logger.debug(f"Workspace state saved to {path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save workspace state: {e}")
            return False
    
    def load_state(self, path: Optional[Path] = None) -> bool:
        """
        Load workspace state from a JSON file.
        
        Args:
            path: Optional path (defaults to .cache/workspace_state.json)
            
        Returns:
            True if successful
        """
        if path is None:
            path = self.cache_root / "workspace_state.json"
        
        if not path.exists():
            return False
        
        try:
            with open(path, "r", encoding="utf-8") as f:
                state = json.load(f)
            
            with self._lock:
                for rtype_str, data in state.get("resources", {}).items():
                    try:
                        rtype = ResourceType(rtype_str)
                        resource = WorkspaceResource.from_dict(data)
                        self._resources[rtype] = resource
                    except Exception as e:
                        logger.warning(f"Failed to load resource {rtype_str}: {e}")
            
            logger.debug(f"Workspace state loaded from {path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to load workspace state: {e}")
            return False
    
    def cleanup_temp(self, max_age_hours: int = 24) -> int:
        """
        Clean up temporary assets older than max_age_hours.
        
        Returns:
            Number of files removed
        """
        temp_path = self.get_resource_path(ResourceType.TEMP_ASSETS)
        if not temp_path or not temp_path.exists():
            return 0
        
        removed = 0
        cutoff = time.time() - (max_age_hours * 3600)
        
        try:
            for item in temp_path.rglob("*"):
                if item.is_file():
                    try:
                        if item.stat().st_mtime < cutoff:
                            item.unlink()
                            removed += 1
                    except Exception:
                        pass
            
            # Remove empty directories
            for dirpath in sorted(temp_path.rglob("*"), key=lambda p: len(p.parts), reverse=True):
                if dirpath.is_dir():
                    try:
                        dirpath.rmdir()
                    except Exception:
                        pass
                        
        except Exception as e:
            logger.error(f"Failed to cleanup temp: {e}")
        
        return removed
    
    def clear_resource(self, resource_type: ResourceType) -> bool:
        """Clear a resource (remove files and mark missing)."""
        with self._lock:
            resource = self._resources.get(resource_type)
            if not resource:
                return False
            
            full_path = self.workspace_root / resource.path
            try:
                if full_path.exists():
                    if full_path.is_file():
                        full_path.unlink()
                    else:
                        shutil.rmtree(full_path)
            except Exception as e:
                logger.warning(f"Failed to remove resource files: {e}")
            
            resource.status = ResourceStatus.MISSING
            resource.path = str(self.workspace_root / DEFAULT_RESOURCES[resource_type]["path"])
            resource.metadata.clear()
            return True
    
    def get_workspace_info(self) -> Dict[str, Any]:
        """Get comprehensive workspace information."""
        with self._lock:
            return {
                "workspace_root": str(self.workspace_root),
                "cache_root": str(self.cache_root),
                "plugins_root": str(self.plugins_root),
                "structure_exists": self.workspace_root.exists(),
                "resources": {
                    rtype.value: {
                        "path": resource.path,
                        "status": resource.status.value,
                        "available": resource.is_available,
                        "metadata": resource.metadata,
                    }
                    for rtype, resource in self._resources.items()
                },
                "available_resources": self.get_available_resources(),
            }


# Global instance management
_workspace_manager: Optional[WorkspaceManager] = None
_manager_lock = threading.Lock()


def get_workspace_manager(app_dir: Optional[Path] = None) -> WorkspaceManager:
    """
    Get the global workspace manager instance.
    
    Args:
        app_dir: Optional app directory (only used on first call)
        
    Returns:
        Global WorkspaceManager instance
    """
    global _workspace_manager
    
    with _manager_lock:
        if _workspace_manager is None:
            _workspace_manager = WorkspaceManager(app_dir)
        return _workspace_manager


def reset_workspace_manager():
    """Reset the global workspace manager (for testing)."""
    global _workspace_manager
    with _manager_lock:
        _workspace_manager = None


# ---------------------------------------------------------------------------
# MADRAC Module Integration Helpers
# ---------------------------------------------------------------------------

def register_madrac_subs_resources(workspace: 'WorkspaceManager') -> bool:
    """
    Register MADRAC-SUBS specific resources when integration is detected.
    
    Called when MADRAC-SUBS is detected as available. Registers the resources
    that MADRAC-SUBS can provide/share with other modules.
    
    Args:
        workspace: WorkspaceManager instance
        
    Returns:
        True if registration successful
    """
    from .resources import ResourceType
    
    try:
        # Register MADRAC-SUBS provided resources
        subs_resources = [
            (ResourceType.PARSED_SUBTITLES, "subtitles/parsed/"),
            (ResourceType.SUBTITLE_TIMELINE, "subtitles/timeline.json"),
            (ResourceType.SUBTITLE_SEGMENTS, "subtitles/segments/"),
            (ResourceType.AUDIO_SEGMENTS, "audio_segments/"),
            (ResourceType.EXTRACTED_AUDIO, "audio/extracted/"),
            (ResourceType.REDUCED_VOCALS, "audio/reduced_vocals/"),
            (ResourceType.WHISPER_RESULTS, "whisper/results/"),
            (ResourceType.TRANSCRIPTION_SEGMENTS, "whisper/segments/"),
            (ResourceType.TRANSLATION_CACHE, "translations/cache/"),
            (ResourceType.TRANSLATED_SEGMENTS, "translations/segments/"),
            (ResourceType.PLAYBACK_STATE, "playback/state/current_state.json"),
            (ResourceType.PLAYBACK_POSITION, "playback/position.json"),
        ]
        
        for rtype, path in subs_resources:
            workspace.register_resource(
                rtype,
                path,
                metadata={"provider": "madrac-subs", "description": f"Provided by MADRAC-SUBS: {rtype.value}"},
                status=ResourceStatus.MISSING  # Will be marked available when MADRAC-SUBS publishes
            )
        
        logger.info("Registered MADRAC-SUBS integration resources")
        return True
        
    except Exception as e:
        logger.error(f"Failed to register MADRAC-SUBS resources: {e}")
        return False


def register_madrac_dubbing_resources(workspace: 'WorkspaceManager') -> bool:
    """
    Register MADRAC-DUBBING specific resources.
    
    Called on startup to register resources this module provides.
    """
    from .resources import ResourceType
    
    try:
        dubbing_resources = [
            (ResourceType.TTS_SEGMENTS, "tts/segments/"),
            (ResourceType.MIXED_AUDIO, "audio/mixed/"),
            (ResourceType.DUBBING_JOBS, "dubbing/jobs/"),
            (ResourceType.TTS_CACHE, "tts/cache/"),
            (ResourceType.VOICE_PROFILES, "tts/voices/"),
            (ResourceType.MODEL_WEIGHTS, "models/"),
        ]
        
        for rtype, path in dubbing_resources:
            workspace.register_resource(
                rtype,
                path,
                metadata={"provider": "madrac-dubbing", "description": f"Provided by MADRAC-DUBBING: {rtype.value}"},
                status=ResourceStatus.AVAILABLE
            )
        
        logger.info("Registered MADRAC-DUBBING resources")
        return True
        
    except Exception as e:
        logger.error(f"Failed to register MADRAC-DUBBING resources: {e}")
        return False