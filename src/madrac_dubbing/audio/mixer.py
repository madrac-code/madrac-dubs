"""Audio processing: mixing, vocal reduction, synchronization"""
import io
import logging
from pathlib import Path
from typing import Tuple, List

import numpy as np
import soundfile as sf

try:
    from scipy.signal import butter, sosfilt
    import librosa
    import pyloudnorm
except ImportError as e:
    logging.warning(f"Some audio libraries not available: {e}")

from ..pipeline.models import SyncReport, SyncSegmentReport

logger = logging.getLogger(__name__)


def reduce_vocals(audio_path: Path, reduction_factor: float = 0.7) -> Tuple[np.ndarray, int]:
    """
    LEGACY FALLBACK — DSP-based vocal attenuation.

    Used when AI source separation (Demucs) is unavailable.
    Attenuates centre-panned content + bandpass filter.
    NOT suitable for professional dubbing; use ``separate_stems()`` instead.

    Args:
        audio_path: Input audio file
        reduction_factor: 0.0 (no reduction) to 1.0 (full removal)

    Returns:
        Tuple of (reduced audio array, sample rate)
    """
    logger.info("LEGACY reduce_vocals (DSP fallback) factor=%s", reduction_factor)
    audio, sr = sf.read(str(audio_path))

    if len(audio.shape) == 2 and audio.shape[1] == 2:
        L, R = audio[:, 0], audio[:, 1]
        center = (L + R) / 2
        audio_reduced = np.column_stack([L - center, R - center])
    else:
        audio_reduced = audio

    sos = butter(4, [100, 10000], btype='band', fs=sr, output='sos')
    if len(audio_reduced.shape) == 2:
        audio_filtered = np.column_stack([
            sosfilt(sos, audio_reduced[:, 0]),
            sosfilt(sos, audio_reduced[:, 1])
        ])
    else:
        audio_filtered = sosfilt(sos, audio_reduced)

    audio_output = audio * (1 - reduction_factor) + audio_filtered * reduction_factor

    return audio_output, sr


STRETCH_MIN = 0.85
STRETCH_MAX = 1.15
_OK_RATIO_LOW = 0.97    # ratios within [0.97, 1.03] → no audible stretch
_OK_RATIO_HIGH = 1.03


def sync_tts_to_subtitle(tts_segments, target_sr: int = 44100) -> Tuple[np.ndarray, int, SyncReport]:
    """
    Align TTS audio to subtitle timing using an absolute timeline (DAW-style).

    Each TTS segment is placed at its exact ``start_ms`` position from the SRT,
    eliminating cumulative drift.  Overlapping segments are summed (controlled
    overlap) and the final mix is peak-normalised to prevent clipping.

    Time-stretching is limited to the ``[STRETCH_MIN, STRETCH_MAX]`` range.
    Outside that range the audio is either truncated (TTS too long) or padded
    with trailing silence (TTS too short).

    Returns:
        Tuple of (output_audio, sample_rate, SyncReport)
    """
    if not tts_segments:
        return np.array([]), target_sr, SyncReport(total_segments=0, ok_count=0,
                    stretched_count=0, truncated_count=0, padded_count=0,
                    avg_error_ms=0.0, max_error_ms=0, max_error_pct=0.0, drift_ms=0)

    logger.info(f"Syncing {len(tts_segments)} TTS segments — absolute timeline @ {target_sr} Hz")

    # ── allocate blank timeline ──────────────────────────────────────────
    total_ms = max(seg.end_ms for seg in tts_segments) + 2000  # 2 s headroom
    total_samples = int(total_ms / 1000 * target_sr)
    output = np.zeros(total_samples, dtype=np.float64)

    # ── segment diagnostics ──────────────────────────────────────────────
    seg_reports: List[SyncSegmentReport] = []
    total_drift_ms = 0

    for seg in tts_segments:
        # read audio – sr is guaranteed to match by earlier conversion
        tts_audio, sr = sf.read(io.BytesIO(seg.audio_bytes))
        if sr != target_sr:
            tts_audio = librosa.resample(tts_audio, orig_sr=sr, target_sr=target_sr)

        tts_duration_ms = len(tts_audio) / target_sr * 1000
        original_duration_ms = tts_duration_ms
        subtitle_duration_ms = seg.end_ms - seg.start_ms
        ratio = subtitle_duration_ms / tts_duration_ms if tts_duration_ms > 0 else 1.0

        error_ms = int(tts_duration_ms - subtitle_duration_ms)
        error_pct = round(abs(error_ms) / subtitle_duration_ms * 100, 1) if subtitle_duration_ms > 0 else 0

        # ── time-stretch within safe limits ──────────────────────────────
        if _OK_RATIO_LOW <= ratio <= _OK_RATIO_HIGH:
            action = "ok"
            tts_duration_ms = subtitle_duration_ms
        elif STRETCH_MIN <= ratio <= STRETCH_MAX:
            tts_audio = librosa.effects.time_stretch(tts_audio, rate=ratio)
            tts_duration_ms = subtitle_duration_ms
            action = "stretched"
        elif ratio > STRETCH_MAX:
            action = "padded"
            logger.warning(
                "Segment %d: original TTS %.0f ms fits in %.0f ms subtitle slot "
                "(ratio=%.2f > %.2f) — padding with silence",
                seg.index, original_duration_ms, subtitle_duration_ms, ratio, STRETCH_MAX,
            )
        else:
            action = "truncated"
            max_samples = int(subtitle_duration_ms / 1000 * target_sr)
            tts_audio = tts_audio[:max_samples]
            logger.warning(
                "Segment %d: original TTS %.0f ms exceeds subtitle slot %.0f ms "
                "(ratio=%.2f < %.2f) — truncating to %.0f ms",
                seg.index, original_duration_ms, subtitle_duration_ms,
                ratio, STRETCH_MIN, subtitle_duration_ms,
            )
            tts_duration_ms = subtitle_duration_ms

        total_drift_ms += max(0, error_ms)

        # ── place at absolute position (DAW-style) ───────────────────────
        start_sample = int(seg.start_ms / 1000 * target_sr)
        num_samples = len(tts_audio)
        if start_sample + num_samples > len(output):
            num_samples = len(output) - start_sample
            tts_audio = tts_audio[:num_samples]

        output[start_sample:start_sample + num_samples] += tts_audio

        seg_reports.append(SyncSegmentReport(
            index=seg.index,
            start_ms=seg.start_ms,
            end_ms=seg.end_ms,
            slot_dur_ms=subtitle_duration_ms,
            tts_dur_ms=int(original_duration_ms),
            error_ms=error_ms,
            error_pct=error_pct,
            ratio=round(ratio, 3),
            action=action,
        ))

    # ── normalise peak to prevent clipping ───────────────────────────────
    peak = np.max(np.abs(output))
    if peak > 0.99:
        gain = 0.95 / peak
        logger.info("Peak %.3f exceeds 0.99 – normalising by %.3f", peak, gain)
        output *= gain

    # ── build report ─────────────────────────────────────────────────────
    ok_count = sum(1 for s in seg_reports if s.action == "ok")
    stretched_count = sum(1 for s in seg_reports if s.action == "stretched")
    truncated_count = sum(1 for s in seg_reports if s.action == "truncated")
    padded_count = sum(1 for s in seg_reports if s.action == "padded")
    errors = [abs(s.error_ms) for s in seg_reports]
    avg_error_ms = round(sum(errors) / len(errors), 1) if errors else 0.0
    max_error = max(errors) if errors else 0
    max_pct = max((s.error_pct for s in seg_reports), default=0.0)

    report = SyncReport(
        total_segments=len(seg_reports),
        ok_count=ok_count,
        stretched_count=stretched_count,
        truncated_count=truncated_count,
        padded_count=padded_count,
        avg_error_ms=avg_error_ms,
        max_error_ms=max_error,
        max_error_pct=max_pct,
        drift_ms=total_drift_ms,
        segments=seg_reports,
    )

    # ── diagnostic log ───────────────────────────────────────────────────
    logger.info("── TTS sync diagnostics ──")
    for s in seg_reports:
        logger.info(
            "  seg=%(index)-3d  start=%(start_ms)6d  end=%(end_ms)6d  "
            "slot=%(slot_dur_ms)5d  tts=%(tts_dur_ms)5d  error=%(error_ms)+5dms  "
            "action=%(action)-10s",
            s.__dict__,
        )
    logger.info(
        "Sync summary: %d total  %d ok  %d stretched  %d truncated  %d padded  "
        "avg_err=%.0fms  max_err=%dms  drift=%dms",
        report.total_segments, ok_count, stretched_count, truncated_count, padded_count,
        avg_error_ms, max_error, total_drift_ms,
    )

    return output, target_sr, report


