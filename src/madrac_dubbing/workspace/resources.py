"""
Workspace Resource Definitions

Defines the resource types and metadata for the MADRAC Shared Workspace.
"""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Optional
import time


class ResourceType(str, Enum):
    """Types of resources managed by the shared workspace."""
    
    # Project & Session
    CURRENT_PROJECT = "current_project"
    SESSION_STATE = "session_state"
    
    # Subtitles
    PARSED_SUBTITLES = "parsed_subtitles"
    SUBTITLE_TIMELINE = "subtitle_timeline"
    SUBTITLE_SEGMENTS = "subtitle_segments"
    
    # Audio
    AUDIO_SEGMENTS = "audio_segments"
    AUDIO_STEMS = "audio_stems"
    EXTRACTED_AUDIO = "extracted_audio"
    REDUCED_VOCALS = "reduced_vocals"
    TTS_SEGMENTS = "tts_segments"
    MIXED_AUDIO = "mixed_audio"
    
    # Recognition/Transcription
    WHISPER_RESULTS = "whisper_results"
    TRANSCRIPTION_SEGMENTS = "transcription_segments"
    
    # Translation
    TRANSLATION_CACHE = "translation_cache"
    TRANSLATED_SEGMENTS = "translated_segments"
    
    # TTS/Dubbing
    TTS_CACHE = "tts_cache"
    VOICE_PROFILES = "voice_profiles"
    DUBBING_JOBS = "dubbing_jobs"
    
    # Playback
    PLAYBACK_STATE = "playback_state"
    PLAYBACK_POSITION = "playback_position"
    
    # Temporary
    TEMP_ASSETS = "temp_assets"
    
    # Model weights
    MODEL_WEIGHTS = "model_weights"

    # User
    USER_PREFERENCES = "user_preferences"
    VOICE_PREFERENCES = "voice_preferences"


class ResourceStatus(str, Enum):
    """Status of a workspace resource."""
    AVAILABLE = "available"
    OUTDATED = "outdated"
    MISSING = "missing"
    PROCESSING = "processing"
    ERROR = "error"


@dataclass
class WorkspaceResource:
    """
    Represents a single resource in the shared workspace.
    
    Attributes:
        resource_type: Type of resource
        path: Filesystem path (relative to workspace root)
        status: Current availability status
        metadata: Arbitrary metadata (hashes, timestamps, versions, etc.)
        created_at: Creation timestamp
        updated_at: Last update timestamp
        version: Resource version for cache invalidation
    """
    resource_type: ResourceType
    path: str
    status: ResourceStatus = ResourceStatus.MISSING
    metadata: Dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)
    version: str = "1.0"
    
    def __post_init__(self):
        if isinstance(self.resource_type, str):
            self.resource_type = ResourceType(self.resource_type)
        if isinstance(self.status, str):
            self.status = ResourceStatus(self.status)
    
    @property
    def is_available(self) -> bool:
        return self.status == ResourceStatus.AVAILABLE
    
    def mark_available(self, metadata: Optional[Dict[str, Any]] = None):
        """Mark resource as available with optional metadata."""
        self.status = ResourceStatus.AVAILABLE
        self.updated_at = time.time()
        if metadata:
            self.metadata.update(metadata)
    
    def mark_outdated(self, reason: str = ""):
        """Mark resource as outdated."""
        self.status = ResourceStatus.OUTDATED
        self.metadata["outdated_reason"] = reason
        self.updated_at = time.time()
    
    def mark_error(self, error: str):
        """Mark resource as having an error."""
        self.status = ResourceStatus.ERROR
        self.metadata["error"] = error
        self.updated_at = time.time()
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "resource_type": self.resource_type.value,
            "path": self.path,
            "status": self.status.value,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "version": self.version,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "WorkspaceResource":
        return cls(
            resource_type=ResourceType(data["resource_type"]),
            path=data["path"],
            status=ResourceStatus(data.get("status", "missing")),
            metadata=data.get("metadata", {}),
            created_at=data.get("created_at", time.time()),
            updated_at=data.get("updated_at", time.time()),
            version=data.get("version", "1.0"),
        )


# Default resource registry - defines the standard workspace structure
DEFAULT_RESOURCES: Dict[ResourceType, Dict[str, Any]] = {
    ResourceType.CURRENT_PROJECT: {
        "path": "current_project/project.json",
        "description": "Active project metadata and configuration",
    },
    ResourceType.SESSION_STATE: {
        "path": "session_state.json",
        "description": "Current session state for crash recovery",
    },
    ResourceType.PARSED_SUBTITLES: {
        "path": "subtitles/parsed/",
        "description": "Parsed subtitle data (SRT/ASS/VTT)",
    },
    ResourceType.SUBTITLE_TIMELINE: {
        "path": "subtitles/timeline.json",
        "description": "Unified subtitle timeline with timestamps",
    },
    ResourceType.SUBTITLE_SEGMENTS: {
        "path": "subtitles/segments/",
        "description": "Individual subtitle segments with metadata",
    },
    ResourceType.AUDIO_SEGMENTS: {
        "path": "audio_segments/",
        "description": "Pre-cut audio segments for reuse",
    },
    ResourceType.AUDIO_STEMS: {
        "path": "audio/stems/",
        "description": "AI-separated audio stems (vocals, background)",
    },
    ResourceType.EXTRACTED_AUDIO: {
        "path": "audio/extracted/",
        "description": "Full extracted audio tracks from video",
    },
    ResourceType.REDUCED_VOCALS: {
        "path": "audio/reduced_vocals/",
        "description": "Vocal-reduced audio tracks",
    },
    ResourceType.TTS_SEGMENTS: {
        "path": "tts/segments/",
        "description": "Generated TTS audio segments",
    },
    ResourceType.MIXED_AUDIO: {
        "path": "audio/mixed/",
        "description": "Final mixed audio tracks",
    },
    ResourceType.WHISPER_RESULTS: {
        "path": "whisper/results/",
        "description": "Whisper transcription results with segments",
    },
    ResourceType.TRANSCRIPTION_SEGMENTS: {
        "path": "whisper/segments/",
        "description": "Individual transcription segments",
    },
    ResourceType.TRANSLATION_CACHE: {
        "path": "translations/cache/",
        "description": "Cached translations by text+language pair",
    },
    ResourceType.TRANSLATED_SEGMENTS: {
        "path": "translations/segments/",
        "description": "Translated subtitle segments",
    },
    ResourceType.TTS_CACHE: {
        "path": "tts/cache/",
        "description": "TTS audio cache by text+voice+language",
    },
    ResourceType.VOICE_PROFILES: {
        "path": "tts/voices/",
        "description": "User voice profiles and custom voices",
    },
    ResourceType.DUBBING_JOBS: {
        "path": "dubbing/jobs/",
        "description": "Dubbing job queue and history",
    },
    ResourceType.PLAYBACK_STATE: {
        "path": "playback/state/current_state.json",
        "description": "Current playback position and state",
    },
    ResourceType.PLAYBACK_POSITION: {
        "path": "play/position.json",
        "description": "Precise playback position with segment mapping",
    },
    ResourceType.TEMP_ASSETS: {
        "path": "temp/",
        "description": "Temporary working files",
    },
    ResourceType.MODEL_WEIGHTS: {
        "path": "models/",
        "description": "AI model weights (Demucs, Whisper, etc.)",
    },
    ResourceType.USER_PREFERENCES: {
        "path": "user/preferences.json",
        "description": "User preferences and settings",
    },
    ResourceType.VOICE_PREFERENCES: {
        "path": "user/voices.json",
        "description": "User voice selection preferences",
    },
}