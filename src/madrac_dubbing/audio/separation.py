"""
AI Source Separation — Demucs htdemucs_ft.

Separates audio into stems, caches results by xxhash of video.

Usage::

    from madrac_dubbing.audio.separation import separate_stems, has_demucs

    if has_demucs():
        stems = separate_stems("audio.wav")
        # stems.vocals / stems.background / stems.metadata
    else:
        from madrac_dubbing.audio.mixer import reduce_vocals
        audio, sr = reduce_vocals("audio.wav")
"""

import json
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import time

import numpy as np
import soundfile as sf

# ── torch.hub trust ────────────────────────────────────────────────────
# PyTorch >= 2.12 requires explicit trust for non-fork repos.
# Required before any demucs import triggers hub.load() internally.
try:
    import torch
    torch.hub.set_trusted_repo_list(["facebook/demucs:main"])
except Exception:
    pass

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Stem result
# ---------------------------------------------------------------------------

@dataclass
class StemSet:
    """Result of AI source separation."""
    vocals: Path
    background: Path
    metadata: dict = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Video hashing (fast, for cache key)
# ---------------------------------------------------------------------------

_CHUNK_SIZE = 65536  # 64 KB


def hash_video(path: Path) -> str:
    """Compute xxhash64 of first 64 KB + total file size.

    Fast enough to run on every pipeline start.  Collisions are
    astronomically unlikely for caching purposes.
    """
    import xxhash
    x = xxhash.xxh64()
    try:
        with open(path, "rb") as f:
            chunk = f.read(_CHUNK_SIZE)
            x.update(chunk)
    except Exception:
        pass
    x.update(str(path.stat().st_size).encode())
    return x.hexdigest()


# ---------------------------------------------------------------------------
# Stem cache paths (managed by WorkspaceManager)
# ---------------------------------------------------------------------------

def _cache_root() -> Path:
    """Return ``<app_dir>/plugins/audio/stems/`` via workspace manager."""
    try:
        from ..workspace_manager import get_manager
        mgr = get_manager()
        stems_path = mgr.workspace_root / "audio" / "stems"
        stems_path.mkdir(parents=True, exist_ok=True)
        return stems_path
    except Exception:
        from ..utils.paths import APP_DIR
        return APP_DIR / ".cache" / "stems"


def stem_cache_dir(video_hash: str) -> Path:
    """Return the cache directory for a given video hash."""
    d = _cache_root() / video_hash
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_stem_cache(video_hash: str) -> Optional[StemSet]:
    """Return cached ``StemSet`` if it exists, else ``None``."""
    cache_dir = _cache_root() / video_hash
    meta_path = cache_dir / "metadata.json"
    if not meta_path.exists():
        return None
    vocals = cache_dir / "vocals.wav"
    background = cache_dir / "background.wav"
    if not vocals.exists() or not background.exists():
        return None
    try:
        with open(meta_path) as f:
            meta = json.load(f)
    except Exception:
        meta = {}
    return StemSet(vocals=vocals, background=background, metadata=meta)


def save_stem_cache(video_hash: str, stems: StemSet):
    """Persist stems to cache directory."""
    cache_dir = _cache_root() / video_hash
    cache_dir.mkdir(parents=True, exist_ok=True)
    dest_vocals = cache_dir / "vocals.wav"
    dest_background = cache_dir / "background.wav"
    shutil.copy2(stems.vocals, dest_vocals)
    shutil.copy2(stems.background, dest_background)
    with open(cache_dir / "metadata.json", "w") as f:
        json.dump(stems.metadata, f, indent=2, ensure_ascii=False)
    logger.info("Stems cached at %s", cache_dir)


# ---------------------------------------------------------------------------
# Demucs detection
# ---------------------------------------------------------------------------

def has_demucs() -> bool:
    """Check whether Demucs models are accessible (importable + files.txt readable)."""
    try:
        import demucs
        from demucs import pretrained
        pretrained._parse_remote_files(pretrained.REMOTE_ROOT / 'files.txt')
        return True
    except (ImportError, OSError, FileNotFoundError):
        return False