def normalize_loudness(audio: np.ndarray, sr: int, target_lufs: float = -20.0) -> np.ndarray:
    """Normalize audio loudness to target LUFS"""
    logger.info(f"Normalizing loudness to {target_lufs} LUFS")
    try:
        from pyloudnorm import Meter
        meter = Meter(sr)
        loudness = meter.integrated_loudness(audio)

        if loudness < -100:
            logger.warning("Audio is silent, skipping normalization")
            return audio

        loudness_normalized = pyloudnorm.normalize.loudness(audio, loudness, target_lufs)
        return loudness_normalized
    except Exception as e:
        logger.error(f"Loudness normalization failed: {e}")
        return audio


def _match_channels(a: np.ndarray, b: np.ndarray) -> Tuple[np.ndarray, np.ndarray]:
    """Match channel counts between two arrays for arithmetic operations."""
    if a.ndim == 1 and b.ndim == 1:
        return a, b

    a_flat = a.reshape(-1, a.shape[-1]) if a.ndim > 1 else a
    b_flat = b.reshape(-1, b.shape[-1]) if b.ndim > 1 else b

    if a_flat.ndim == 1 and b_flat.ndim == 2:
        a_flat = np.column_stack([a_flat, a_flat])
    elif a_flat.ndim == 2 and b_flat.ndim == 1:
        b_flat = np.column_stack([b_flat, b_flat])

    return a_flat, b_flat


def mix_audio_tracks(
    reduced_original: np.ndarray,
    dubbed_tts: np.ndarray,
    sr: int,
    mix_ratio: float = 0.3
) -> np.ndarray:
    """
    Mix reduced original audio with dubbed TTS.

    Args:
        reduced_original: Original audio with reduced vocals
        dubbed_tts: Dubbed TTS audio
        sr: Sample rate
        mix_ratio: Weight of original audio (0.0-1.0)

    Returns:
        Mixed audio array
    """
    logger.info(f"Mixing audio with ratio {mix_ratio} original / {1-mix_ratio} dubbed")

    original, tts = _match_channels(reduced_original, dubbed_tts)

    min_length = min(len(original), len(tts))
    final_audio = (original[:min_length] * mix_ratio +
                   tts[:min_length] * (1 - mix_ratio))

    return final_audio
