"""Microsoft Edge TTS Integration"""
import asyncio
import importlib.metadata
import io
from typing import List, Dict, Optional
import logging

from .engine import TTSEngine
from .cache import hash_tts, get_tts_cache, save_tts_cache, TTSCacheStats
from ..pipeline.models import Segment, TTSSegment
from ..utils.audio import get_audio_duration_ms

_EDGE_VERSION = importlib.metadata.version("edge-tts")

try:
    import edge_tts
except ImportError:
    edge_tts = None

logger = logging.getLogger(__name__)

# Index 0 = fallback male, index 1 = fallback female
_FALLBACK_VOICE_MAP: Dict[str, List[str]] = {
    'es': ['es-ES-AlvaroNeural', 'es-ES-ElviraNeural'],
    'en': ['en-US-GuyNeural', 'en-US-JennyNeural'],
    'fr': ['fr-FR-DeniseNeural', 'fr-FR-HenriNeural'],
    'pt': ['pt-BR-AntonioNeural', 'pt-BR-FranciscaNeural'],
    'it': ['it-IT-DiegoNeural', 'it-IT-IsabellaNeural'],
    'de': ['de-DE-ConradNeural', 'de-DE-KatjaNeural'],
    'ja': ['ja-JP-DaichiNeural', 'ja-JP-NanamiNeural'],
    'zh': ['zh-CN-YunxiNeural', 'zh-CN-XiaoxiuNeural'],
    'ru': ['ru-RU-DmitryNeural', 'ru-RU-SvetlanaNeural'],
    'ar': ['ar-EG-SalmaNeural', 'ar-SA-AmmmarNeural'],
}

_FALLBACK_VOICES_BY_GENDER: Dict[str, Dict[str, List[str]]] = {
    lang: {"Male": [v[0]], "Female": [v[1]]} for lang, v in _FALLBACK_VOICE_MAP.items()
}


