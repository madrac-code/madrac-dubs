"""
Validation script — full dubbing pipeline test with sync metrics.

Usage:
    python validate_sync.py

Output:
    - plugins/validation/<timestamp>/    (stems + report)
    - plugins/validation/<timestamp>/report.json
"""

import json
import logging
import shutil
import sys
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import List, Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    stream=sys.stdout,
)
logger = logging.getLogger("validate")


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------

@dataclass
class SegmentSyncMetric:
    index: int
    start_ms: int
    end_ms: int
    slot_dur_ms: int
    tts_dur_ms: int
    ratio: float
    stretch: str
    error_ms: int            # |tts_dur - slot_dur|
    error_pct: float         # error / slot_dur * 100
    overlapped: bool = False # tts overflows into next slot


@dataclass
class PipelineStageTiming:
    stage: str
    elapsed_s: float


@dataclass
class SyncReport:
    video: str
    video_duration_s: float
    total_segments: int
    avg_error_ms: float
    avg_error_pct: float
    max_error_ms: int
    max_error_pct: float
    total_drift_ms: float
    overlap_count: int
    overlap_pct: float
    segments: List[dict]
    stage_timings: List[dict] = field(default_factory=list)
    cache_hit: bool = False
    model: str = ""
    separation_s: float = 0.0

    def to_dict(self):
        return {
            "video": self.video,
            "video_duration_s": self.video_duration_s,
            "total_segments": self.total_segments,
            "avg_error_ms": round(self.avg_error_ms, 1),
            "avg_error_pct": round(self.avg_error_pct, 1),
            "max_error_ms": self.max_error_ms,
            "max_error_pct": round(self.max_error_pct, 1),
            "total_drift_ms": round(self.total_drift_ms, 1),
            "overlap_count": self.overlap_count,
            "overlap_pct": round(self.overlap_pct, 1),
            "cache_hit": self.cache_hit,
            "model": self.model,
            "separation_s": round(self.separation_s, 1),
            "segments": self.segments,
            "stage_timings": self.stage_timings,
        }


# ---------------------------------------------------------------------------
# Log parser
# ---------------------------------------------------------------------------




# ---------------------------------------------------------------------------
# Runner
# ---------------------------------------------------------------------------

