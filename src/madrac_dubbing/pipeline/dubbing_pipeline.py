"""Main dubbing pipeline orchestrator"""
import logging
import time
from pathlib import Path
from typing import Callable, Optional
import tempfile
import shutil

import soundfile as sf

from .models import (
    DubbingJob, DubbingStatus,
    JobReport, SyncReport, TTSReport, DemucsReport, PerformanceReport, StageTiming,
)
from ..tts.edge_tts import EdgeTTSEngine
from ..audio.mixer import sync_tts_to_subtitle, normalize_loudness, mix_audio_tracks
from ..audio.separation import separate_stems, has_demucs, hash_video
from ..utils.ffmpeg import extract_audio, mux_audio_to_video
from ..utils.audio import parse_srt_file

logger = logging.getLogger(__name__)


class DubbingPipeline:
    """Main dubbing workflow orchestrator"""

    def __init__(self, on_progress: Optional[Callable] = None, on_log: Optional[Callable] = None):
        self.on_progress = on_progress or (lambda *a: None)
        self.on_log = on_log or (lambda *a: None)
        self.tts_engine = EdgeTTSEngine()
        self.temp_dir = None

    def _update(self, job: DubbingJob, progress: int, message: str):
        """Update job progress"""
        job.progress_pct = progress
        job.message = message
        self.on_progress(job)
        self.on_log(f"[{progress}%] {message}")
        logger.info(f"[{progress}%] {message}")

    def _validate_inputs(self, job: DubbingJob):
        """Validate input files exist"""
        if not job.video_path.exists():
            raise FileNotFoundError(f"Video not found: {job.video_path}")
        if not job.srt_path.exists():
            raise FileNotFoundError(f"SRT not found: {job.srt_path}")

    def process(self, job: DubbingJob) -> bool:
        """Execute dubbing pipeline for one job"""
        self.temp_dir = Path(tempfile.mkdtemp(prefix="madrac_dub_"))
        stage_timings: list[StageTiming] = []
        _t0 = time.perf_counter()

        def _stage(name: str):
            _mark(name)

        def _mark(name: str):
            stage_timings.append(StageTiming(stage=name, elapsed_s=round(time.perf_counter() - _t0, 3)))

        try:
            job.status = DubbingStatus.VALIDATING
            self._validate_inputs(job)
            self._update(job, 10, "Validating input files...")
            _mark("validate")

            job.status = DubbingStatus.EXTRACTING_AUDIO
            self._update(job, 15, "Extracting audio from video...")
            original_audio_path = self.temp_dir / "original_audio.wav"
            extract_audio(job.video_path, original_audio_path)
            self._update(job, 25, "Audio extracted")
            _mark("extract_audio")

            job.status = DubbingStatus.GENERATING_TTS
            self._update(job, 30, "Reading subtitles...")
            subtitles = parse_srt_file(job.srt_path)
            self._update(job, 35, f"Generating TTS for {len(subtitles)} segments...")

            t0 = time.perf_counter()
            tts_segments = self.tts_engine.synthesize(
                subtitles,
                job.config.language,
                job.config.voice
            )
            tts_s = time.perf_counter() - t0

            tts_cache = self.tts_engine.cache_stats
            tts_report = TTSReport(
                engine="edge",
                cache_hits=tts_cache.hits,
                cache_misses=tts_cache.misses,
                hit_rate=round(tts_cache.hit_rate * 100, 1),
                synthesis_s=round(tts_s, 3),
            )

            self._update(job, 50, f"Generated TTS for {len(tts_segments)} segments")
            _mark("tts_synthesis")

            job.status = DubbingStatus.REDUCING_VOCALS
            self._update(job, 55, "Separating audio stems...")

            demucs_report = DemucsReport()
            if has_demucs():
                t0 = time.perf_counter()
                video_hash = hash_video(job.video_path)
                stems = separate_stems(original_audio_path, video_hash=video_hash)
                t_sep = time.perf_counter() - t0
                background_path = stems.background
                cache_hit = stems.metadata.get("cache_hit", False)
                demucs_report = DemucsReport(
                    model=stems.metadata.get("model", "htdemucs"),
                    separation_s=round(t_sep, 3),
                    cache_hit=cache_hit,
                )
                logger.info("[DEMUCS] pipeline: separation=%dm%02ds  cache_hit=%s  model=%s",
                            int(t_sep // 60), int(t_sep % 60), cache_hit,
                            stems.metadata.get("model", "?"))
                logger.info("[DEMUCS] pipeline: background=%s  vocals=%s",
                            stems.background, stems.vocals)
                self._update(job, 60, "AI separation complete, background preserved")
            else:
                # LEGACY FALLBACK — DSP vocal attenuation
                from ..audio.mixer import reduce_vocals
                bg_path = self.temp_dir / "legacy_background.wav"
                reduced, sr = reduce_vocals(original_audio_path, job.config.reduce_vocals)
                sf.write(str(bg_path), reduced, sr)
                background_path = bg_path
                self._update(job, 60, "Legacy vocal reduction complete")
            _mark("separate_stems")

            job.status = DubbingStatus.MIXING_AUDIO
            self._update(job, 65, "Synchronizing TTS to subtitles...")
            background_audio, sr = sf.read(str(background_path))
            dubbed_audio, sr, sync_report = sync_tts_to_subtitle(tts_segments, sr)
            _mark("sync_tts")

            self._update(job, 70, "Normalizing loudness...")
            dubbed_audio = normalize_loudness(dubbed_audio, sr, job.config.target_lufs)
            _mark("normalize")

            self._update(job, 75, "Mixing audio tracks...")
            final_audio = mix_audio_tracks(background_audio, dubbed_audio, sr, mix_ratio=0.3)
            _mark("mix")

            dubbed_audio_path = self.temp_dir / "dubbed_audio.wav"
            sf.write(str(dubbed_audio_path), final_audio, sr)
            self._update(job, 80, "Audio mixed and saved")
            _mark("export")

            job.status = DubbingStatus.EXPORTING
            self._update(job, 85, "Exporting dubbed video...")
            job.output_path.parent.mkdir(parents=True, exist_ok=True)
            mux_audio_to_video(job.video_path, dubbed_audio_path, job.output_path)
            self._update(job, 95, "Video exported")
            _mark("done")

            job.status = DubbingStatus.COMPLETED
            job.report = JobReport(
                job_id=job.job_id,
                sync=sync_report,
                tts=tts_report,
                demucs=demucs_report,
                performance=PerformanceReport(stage_timings=stage_timings),
            )
            self._update(job, 100, "Dubbing completed successfully!")
            return True

        except Exception as e:
            job.status = DubbingStatus.FAILED
            job.error = str(e)
            logger.error(f"Dubbing pipeline failed: {e}", exc_info=True)
            self._update(job, 0, f"Error: {e}")
            return False

        finally:
            if self.temp_dir and self.temp_dir.exists():
                shutil.rmtree(self.temp_dir, ignore_errors=True)
