"""
MADRAC Ecosystem - Integration Layer

Capability-based discovery system for the MADRAC module ecosystem.
Detects available MADRAC modules and exposes a central Capabilities object
that the rest of the application consumes.

Detection priority (highest first):
    1. Explicit CLI flags (``--standalone`` / ``--integrated``)
    2. Environment variables (``MADRAC_OPERATING_MODE`` / ``MADRAC_MODE``)
    3. ``WorkspaceManager.discover_modules()``
    4. Legacy filesystem scan (for backward compatibility)
    5. Fallback to standalone

Supported modules:
    - MADRAC-SUBS (M)         → subtitles, subtitle_editor, subtitle_timeline, audio_segments, playback_control
    - MADRAC-ASISTENTE (A)    → assistant, ai_orchestration
    - MADRAC-DUBBING (D)      → dubbing, tts, voice_synthesis
    - MADRAC-RECOGNITION (R)  → recognition, transcription, speaker_id, audio_analysis
    - MADRAC-SUBS-WEB (W)     → web_sync, cloud_projects
"""

import os
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Module registry — maps MADRAC executables to the capabilities they provide
# ---------------------------------------------------------------------------

MODULE_REGISTRY: Dict[str, List[str]] = {
    "madrac-subs.exe": [
        "subtitles",
        "subtitle_editor",
        "subtitle_timeline",
        "audio_segments",
        "playback_control",
        "whisper_models",
        "translation_models",
        "project_management",
    ],
    "madrac-asistente.exe": [
        "assistant",
        "ai_orchestration",
        "workflow_automation",
    ],
    "madrac-dubbing.exe": [
        "dubbing",
        "tts",
        "voice_synthesis",
        "audio_mixing",
    ],
    "madrac-recognition.exe": [
        "recognition",
        "transcription",
        "speaker_id",
        "audio_analysis",
        "voice_activity_detection",
    ],
    "madrac-subs-web.exe": [
        "web_sync",
        "cloud_projects",
        "community_subtitles",
    ],
}


ALL_CAPABILITIES = [
    # M - Subtitle Processing
    "subtitles",
    "subtitle_editor",
    "subtitle_timeline",
    "audio_segments",
    "playback_control",
    "whisper_models",
    "translation_models",
    "project_management",
    # A - AI Assistant
    "assistant",
    "ai_orchestration",
    "workflow_automation",
    # D - Dubbing
    "dubbing",
    "tts",
    "voice_synthesis",
    "audio_mixing",
    # R - Recognition
    "recognition",
    "transcription",
    "speaker_id",
    "audio_analysis",
    "voice_activity_detection",
    # W - Web Sync
    "web_sync",
    "cloud_projects",
    "community_subtitles",
    # Shared / cross-cutting (placeholders for future use)
    "shared_workspace",
    "plugins",
    "projects",
    "playback",
    "events",
    "active_sessions",
]


# ---------------------------------------------------------------------------
# Capabilities dataclass
# ---------------------------------------------------------------------------

