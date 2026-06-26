"""Abstract TTS engine interface"""
from abc import ABC, abstractmethod
from typing import List
from dataclasses import dataclass
from ..pipeline.models import Segment, TTSSegment


@dataclass
class TTSSegment:
    """TTS output with timing and audio"""
    index: int
    text: str
    audio_bytes: bytes
    duration_ms: int
    start_ms: int
    end_ms: int


class TTSEngine(ABC):
    """Abstract TTS engine interface"""

    @abstractmethod
    def synthesize(self, segments: List[Segment], language: str, voice: str) -> List[TTSSegment]:
        """Generate TTS audio for subtitle segments"""
        pass

    @abstractmethod
    def list_voices(self, language: str) -> List[str]:
        """List available voices for language"""
        pass

    @property
    @abstractmethod
    def supported_languages(self) -> List[str]:
        """Return list of supported ISO 639-1 language codes"""
        pass