def _resolve_device() -> str:
    """Return ``"cuda"`` or ``"cpu"`` depending on availability."""
    try:
        import torch
        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def separate_stems(
    audio_path: Path,
    device: str = "auto",
    model_name: str = "htdemucs",
    output_dir: Optional[Path] = None,
    video_hash: Optional[str] = None,
) -> StemSet:
    """Separate audio into vocals / background using Demucs.

    Parameters
    ----------
    audio_path:
        Input audio file (WAV recommended).
    device:
        ``"cuda"``, ``"cpu"``, or ``"auto"`` (auto-detect).
    model_name:
        Demucs model (``"htdemucs"`` or ``"htdemucs_ft"``).
        Default is ``"htdemucs"`` (faster, ~same quality).
    output_dir:
        Where to write stems.  If ``None``, uses a temp directory.
    video_hash:
        xxhash of the source video.  If provided and cached stems exist,
        they are returned without re-processing.

    Returns
    -------
    StemSet with paths to ``vocals.wav`` and ``background.wav``.

    Raises
    ------
    ImportError
        If Demucs / PyTorch are not installed.
    FileNotFoundError
        If Demucs fails to produce output files.
    """
    t_start = time.perf_counter()

    if not has_demucs():
        raise ImportError(
            "Demucs is not installed. "
            "Run `python -m madrac_dubbing download-models demucs` "
            "or install manually: pip install demucs torch"
        )

    logger.info("[DEMUCS] available=True  model=%s  device=%s", model_name, device)

    # --- resolve device ---
    if device == "auto":
        device = _resolve_device()

    # --- check cache ---
    cache_hit = False
    if video_hash:
        cached = get_stem_cache(video_hash)
        if cached is not None:
            logger.info("[DEMUCS] cache_hit=True  hash=%s", video_hash[:12])
            # Re-validate cached files still exist
            if cached.vocals.exists() and cached.background.exists():
                v_size = cached.vocals.stat().st_size
                b_size = cached.background.stat().st_size
                logger.info("[DEMUCS] vocals=%s MB  background=%s MB  (from cache)",
                           v_size / 1e6, b_size / 1e6)
                cached.metadata["cache_hit"] = True
                return cached
            else:
                logger.warning("[DEMUCS] cache miss — stems missing on disk, re-processing")

    logger.info("[DEMUCS] cache_hit=False  — processing new separation")

    # --- run Demucs ---
    import torch as _torch
    from demucs import separate as _separate

    # ── Monkey-patch: torchaudio ≥2.9 requires torchcodec (missing FFmpeg DLLs).
    # ── demucs.separate imports `from .audio import save_audio` at module level,
    # ── so we patch the local reference directly.
    import soundfile as _sf
    _original_save = _separate.save_audio
    def _safe_save_audio(wav, path, samplerate, **kwargs):
        import numpy as _np
        arr = wav.cpu().numpy().T if wav.is_cuda else wav.numpy().T
        _sf.write(str(path), arr, samplerate)
        logger.info("[DEMUCS] saved %s (%.1f MB, %d ch, %d Hz)",
                    path, len(arr) / 1e6, arr.shape[1] if arr.ndim > 1 else 1, samplerate)
    _separate.save_audio = _safe_save_audio

    out_dir = output_dir or Path(audio_path).parent / ".stems_tmp"
    out_dir.mkdir(parents=True, exist_ok=True)

    _separate.main([
        "--two-stems", "vocals",
        "-n", model_name,
        "-d", device,
        str(audio_path),
        "-o", str(out_dir),
    ])

    # Restore original
    _separate.save_audio = _original_save

    # Demucs writes to ``out_dir / model_name / <audio_stem>/``
    src_dir = out_dir / model_name / audio_path.stem
    vocals = src_dir / "vocals.wav"
    no_vocals = src_dir / "no_vocals.wav"

    if not no_vocals.exists() and (src_dir / "other.wav").exists():
        background_path = out_dir / "background.wav"
        _merge_background(src_dir, background_path, device)
        bg = background_path
    elif no_vocals.exists():
        bg = no_vocals
    else:
        raise FileNotFoundError(f"[DEMUCS] ERROR — output not found in {src_dir}")

    # ── validation ─────────────────────────────────────────────────────
    errors = []
    if not vocals.exists():
        errors.append(f"vocals.wav missing at {vocals}")
    if not bg.exists():
        errors.append(f"background.wav missing at {bg}")
    if errors:
        raise FileNotFoundError("[DEMUCS] " + "; ".join(errors))

    v_size = vocals.stat().st_size
    b_size = bg.stat().st_size
    v_dur = _get_duration(vocals)
    b_dur = _get_duration(bg)
    t_elapsed = time.perf_counter() - t_start

    logger.info("[DEMUCS] separation_time=%dm%02ds  model=%s  device=%s",
                int(t_elapsed // 60), int(t_elapsed % 60), model_name, device)
    logger.info("[DEMUCS] vocals=%s  %.1f MB  %.1fs",
                vocals.name, v_size / 1e6, v_dur)
    logger.info("[DEMUCS] background=%s  %.1f MB  %.1fs",
                bg.name, b_size / 1e6, b_dur)
    logger.info("[DEMUCS] stems written to %s", bg.parent)

    stems = StemSet(
        vocals=vocals,
        background=bg,
        metadata={
            "model": model_name,
            "device": device,
            "duration_s": round(v_dur, 1),
            "created_at": time.time(),
            "source": str(audio_path),
            "hash": video_hash or "",
            "cache_hit": cache_hit,
            "separation_s": round(t_elapsed, 1),
        },
    )

    if video_hash:
        save_stem_cache(video_hash, stems)

    if output_dir is None:
        try:
            shutil.rmtree(out_dir, ignore_errors=True)
        except Exception:
            pass

    return stems


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _merge_background(src_dir: Path, dest: Path, device: str):
    """Merge non-vocal stems (bass, drums, other) into a single background."""
    import librosa
    stems = []
    target_sr = None
    for name in ("bass", "drums", "other"):
        wav = src_dir / f"{name}.wav"
        if wav.exists():
            data, sr = librosa.load(str(wav), sr=None, mono=False)
            if target_sr is None:
                target_sr = sr
            stems.append(data)
    if not stems:
        raise FileNotFoundError(f"No non-vocal stems found in {src_dir}")
    # Sum and normalize to prevent clipping
    background = np.sum(stems, axis=0)
    peak = np.max(np.abs(background))
    if peak > 1.0:
        background = background / peak * 0.95
    sf.write(str(dest), background.T, target_sr)


def _get_duration(wav_path: Path) -> float:
    """Return audio duration in seconds."""
    try:
        data, sr = sf.read(str(wav_path))
        return len(data) / sr
    except Exception:
        return 0.0


__all__ = [
    "StemSet",
    "separate_stems",
    "has_demucs",
    "hash_video",
    "get_stem_cache",
]
