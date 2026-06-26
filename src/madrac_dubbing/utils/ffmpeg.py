"""FFmpeg wrapper utilities"""
import subprocess
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_audio(video_path: Path, output_wav: Path) -> Path:
    """Extract audio from video using ffmpeg"""
    logger.info(f"Extracting audio from {video_path}")
    cmd = [
        'ffmpeg',
        '-i', str(video_path),
        '-q:a', '9',
        '-n',
        str(output_wav)
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        logger.info(f"Audio extracted to {output_wav}")
        return output_wav
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg audio extraction failed: {e.stderr}")
        raise


def get_audio_info(audio_path: Path) -> dict:
    """Get audio metadata using ffprobe"""
    cmd = [
        'ffprobe',
        '-v', 'error',
        '-show_streams',
        '-of', 'json',
        str(audio_path)
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return json.loads(result.stdout)
    except subprocess.CalledProcessError as e:
        logger.error(f"FFprobe failed: {e.stderr}")
        raise


def mux_audio_to_video(
    video_path: Path,
    audio_path: Path,
    output_path: Path,
    codec: str = "aac"
) -> Path:
    """Mux audio into video using ffmpeg"""
    logger.info(f"Muxing audio into video: {output_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)

    cmd = [
        'ffmpeg',
        '-i', str(video_path),
        '-i', str(audio_path),
        '-c:v', 'copy',
        '-c:a', codec,
        '-map', '0:v:0',
        '-map', '1:a:0',
        '-y',  # Overwrite output
        str(output_path)
    ]

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        logger.info(f"Video muxed to {output_path}")
        return output_path
    except subprocess.CalledProcessError as e:
        logger.error(f"FFmpeg muxing failed: {e.stderr}")
        raise


def get_video_duration(video_path: Path) -> float:
    """Get video duration in seconds"""
    cmd = [
        'ffprobe',
        '-v', 'error',
        '-show_entries', 'format=duration',
        '-of', 'default=noprint_wrappers=1:nokey=1:csv_sep=,',
        str(video_path)
    ]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        return float(result.stdout.strip())
    except (subprocess.CalledProcessError, ValueError) as e:
        logger.error(f"Failed to get video duration: {e}")
        raise
