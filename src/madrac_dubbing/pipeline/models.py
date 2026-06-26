"""Data models for dubbing pipeline"""
import json
import os
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional, List
from enum import Enum

MAX_HISTORY = 1000
"""Maximum entries in ``index.json`` to prevent unbounded growth."""


class DubbingStatus(Enum):
    """Status of a dubbing job"""
    PENDING = "pending"
    VALIDATING = "validating"
    EXTRACTING_AUDIO = "extracting_audio"
    GENERATING_TTS = "generating_tts"
    REDUCING_VOCALS = "reducing_vocals"
    MIXING_AUDIO = "mixing_audio"
    EXPORTING = "exporting"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class SyncSegmentReport:
    """Per-segment sync diagnostics."""
    index: int
    start_ms: int
    end_ms: int
    slot_dur_ms: int
    tts_dur_ms: int
    error_ms: int
    error_pct: float
    ratio: float
    action: str  # "ok", "stretched", "truncated", "padded"


@dataclass
class SyncReport:
    """Aggregate sync quality metrics.

    Shared report type — usable by SUBS (subtitle timing quality),
    DUBBING (TTS-to-subtitle sync), and RECO (recognition alignment).
    """
    total_segments: int
    ok_count: int
    stretched_count: int
    truncated_count: int
    padded_count: int
    avg_error_ms: float
    max_error_ms: float
    max_error_pct: float
    drift_ms: int
    segments: List[SyncSegmentReport] = field(default_factory=list)


@dataclass
class DemucsReport:
    """AI source separation diagnostics."""
    model: str = "htdemucs"
    separation_s: float = 0.0
    cache_hit: bool = False


@dataclass
class TTSReport:
    """TTS synthesis diagnostics."""
    engine: str = "edge"
    cache_hits: int = 0
    cache_misses: int = 0
    hit_rate: float = 0.0
    synthesis_s: float = 0.0


@dataclass
class StageTiming:
    """Timing for a single pipeline stage."""
    stage: str
    elapsed_s: float


@dataclass
class PerformanceReport:
    """Pipeline performance and stage timings."""
    stage_timings: List[StageTiming] = field(default_factory=list)


@dataclass
class JobReport:
    """Unified diagnostics report for a dubbing job.

    Designed for MADRAC-CORE compatibility:
      - SUBS can publish SubtitleQualityReport with same pattern
      - RECO can publish RecognitionQualityReport with same pattern
      - ASISTENTE can publish TaskReport with same pattern
    """
    job_id: str = ""
    sync: Optional[SyncReport] = None
    tts: Optional[TTSReport] = None
    demucs: Optional[DemucsReport] = None
    performance: Optional[PerformanceReport] = None

    def to_dict(self) -> dict:
        d = {"job_id": self.job_id}
        for name in ("sync", "tts", "demucs", "performance"):
            report = getattr(self, name)
            if report is not None:
                d[name] = _report_to_dict(report)
        return d


def _report_to_dict(obj) -> dict:
    """Recursively convert a dataclass report to a dict."""
    from dataclasses import fields, is_dataclass
    if is_dataclass(obj):
        result = {}
        for f in fields(obj):
            val = getattr(obj, f.name)
            if isinstance(val, list) and val and is_dataclass(val[0]):
                result[f.name] = [_report_to_dict(v) for v in val]
            elif is_dataclass(val):
                result[f.name] = _report_to_dict(val)
            else:
                result[f.name] = val
        return result
    return obj


@dataclass
class DubbingConfig:
    """Configuration for dubbing job"""
    language: str  # Target language (es, en, fr, pt, etc)
    voice: str = "female"  # Voice ID (female, male, neutral)
    tts_engine: str = "edge"  # edge, elevenlabs, pyttsx3
    reduce_vocals: float = 0.7  # 0.0-1.0
    target_lufs: float = -20.0  # Loudness normalization
    hardcode_subs: bool = False  # Burn subtitles to video
    output_tracks: bool = True  # Export separate tracks in MKV

    def to_dict(self):
        return {
            "language": self.language,
            "voice": self.voice,
            "tts_engine": self.tts_engine,
            "reduce_vocals": self.reduce_vocals,
            "target_lufs": self.target_lufs,
            "hardcode_subs": self.hardcode_subs,
            "output_tracks": self.output_tracks,
        }

    @classmethod
    def from_dict(cls, data: dict):
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})


@dataclass
class DubbingJob:
    """Represents one dubbing task"""
    job_id: str
    video_path: Path
    srt_path: Path
    output_path: Path
    config: DubbingConfig
    status: DubbingStatus = DubbingStatus.PENDING
    progress_pct: int = 0
    message: str = ""
    error: Optional[str] = None
    report: Optional[JobReport] = None

    def __post_init__(self):
        if isinstance(self.video_path, str):
            self.video_path = Path(self.video_path)
        if isinstance(self.srt_path, str):
            self.srt_path = Path(self.srt_path)
        if isinstance(self.output_path, str):
            self.output_path = Path(self.output_path)

    def to_dict(self):
        return {
            "job_id": self.job_id,
            "video_path": str(self.video_path),
            "srt_path": str(self.srt_path),
            "output_path": str(self.output_path),
            "config": self.config.to_dict(),
            "status": self.status.value,
            "progress_pct": self.progress_pct,
            "message": self.message,
            "error": self.error,
        }


@dataclass
class Segment:
    """Subtitle segment"""
    index: int
    start_ms: int
    end_ms: int
    text: str


@dataclass
class TTSSegment:
    """TTS output: audio bytes + timing info"""
    index: int  # Subtitle index
    text: str  # Original text
    audio_bytes: bytes  # WAV audio (16kHz, mono)
    duration_ms: int  # Actual audio duration
    start_ms: int  # Sync to this subtitle start
    end_ms: int  # Subtitle end
