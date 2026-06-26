"""
MADRAC Shared Workspace Layer

Centralized workspace management for all MADRAC modules (M, A, D, R, WEB).
Provides a unified filesystem-based workspace rooted at APP_DIR.
"""

from .manager import WorkspaceManager, get_workspace_manager
from .resources import WorkspaceResource, ResourceType, ResourceStatus

__all__ = [
    "WorkspaceManager",
    "get_workspace_manager",
    "WorkspaceResource",
    "ResourceType",
    "ResourceStatus",
]