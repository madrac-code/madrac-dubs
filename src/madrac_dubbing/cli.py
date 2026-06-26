"""Command-line interface"""
import click
import json
import logging
from pathlib import Path
from typing import Optional

from .pipeline.models import DubbingJob, DubbingConfig
from .pipeline.dubbing_pipeline import DubbingPipeline

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


@click.command()
@click.option('--video', type=click.Path(exists=True), required=True,
              help='Path to input video file')
@click.option('--srt', type=click.Path(exists=True), required=True,
              help='Path to SRT subtitle file')
@click.option('--output', type=click.Path(), required=True,
              help='Path to output dubbed video (MKV)')
@click.option('--language', default='es',
              help='Target language (es, en, fr, pt, etc)')
@click.option('--voice', default='female',
              help='Voice preference (female, male, neutral)')
@click.option('--tts-engine', default='edge',
              help='TTS engine (edge, elevenlabs, pyttsx3)')
@click.option('--reduce-vocals', type=float, default=0.7,
              help='Vocal reduction factor (0.0-1.0)')
@click.option('--target-lufs', type=float, default=-20.0,
              help='Target loudness in LUFS')
@click.option('--config-json', type=str, default=None,
              help='JSON config (overrides other options)')
def dub(video, srt, output, language, voice, tts_engine, reduce_vocals, target_lufs, config_json):
    """Dub a video with AI text-to-speech"""

    config_dict = {
        'language': language,
        'voice': voice,
        'tts_engine': tts_engine,
        'reduce_vocals': reduce_vocals,
        'target_lufs': target_lufs,
    }

    if config_json:
        try:
            config_dict.update(json.loads(config_json))
        except json.JSONDecodeError as e:
            click.echo(f"Invalid JSON config: {e}", err=True)
            raise click.Abort()

    config = DubbingConfig(**config_dict)

    job = DubbingJob(
        job_id='cli-job',
        video_path=Path(video),
        srt_path=Path(srt),
        output_path=Path(output),
        config=config,
    )

    def on_progress(j):
        click.echo(f"[{j.progress_pct}%] {j.message}")

    pipeline = DubbingPipeline(on_progress=on_progress, on_log=logger.info)

    click.echo(f"Starting dubbing job...")
    click.echo(f"  Video: {video}")
    click.echo(f"  Subtitles: {srt}")
    click.echo(f"  Output: {output}")
    click.echo(f"  Language: {language}")
    click.echo(f"  Voice: {voice}")

    success = pipeline.process(job)

    if success:
        click.echo(f"\n✓ Dubbing completed! Output: {output}")
        return 0
    else:
        click.echo(f"\n✗ Dubbing failed: {job.error}", err=True)
        return 1


if __name__ == '__main__':
    dub()
