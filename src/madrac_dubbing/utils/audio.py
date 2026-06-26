"""Audio utility functions"""
import io
import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def get_audio_duration_ms(audio_bytes: bytes) -> int:
    """Get duration of audio from bytes (WAV/MP3 format)"""
    try:
        import soundfile as sf
        data, sr = sf.read(io.BytesIO(audio_bytes))
        if len(data.shape) > 1:
            duration = len(data) / sr * 1000
        else:
            duration = len(data) / sr * 1000
        logger.debug(f"Audio duration computed: {int(duration)} ms (sr={sr}, frames={len(data)}, shape={data.shape})")
        return int(duration)
    except Exception as e:
        logger.error(f"Failed to get audio duration from {len(audio_bytes)} bytes: {e}")
        return 0


def parse_srt_file(srt_path: Path) -> list:
    """Parse SRT subtitle file into segment objects"""
    from ..pipeline.models import Segment

    segments = []
    try:
        content = None
        for enc in ['utf-8-sig', 'utf-16', 'utf-8', 'cp1252']:
            try:
                with open(srt_path, 'r', encoding=enc) as f:
                    content = f.read()
                break
            except UnicodeDecodeError:
                continue
                
        if content is None:
            raise ValueError(f"Could not decode {srt_path} with any known encoding")

        blocks = content.strip().replace('\r\n', '\n').split('\n\n')
        for block in blocks:
            lines = block.strip().split('\n')
            if len(lines) >= 3:
                try:
                    index = int(lines[0])
                    timing = lines[1]
                    text = '\n'.join(lines[2:])

                    start_str, end_str = timing.split(' --> ')
                    start_ms = timecode_to_ms(start_str.strip())
                    end_ms = timecode_to_ms(end_str.strip())

                    segments.append(Segment(
                        index=index,
                        start_ms=start_ms,
                        end_ms=end_ms,
                        text=text.strip()
                    ))
                except (ValueError, IndexError) as e:
                    logger.warning(f"Failed to parse SRT block: {e}")
                    continue

        logger.info(f"Parsed {len(segments)} subtitle segments from {srt_path}")
        return segments
    except Exception as e:
        logger.error(f"Failed to read SRT file {srt_path}: {e}")
        raise


def timecode_to_ms(timecode: str) -> int:
    """Convert SRT timecode (HH:MM:SS,mmm) to milliseconds"""
    parts = timecode.replace(',', '.').split(':')
    hours = int(parts[0])
    minutes = int(parts[1])
    seconds = float(parts[2])
    return int((hours * 3600 + minutes * 60 + seconds) * 1000)


def ms_to_timecode(ms: int) -> str:
    """Convert milliseconds to SRT timecode (HH:MM:SS,mmm)"""
    total_seconds = ms / 1000
    hours = int(total_seconds // 3600)
    minutes = int((total_seconds % 3600) // 60)
    seconds = int(total_seconds % 60)
    millis = int((total_seconds % 1) * 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{millis:03d}"