@dataclass
class Capabilities:
    """Central capabilities object consumed by the rest of the application.

    Every capability defaults to ``False``.  Populated at startup based on
    detected modules, environment variable overrides, or explicit injection.
    """

    # M - Subtitle Processing
    subtitles: bool = False
    subtitle_editor: bool = False
    subtitle_timeline: bool = False
    audio_segments: bool = False
    playback_control: bool = False
    whisper_models: bool = False
    translation_models: bool = False
    project_management: bool = False

    # A - AI Assistant
    assistant: bool = False
    ai_orchestration: bool = False
    workflow_automation: bool = False

    # D - Dubbing
    dubbing: bool = False
    tts: bool = False
    voice_synthesis: bool = False
    audio_mixing: bool = False

    # R - Recognition
    recognition: bool = False
    transcription: bool = False
    speaker_id: bool = False
    audio_analysis: bool = False
    voice_activity_detection: bool = False

    # W - Web Sync
    web_sync: bool = False
    cloud_projects: bool = False
    community_subtitles: bool = False

    # Shared / cross-cutting placeholders
    shared_workspace: bool = False
    plugins: bool = False
    projects: bool = False
    playback: bool = False
    events: bool = False
    active_sessions: bool = False

    # --- module-level presence flags (convenience) ---
    subs: bool = False
    assistant_app: bool = False
    dubbing_app: bool = False
    recognition_app: bool = False
    subs_web: bool = False

    def to_dict(self) -> dict:
        return {
            "subtitles": self.subtitles,
            "subtitle_editor": self.subtitle_editor,
            "subtitle_timeline": self.subtitle_timeline,
            "audio_segments": self.audio_segments,
            "playback_control": self.playback_control,
            "whisper_models": self.whisper_models,
            "translation_models": self.translation_models,
            "project_management": self.project_management,
            "assistant": self.assistant,
            "ai_orchestration": self.ai_orchestration,
            "workflow_automation": self.workflow_automation,
            "dubbing": self.dubbing,
            "tts": self.tts,
            "voice_synthesis": self.voice_synthesis,
            "audio_mixing": self.audio_mixing,
            "recognition": self.recognition,
            "transcription": self.transcription,
            "speaker_id": self.speaker_id,
            "audio_analysis": self.audio_analysis,
            "voice_activity_detection": self.voice_activity_detection,
            "web_sync": self.web_sync,
            "cloud_projects": self.cloud_projects,
            "community_subtitles": self.community_subtitles,
            "shared_workspace": self.shared_workspace,
            "plugins": self.plugins,
            "projects": self.projects,
            "playback": self.playback,
            "events": self.events,
            "active_sessions": self.active_sessions,
            "subs": self.subs,
            "assistant_app": self.assistant_app,
            "dubbing_app": self.dubbing_app,
            "recognition_app": self.recognition_app,
            "subs_web": self.subs_web,
        }

    def any_integration_available(self) -> bool:
        return any(
            v for k, v in self.to_dict().items()
            if k not in ("subs", "assistant_app", "dubbing_app", "recognition_app", "subs_web")
            and v is True
        )

    def detected_modules(self) -> List[str]:
        modules = []
        if self.subs:
            modules.append("MADRAC-SUBS (M)")
        if self.assistant_app:
            modules.append("MADRAC-ASISTENTE (A)")
        if self.dubbing_app:
            modules.append("MADRAC-DUBBING (D)")
        if self.recognition_app:
            modules.append("MADRAC-RECOGNITION (R)")
        if self.subs_web:
            modules.append("MADRAC-SUBS-WEB (W)")
        return modules


# ---------------------------------------------------------------------------
# Detection helpers
# ---------------------------------------------------------------------------

def _get_app_dir() -> Path:
    from .utils.paths import APP_DIR
    return APP_DIR


def _detect_module(exe_name: str, app_dir: Path) -> bool:
    """Check if a MADRAC module executable exists.

    Priority:
        1. Environment variable override ``MADRAC_CAP_<BASENAME>``
        2. File-system presence in *app_dir*
    """
    env_key = "MADRAC_CAP_" + exe_name.replace("-", "_").replace(".", "_").upper()
    env_val = os.environ.get(env_key)
    if env_val is not None:
        return env_val.lower() == "true"
    return (app_dir / exe_name).exists()


