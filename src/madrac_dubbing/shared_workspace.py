"""
MADRAC Ecosystem - Shared Workspace Layer

Thin public facade over the real WorkspaceManager in ``workspace/``.
Guarantees backward compatibility with existing imports.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

from .workspace import get_workspace_manager as _get_manager
from .workspace.resources import ResourceType as _ResourceType

logger = logging.getLogger(__name__)


@dataclass
class WorkspaceResource:
    """Describes a single resource type managed by the shared workspace."""
    name: str
    description: str
    available: bool = False
    path: Optional[Path] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SharedWorkspace:
    """Public facade over the real WorkspaceManager.

    Delegates to ``workspace.WorkspaceManager`` under the hood so all
    resources are managed consistently across MADRAC modules.
    """

    base_dir: Optional[Path] = None
    is_available: bool = False

    def __post_init__(self):
        if not self.is_available:
            return
        try:
            self._manager = _get_manager(self.base_dir)
            self._manager.ensure_structure()
            self._resources: Dict[str, WorkspaceResource] = {}
            self._sync_resources()
        except Exception as e:
            logger.warning("SharedWorkspace not available: %s", e)
            self.is_available = False

    def _sync_resources(self):
        """Sync resource view from the real WorkspaceManager."""
        if not self.is_available:
            return
        for rtype, rsrc in self._manager._resources.items():
            wr = WorkspaceResource(
                name=rtype.value,
                description=rsrc.metadata.get("description", ""),
                available=rsrc.is_available,
                path=self._manager.workspace_root / rsrc.path if rsrc.path else None,
                metadata=dict(rsrc.metadata),
            )
            self._resources[rtype.value] = wr

    def get_resource(self, name: str) -> Optional[WorkspaceResource]:
        if not self.is_available:
            return None
        self._sync_resources()
        return self._resources.get(name)

    def available_resources(self) -> List[str]:
        if not self.is_available:
            return []
        self._sync_resources()
        return [r.name for r in self._resources.values() if r.available]

    def all_resources(self) -> List[str]:
        if not self.is_available:
            return []
        self._sync_resources()
        return list(self._resources.keys())

    @property
    def current_project(self) -> Optional[WorkspaceResource]:
        return self.get_resource("current_project")

    @property
    def parsed_subtitles(self) -> Optional[WorkspaceResource]:
        return self.get_resource("parsed_subtitles")

    @property
    def subtitle_timeline(self) -> Optional[WorkspaceResource]:
        return self.get_resource("subtitle_timeline")

    @property
    def audio_segments(self) -> Optional[WorkspaceResource]:
        return self.get_resource("audio_segments")

    @property
    def whisper_results(self) -> Optional[WorkspaceResource]:
        return self.get_resource("whisper_results")

    @property
    def translation_cache(self) -> Optional[WorkspaceResource]:
        return self.get_resource("translation_cache")

    @property
    def playback_state(self) -> Optional[WorkspaceResource]:
        return self.get_resource("playback_state")

    @property
    def temp_assets(self) -> Optional[WorkspaceResource]:
        return self.get_resource("temp_assets")

    @property
    def user_preferences(self) -> Optional[WorkspaceResource]:
        return self.get_resource("user_preferences")

    def publish_resource(self, name: str, path: Path, metadata: Optional[dict] = None):
        if not self.is_available:
            return
        try:
            rtype = _ResourceType(name)
            self._manager.register_resource(
                rtype,
                str(path.relative_to(self._manager.workspace_root))
                if path.is_relative_to(self._manager.workspace_root)
                else str(path),
                metadata=metadata or {},
            )
        except Exception as e:
            logger.warning("publish_resource failed: %s", e)

    def invalidate_resource(self, name: str):
        if not self.is_available:
            return
        try:
            rtype = _ResourceType(name)
            self._manager.mark_resource_outdated(rtype, "invalidated by consumer")
        except Exception as e:
            logger.warning("invalidate_resource failed: %s", e)


workspace = SharedWorkspace(is_available=False)


__all__ = [
    "SharedWorkspace",
    "WorkspaceResource",
    "workspace",
]
