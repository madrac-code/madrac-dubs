"""TTS Cache: hash-based persistent cache for synthesized speech.

Design (MADRAC-CORE compatible):
  - Hash includes engine, voice, language, text, rate, pitch
  - Flat file layout:  plugins/tts/cache/<hash>.wav  +  <hash>.json
  - Same pattern as separation.py stem cache
  - Cache keys are globally unique (xxhash of all parameters)

Future:
  - Multiple TTS engines share the same cache (Edge, ElevenLabs, Piper, etc.)
  - SUBS / DUBBING / RECO / ASISTENTE all read from the same pool
"""
import json
import logging
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class TTSCacheEntry:
    audio_bytes: bytes
    duration_ms: int
    metadata: dict = field(default_factory=dict)


@dataclass
class TTSCacheStats:
    hits: int = 0
    misses: int = 0

    @property
    def total(self) -> int:
        return self.hits + self.misses

    @property
    def hit_rate(self) -> float:
        if self.total == 0:
            return 0.0
        return self.hits / self.total


def hash_tts(
    text: str,
    voice: str,
    language: str,
    engine: str = "edge",
    engine_version: str = "",
    rate: str = "default",
    pitch: str = "default",
) -> str:
    """Deterministic xxhash64 key for a TTS request.

    All parameters that affect the output audio must be included so
    that a change in any one of them produces a different cache key.
    ``engine_version`` ensures cache invalidation when the TTS engine
    is updated (e.g. edge-tts 7.0 → 8.0).
    """
    import xxhash

    x = xxhash.xxh64()
    parts = [engine, engine_version, voice, language, text, rate, pitch]
    for part in parts:
        x.update(part.encode("utf-8"))
    return x.hexdigest()


def _tts_cache_root() -> Path:
    """Return ``<app_dir>/plugins/tts/cache/`` via workspace manager."""
    try:
        from ..workspace_manager import get_manager

        mgr = get_manager()
        cache_dir = mgr.workspace_root / "tts" / "cache"
        cache_dir.mkdir(parents=True, exist_ok=True)
        return cache_dir
    except Exception:
        pass

    from ..utils.paths import APP_DIR

    fallback = APP_DIR / ".cache" / "tts"
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback


def _hash_path(h: str) -> tuple[Path, Path]:
    """Return (wav_path, json_path) for a given hash."""
    root = _tts_cache_root()
    return root / f"{h}.wav", root / f"{h}.json"


def get_tts_cache(hash_key: str) -> Optional[TTSCacheEntry]:
    """Return cached TTS audio if available."""
    wav_path, json_path = _hash_path(hash_key)
    if not wav_path.exists() or not json_path.exists():
        return None
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            meta = json.load(f)
        audio_bytes = wav_path.read_bytes()
        duration_ms = meta.get("duration_ms", 0)
        logger.debug("TTS cache HIT  hash=%s  text=%.40s", hash_key[:12], meta.get("text", ""))
        return TTSCacheEntry(
            audio_bytes=audio_bytes,
            duration_ms=duration_ms,
            metadata=meta,
        )
    except Exception as e:
        logger.warning("TTS cache read error for %s: %s", hash_key[:12], e)
        return None


def save_tts_cache(hash_key: str, audio_bytes: bytes, duration_ms: int, metadata: dict) -> None:
    """Persist TTS audio and metadata to cache."""
    wav_path, json_path = _hash_path(hash_key)
    wav_path.parent.mkdir(parents=True, exist_ok=True)
    meta = dict(metadata)
    meta["duration_ms"] = duration_ms
    meta["cached_at"] = time.time()
    try:
        wav_path.write_bytes(audio_bytes)
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2, ensure_ascii=False)
        logger.info("TTS cache SAVE hash=%s  text=%.40s", hash_key[:12], meta.get("text", ""))
    except Exception as e:
        logger.warning("TTS cache write error for %s: %s", hash_key[:12], e)


def clear_tts_cache() -> int:
    """Remove all cached TTS entries.  Returns number of files removed."""
    root = _tts_cache_root()
    count = 0
    for f in root.iterdir():
        if f.suffix in (".wav", ".json"):
            f.unlink()
            count += 1
    logger.info("TTS cache cleared: %d files removed from %s", count, root)
    return count