def detect_capabilities(use_workspace_manager: bool = True) -> Capabilities:
    """Scan for MADRAC modules and return a populated ``Capabilities`` object.

    When *use_workspace_manager* is ``True`` (default), detection delegates to
    ``WorkspaceManager.discover_modules()`` for consistency with the rest of
    the ecosystem.  Set to ``False`` to use the legacy filesystem scan (useful
    in tests or CLI scenarios without a full workspace).
    """
    caps = Capabilities()
    app_dir = _get_app_dir()

    # Blanket override (testing convenience)
    if os.environ.get("MADRAC_INTEGRATION_AVAILABLE", "").lower() == "true":
        for cap_name in ALL_CAPABILITIES:
            setattr(caps, cap_name, True)
        caps.subs = True
        caps.assistant_app = True
        caps.dubbing_app = True
        caps.recognition_app = True
        caps.subs_web = True
        caps.shared_workspace = True
        logger.info("Integration forced via MADRAC_INTEGRATION_AVAILABLE")
        return caps

    # Preferred: delegate to WorkspaceManager
    if use_workspace_manager:
        try:
            from .workspace_manager import get_manager
            mgr = get_manager(app_dir)
            result = mgr.discover_modules()
        except Exception:
            result = {}
    else:
        result = {}
        for exe in MODULE_REGISTRY:
            name = exe.replace("madrac-", "").replace("-web", "_web").replace(".exe", "")
            result[name] = _detect_module(exe, app_dir)

    detected_any = False
    for exe_name, cap_keys in MODULE_REGISTRY.items():
        short = exe_name.replace("madrac-", "").replace("-web", "_web").replace(".exe", "")
        present = result.get(short, _detect_module(exe_name, app_dir))
        if present:
            detected_any = True
            logger.debug("Detected module: %s", exe_name)
            for key in cap_keys:
                setattr(caps, key, True)
            if exe_name == "madrac-subs.exe":
                caps.subs = True
            elif exe_name == "madrac-asistente.exe":
                caps.assistant_app = True
            elif exe_name == "madrac-dubbing.exe":
                caps.dubbing_app = True
            elif exe_name == "madrac-recognition.exe":
                caps.recognition_app = True
            elif exe_name == "madrac-subs-web.exe":
                caps.subs_web = True

    if detected_any or caps.any_integration_available():
        caps.shared_workspace = True

    return caps


# ---------------------------------------------------------------------------
# Mode determination
# ---------------------------------------------------------------------------

def determine_mode(
    capabilities: Capabilities,
    cli_mode: Optional[str] = None,
    cli_standalone: bool = False,
    cli_skip_validate: bool = False,
) -> tuple:
    """Determine the operating mode for MADRAC-DUBBING.

    Priority:
        1. Explicit CLI flags (``--standalone`` / ``--integrated``)
        2. Explicit ``--mode`` value
        3. Environment variables ``MADRAC_OPERATING_MODE`` / ``MADRAC_MODE``
        4. Auto-detection from *capabilities*
        5. Fallback to ``'standalone'``

    Returns ``(mode, skip_validation)``.
    """
    skip_validation = cli_skip_validate

    if cli_standalone or cli_skip_validate:
        return "standalone", skip_validation

    if cli_mode:
        mode = cli_mode.lower()
        if mode in ("standalone", "integrated"):
            return mode, skip_validation
        logger.warning("Unknown --mode value '%s', falling back to auto-detect", cli_mode)

    env_mode = os.environ.get("MADRAC_OPERATING_MODE") or os.environ.get("MADRAC_MODE")
    if env_mode:
        mode = env_mode.lower()
        if mode in ("standalone", "integrated"):
            return mode, skip_validation

    if capabilities.any_integration_available():
        return "integrated", skip_validation

    return "standalone", skip_validation


# ---------------------------------------------------------------------------
# Public API — singleton-like access
# ---------------------------------------------------------------------------

capabilities: Capabilities = detect_capabilities()
current_mode: str = "standalone"
skip_validation: bool = False


def reload_capabilities():
    global capabilities
    capabilities = detect_capabilities()


def set_mode(mode: str, skip: bool = False):
    global current_mode, skip_validation
    current_mode = mode
    skip_validation = skip


__all__ = [
    "Capabilities",
    "capabilities",
    "current_mode",
    "skip_validation",
    "detect_capabilities",
    "determine_mode",
    "reload_capabilities",
    "set_mode",
    "MODULE_REGISTRY",
    "ALL_CAPABILITIES",
]