class EdgeTTSEngine(TTSEngine):
    """Microsoft Edge TTS - free, online, 200+ voices across 50+ languages"""

    def __init__(self):
        if not edge_tts:
            raise ImportError("edge-tts not installed. Run: pip install edge-tts")

        self._fallback_voice_map = dict(_FALLBACK_VOICE_MAP)
        self._cached_voices: Optional[Dict[str, List[str]]] = None
        self._cached_voices_by_gender: Optional[Dict[str, Dict[str, List[str]]]] = None
        self._languages_cache: Optional[List[str]] = None
        self.cache_stats = TTSCacheStats()

    def _fetch_voices_sync(self):
        if self._cached_voices is not None:
            return

        self._cached_voices = {}
        self._cached_voices_by_gender = {}

        loop = asyncio.new_event_loop()
        try:
            voices = loop.run_until_complete(edge_tts.list_voices())
            for v in voices:
                locale = v.get("Locale", "")
                short_lang = locale.split('-')[0].lower() if '-' in locale else locale.lower()
                name = v.get("ShortName", "")
                gender = v.get("Gender", "Female")

                if short_lang not in self._cached_voices:
                    self._cached_voices[short_lang] = []
                    self._cached_voices_by_gender[short_lang] = {"Male": [], "Female": []}
                self._cached_voices[short_lang].append(name)
                self._cached_voices_by_gender[short_lang].setdefault(gender, []).append(name)

            self._languages_cache = list(self._cached_voices.keys())
            logger.info(f"Fetched {len(voices)} voices across {len(self._languages_cache)} languages")
        except Exception as e:
            logger.warning(f"Failed to fetch edge-tts voices dynamically: {e}. Using fallback.")
            self._cached_voices = dict(self._fallback_voice_map)
            self._cached_voices_by_gender = dict(_FALLBACK_VOICES_BY_GENDER)
            self._languages_cache = list(self._fallback_voice_map.keys())
        finally:
            loop.close()

    async def _synthesize_segment_async(self, text: str, voice: str) -> bytes:
        """Generate audio for one segment using edge-tts"""
        try:
            communicate = edge_tts.Communicate(text, voice)
            audio_data = b""
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_data += chunk["data"]
            return audio_data
        except Exception as e:
            logger.error(f"TTS synthesis failed for text '{text[:50]}...': {e}")
            raise

    def _get_voice_for_language(self, language: str, voice_preference: str) -> str:
        """Get appropriate voice ID for language using Gender metadata."""
        self._fetch_voices_sync()

        if language not in self._cached_voices:
            logger.warning(f"Language {language} not found, defaulting to English")
            language = 'en'

        voices = self._cached_voices.get(language, self._fallback_voice_map.get('en', []))
        if not voices:
            return 'en-US-GuyNeural'

        # Exact voice ID match
        if voice_preference in voices:
            return voice_preference

        # Select by gender using real API metadata
        voices_by_gender = self._cached_voices_by_gender.get(language, {}) if self._cached_voices_by_gender else {}

        if voice_preference == "male":
            candidates = voices_by_gender.get("Male", [])
            if candidates:
                return candidates[0]
        elif voice_preference == "female":
            candidates = voices_by_gender.get("Female", [])
            if candidates:
                return candidates[0]
        else:
            # Default to male for neutral/unrecognised preferences
            candidates = voices_by_gender.get("Male", [])
            if candidates:
                return candidates[0]

        logger.warning(
            "No %s voice found for %s in dynamic metadata, using first available",
            voice_preference, language,
        )
        return voices[0]

    def synthesize(self, segments: List[Segment], language: str, voice: str) -> List[TTSSegment]:
        """Generate TTS audio for subtitle segments (cache-aware)."""
        voice_id = self._get_voice_for_language(language, voice)
        results = []
        self.cache_stats = TTSCacheStats()

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

        try:
            for seg in segments:
                h = hash_tts(seg.text, voice_id, language, engine="edge", engine_version=_EDGE_VERSION)
                cached = get_tts_cache(h)

                if cached is not None:
                    self.cache_stats.hits += 1
                    logger.debug(
                        "TTS cache HIT  seg=%(index)d  hash=%(hash)s  text=%(text).40s",
                        {"index": seg.index, "hash": h[:12], "text": seg.text},
                    )
                    results.append(TTSSegment(
                        index=seg.index,
                        text=seg.text,
                        audio_bytes=cached.audio_bytes,
                        duration_ms=cached.duration_ms,
                        start_ms=seg.start_ms,
                        end_ms=seg.end_ms,
                    ))
                    continue

                self.cache_stats.misses += 1
                logger.info(
                    "TTS cache MISS seg=%(index)d  text=%(text).50s...",
                    {"index": seg.index, "text": seg.text},
                )

                audio_bytes = loop.run_until_complete(
                    self._synthesize_segment_async(seg.text, voice_id)
                )

                duration_ms = get_audio_duration_ms(audio_bytes)

                save_tts_cache(h, audio_bytes, duration_ms, {
                    "text": seg.text,
                    "voice": voice_id,
                    "language": language,
                    "engine": "edge",
                    "engine_version": _EDGE_VERSION,
                    "rate": "default",
                    "pitch": "default",
                })

                results.append(TTSSegment(
                    index=seg.index,
                    text=seg.text,
                    audio_bytes=audio_bytes,
                    duration_ms=duration_ms,
                    start_ms=seg.start_ms,
                    end_ms=seg.end_ms,
                ))
        finally:
            loop.close()

        logger.info(
            "TTS synthesis done: %d segments  cache_hits=%d  cache_misses=%d  hit_rate=%.0f%%",
            len(results),
            self.cache_stats.hits,
            self.cache_stats.misses,
            self.cache_stats.hit_rate * 100,
        )

        return results

    def preview_voice(self, language: str, voice_id: str) -> bytes:
        """Generate a short preview audio for the requested voice."""
        preview_texts = {
            'es': "Esta es una vista previa de la voz seleccionada.",
            'en': "This is a preview of the selected voice.",
            'fr': "Ceci est un aperçu de la voix sélectionnée.",
            'pt': "Esta é uma prévia da voz selecionada.",
            'it': "Questa è un'anteprima della voce selezionata.",
            'de': "Dies ist eine Vorschau der ausgewählten Stimme.",
            'ja': "これは選択された声のプレビューです。",
            'zh': "这是所选声音的预览。",
            'ru': "Это предварительный просмотр выбранного голоса.",
            'ar': "هذه معاينة للصوت المحدد."
        }
        text = preview_texts.get(language, "This is a preview of the selected voice.")
        
        # Verify the voice_id actually exists or fallback
        self._fetch_voices_sync()
        if voice_id not in self._cached_voices.get(language, []):
            voice_id = self._get_voice_for_language(language, voice_id)
            
        loop = asyncio.new_event_loop()
        try:
            return loop.run_until_complete(self._synthesize_segment_async(text, voice_id))
        finally:
            loop.close()

    def list_voices(self, language: str) -> List[str]:
        """List available voices for language"""
        self._fetch_voices_sync()
        return self._cached_voices.get(language, [])

    @property
    def supported_languages(self) -> List[str]:
        """Return supported ISO 639-1 language codes"""
        self._fetch_voices_sync()
        return self._languages_cache