def main():
    import soundfile as sf
    test_dir = Path(r"D:\madrac-dubs\test_media")
    video_path = test_dir / "synthetic_3min.mp4"
    srt_path = test_dir / "synthetic_3min.srt"

    if not video_path.exists() or not srt_path.exists():
        logger.error("Test media not found. Run media creation first.")
        return

    # Output dir — preserved for inspection
    ts = time.strftime("%Y%m%d_%H%M%S")
    out_dir = Path(r"D:\madrac-dubs\plugins\validation") / ts
    out_dir.mkdir(parents=True, exist_ok=True)
    stems_out = out_dir / "stems"
    stems_out.mkdir(parents=True, exist_ok=True)

    logger.info("=" * 60)
    logger.info("VALIDATION RUN — %s", ts)
    logger.info("  video: %s", video_path)
    logger.info("  srt:   %s", srt_path)
    logger.info("  out:   %s", out_dir)
    logger.info("=" * 60)

    # ------------------------------------------------------------------
    # Stage timing
    # ------------------------------------------------------------------
    stage_times: List[PipelineStageTiming] = []
    t_last = time.perf_counter()

    def mark_stage(name: str):
        nonlocal t_last
        now = time.perf_counter()
        stage_times.append(PipelineStageTiming(stage=name, elapsed_s=round(now - t_last, 3)))
        t_last = now
        logger.info("[STAGE] %s  (%.3fs)", name, stage_times[-1].elapsed_s)

    def capture_log(msg: str):
        pass  # not needed; we use direct data

    # ------------------------------------------------------------------
    # Run pipeline
    # ------------------------------------------------------------------
    from madrac_dubbing.pipeline.models import DubbingJob, DubbingConfig, DubbingStatus
    from madrac_dubbing.pipeline.dubbing_pipeline import DubbingPipeline
    from madrac_dubbing.audio.separation import hash_video

    config = DubbingConfig(
        language="es",
        voice="female",
        tts_engine="edge",
        reduce_vocals=0.7,
        target_lufs=-20.0,
    )

    job = DubbingJob(
        job_id="validation-run",
        video_path=video_path,
        srt_path=srt_path,
        output_path=out_dir / "dubbed_output.mp4",
        config=config,
    )

    def on_progress(j):
        pass  # we track via stages

    import tempfile

    pipeline = DubbingPipeline(on_progress=on_progress, on_log=capture_log)
    pipeline.temp_dir = Path(tempfile.mkdtemp(prefix="madrac_val_"))
    mark_stage("tts_engine_init")  # EdgeTTSEngine.__init__ fetches 322 voices

    job.status = DubbingStatus.VALIDATING
    pipeline._validate_inputs(job)
    mark_stage("extract_audio")

    job.status = DubbingStatus.EXTRACTING_AUDIO
    from madrac_dubbing.utils.ffmpeg import extract_audio
    original_audio_path = pipeline.temp_dir / "original_audio.wav"
    extract_audio(job.video_path, original_audio_path)
    mark_stage("parse_srt")

    job.status = DubbingStatus.GENERATING_TTS
    from madrac_dubbing.utils.audio import parse_srt_file
    subtitles = parse_srt_file(job.srt_path)
    logger.info("Parsed %d subtitles", len(subtitles))
    mark_stage("tts_synthesis")

    tts_segments = pipeline.tts_engine.synthesize(
        subtitles,
        job.config.language,
        job.config.voice
    )
    mark_stage("separate_stems")

    # ── AI source separation ──────────────────────────────────────────
    from madrac_dubbing.audio.separation import separate_stems, has_demucs

    stems = None
    if has_demucs():
        video_hash = hash_video(job.video_path)
        t0 = time.perf_counter()
        stems = separate_stems(original_audio_path, video_hash=video_hash)
        t_sep = time.perf_counter() - t0
        background_path = stems.background
        logger.info("[DEMUCS] separation_time=%dm%02ds  model=%s",
                    int(t_sep // 60), int(t_sep % 60),
                    stems.metadata.get("model", "?"))
        logger.info("[DEMUCS] vocals=%s  background=%s", stems.vocals, stems.background)

        # ── Preserve stems from CACHE (temp was cleaned by separate_stems) ──
        from madrac_dubbing.audio.separation import get_stem_cache
        cached = get_stem_cache(video_hash)
        if cached:
            cache_dir = cached.vocals.parent
            logger.info("[VALIDATE] Copying stems from cache: %s", cache_dir)
            if cache_dir.exists():
                for f in cache_dir.iterdir():
                    if f.is_file():
                        shutil.copy2(str(f), str(stems_out / f.name))
        # Also copy from temp if still there (race condition guard)
        if stems.vocals.parent.exists():
            for f in stems.vocals.parent.iterdir():
                if f.is_file() and not (stems_out / f.name).exists():
                    shutil.copy2(str(f), str(stems_out / f.name))
        logger.info("[VALIDATE] Stems preserved to %s", stems_out)

        # Use cached stems for background
        if cached and cached.background.exists():
            background_path = cached.background
        elif stems.background.exists():
            background_path = stems.background
    else:
        logger.warning("Demucs not available, using DSP fallback")
        from madrac_dubbing.audio.mixer import reduce_vocals
        bg_path = pipeline.temp_dir / "legacy_background.wav"
        reduced_arr, sr = reduce_vocals(original_audio_path, job.config.reduce_vocals)
        sf.write(str(bg_path), reduced_arr, sr)
        background_path = bg_path
        stems = None

    mark_stage("sync_tts")

    # ── Sync to subtitle timeline ─────────────────────────────────────
    background_audio, sr = sf.read(str(background_path))
    from madrac_dubbing.audio.mixer import sync_tts_to_subtitle
    dubbed_audio, sr = sync_tts_to_subtitle(tts_segments, sr)
    mark_stage("normalize")

    from madrac_dubbing.audio.mixer import normalize_loudness
    dubbed_audio = normalize_loudness(dubbed_audio, sr, job.config.target_lufs)
    mark_stage("mix")

    from madrac_dubbing.audio.mixer import mix_audio_tracks
    final_audio = mix_audio_tracks(background_audio, dubbed_audio, sr, mix_ratio=0.3)
    dubbed_audio_path = pipeline.temp_dir / "dubbed_audio.wav"
    sf.write(str(dubbed_audio_path), final_audio, sr)
    mark_stage("export")

    from madrac_dubbing.utils.ffmpeg import mux_audio_to_video
    job.output_path.parent.mkdir(parents=True, exist_ok=True)
    mux_audio_to_video(job.video_path, dubbed_audio_path, job.output_path)
    mark_stage("done")

    # ------------------------------------------------------------------
    # Compute sync metrics directly from TTS segments & subtitle slots
    # ------------------------------------------------------------------
    logger.info("")
    logger.info("=" * 60)
    logger.info("SYNC METRICS ANALYSIS — from TTS segment data")
    logger.info("=" * 60)

    segments: List[SegmentSyncMetric] = []
    for seg in tts_segments:
        slot_ms = seg.end_ms - seg.start_ms
        tts_ms = seg.duration_ms
        ratio = tts_ms / slot_ms if slot_ms > 0 else 1.0
        error_ms = abs(tts_ms - slot_ms)
        error_pct = (error_ms / slot_ms * 100) if slot_ms > 0 else 0

        segments.append(SegmentSyncMetric(
            index=seg.index,
            start_ms=seg.start_ms,
            end_ms=seg.end_ms,
            slot_dur_ms=slot_ms,
            tts_dur_ms=tts_ms,
            ratio=ratio,
            stretch="",
            error_ms=error_ms,
            error_pct=error_pct,
        ))

    # Detect overlaps: TTS duration > slot duration and the next segment starts
    # before this segment's TTS would end
    for i, seg in enumerate(segments):
        if i + 1 < len(segments):
            next_start = segments[i + 1].start_ms
            tts_end = seg.start_ms + seg.tts_dur_ms
            if tts_end > next_start:
                seg.overlapped = True

    total_segments = len(segments)
    errors_ms = [s.error_ms for s in segments]
    errors_pct = [s.error_pct for s in segments]
    overlaps = [s for s in segments if s.overlapped]

    # Compute drift: cumulative sum of (tts_dur_ms - slot_dur_ms)
    drift_values = [(s.tts_dur_ms - s.slot_dur_ms) for s in segments]
    total_drift = sum(drift_values)

    report = SyncReport(
        video=video_path.name,
        video_duration_s=180.0,
        total_segments=total_segments,
        avg_error_ms=sum(errors_ms) / len(errors_ms),
        avg_error_pct=sum(errors_pct) / len(errors_pct),
        max_error_ms=max(errors_ms),
        max_error_pct=max(errors_pct),
        total_drift_ms=total_drift,
        overlap_count=len(overlaps),
        overlap_pct=len(overlaps) / total_segments * 100,
        segments=[asdict(s) for s in segments],
        stage_timings=[asdict(t) for t in stage_times],
    )

    if stems is not None:
        report.cache_hit = stems.metadata.get("cache_hit", False)
        report.model = stems.metadata.get("model", "")
        report.separation_s = stems.metadata.get("separation_s", 0.0)

    # ── Print report ──────────────────────────────────────────────────
    logger.info("")
    logger.info("  Segments analyzed:    %d", report.total_segments)
    logger.info("  Avg sync error:       %.1f ms  (%.1f%%)",
                report.avg_error_ms, report.avg_error_pct)
    logger.info("  Max sync error:       %d ms  (%.1f%%)",
                report.max_error_ms, report.max_error_pct)
    logger.info("  Total drift:          %.1f ms", report.total_drift_ms)
    logger.info("  Overlaps:             %d / %d  (%.1f%%)",
                report.overlap_count, report.total_segments, report.overlap_pct)
    logger.info("  Cache hit:            %s", report.cache_hit)
    logger.info("  Separation model:     %s", report.model)
    logger.info("  Separation time:      %.1f s", report.separation_s)
    logger.info("")
    logger.info("  ── Pipeline stage timings ──")

    total_elapsed = 0.0
    for st in stage_times:
        logger.info("    %-20s  %.3fs", st.stage, st.elapsed_s)
        total_elapsed += st.elapsed_s
    logger.info("    %-20s  %.3fs", "TOTAL", total_elapsed)
    logger.info("")

    # ── Detailed per-segment table ──
    logger.info("  ── Per-segment breakdown ──")
    logger.info("  %4s | %6s | %6s | %5s | %5s | %7s | %8s | %s",
                "Seg", "Start", "End", "Slot", "TTS", "Err ms", "Err %", "Overlap")
    logger.info("  " + "-" * 70)
    for s in segments:
        logger.info("  %4d | %6d | %6d | %5d | %5d | %7d | %7.1f%% | %s",
                    s.index, s.start_ms, s.end_ms, s.slot_dur_ms,
                    s.tts_dur_ms, s.error_ms, s.error_pct,
                    "YES" if s.overlapped else "no")

    # ── Save report ───────────────────────────────────────────────────
    report_path = out_dir / "report.json"
    report_path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    logger.info("")
    logger.info("Report saved: %s", report_path)
    logger.info("Stems at:     %s", stems_out)
    logger.info("Output video: %s", job.output_path)
    logger.info("=" * 60)


if __name__ == "__main__":
    main()
