"""Test suite for MADRAC Dubbing Extension"""
import pytest
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

from src.madrac_dubbing.pipeline.models import (
    DubbingJob, DubbingConfig, DubbingStatus, Segment
)
from src.madrac_dubbing.utils.audio import timecode_to_ms, ms_to_timecode


class TestModels:
    """Test data models"""

    def test_dubbing_config_creation(self):
        config = DubbingConfig(language='es', voice='female')
        assert config.language == 'es'
        assert config.voice == 'female'
        assert config.reduce_vocals == 0.7

    def test_dubbing_config_to_dict(self):
        config = DubbingConfig(language='es', voice='female')
        config_dict = config.to_dict()
        assert config_dict['language'] == 'es'
        assert config_dict['voice'] == 'female'

    def test_dubbing_config_from_dict(self):
        data = {'language': 'en', 'voice': 'male', 'reduce_vocals': 0.5}
        config = DubbingConfig.from_dict(data)
        assert config.language == 'en'
        assert config.voice == 'male'
        assert config.reduce_vocals == 0.5

    def test_dubbing_job_creation(self):
        config = DubbingConfig(language='es')
        job = DubbingJob(
            job_id='test-1',
            video_path=Path('/tmp/video.mp4'),
            srt_path=Path('/tmp/subs.srt'),
            output_path=Path('/tmp/output.mkv'),
            config=config
        )
        assert job.job_id == 'test-1'
        assert job.status == DubbingStatus.PENDING

    def test_dubbing_job_string_paths_converted(self):
        config = DubbingConfig(language='es')
        job = DubbingJob(
            job_id='test-1',
            video_path='/tmp/video.mp4',
            srt_path='/tmp/subs.srt',
            output_path='/tmp/output.mkv',
            config=config
        )
        assert isinstance(job.video_path, Path)
        assert isinstance(job.srt_path, Path)
        assert isinstance(job.output_path, Path)


class TestAudioUtilities:
    """Test audio utility functions"""

    def test_timecode_to_ms_basic(self):
        result = timecode_to_ms("00:00:05,000")
        assert result == 5000

    def test_timecode_to_ms_with_hours(self):
        result = timecode_to_ms("01:30:45,500")
        assert result == (1 * 3600 + 30 * 60 + 45) * 1000 + 500

    def test_ms_to_timecode_basic(self):
        result = ms_to_timecode(5000)
        assert result == "00:00:05,000"

    def test_timecode_roundtrip(self):
        original = "00:01:30,250"
        ms = timecode_to_ms(original)
        result = ms_to_timecode(ms)
        assert result == original


class TestTTSEngine:
    """Test TTS engine"""

    @pytest.mark.asyncio
    async def test_edge_tts_initialization(self):
        from src.madrac_dubbing.tts.edge_tts import EdgeTTSEngine
        engine = EdgeTTSEngine()
        assert engine is not None
        assert 'es' in engine.supported_languages

    def test_edge_tts_voice_selection(self):
        from src.madrac_dubbing.tts.edge_tts import EdgeTTSEngine
        engine = EdgeTTSEngine()

        male_voice = engine._get_voice_for_language('es', 'male')
        assert 'Neural' in male_voice

        female_voice = engine._get_voice_for_language('es', 'female')
        assert 'Neural' in female_voice

    def test_tts_list_voices(self):
        from src.madrac_dubbing.tts.edge_tts import EdgeTTSEngine
        engine = EdgeTTSEngine()
        voices = engine.list_voices('es')
        assert len(voices) > 0
        assert all('Neural' in v for v in voices)


class TestPipeline:
    """Test dubbing pipeline"""

    def test_pipeline_initialization(self):
        from src.madrac_dubbing.pipeline.dubbing_pipeline import DubbingPipeline
        pipeline = DubbingPipeline()
        assert pipeline is not None

    @patch('src.madrac_dubbing.pipeline.dubbing_pipeline.extract_audio')
    @patch('src.madrac_dubbing.pipeline.dubbing_pipeline.parse_srt_file')
    @patch('src.madrac_dubbing.pipeline.dubbing_pipeline.sf')
    def test_pipeline_update_progress(self, mock_sf, mock_parse, mock_extract):
        from src.madrac_dubbing.pipeline.dubbing_pipeline import DubbingPipeline

        progress_calls = []

        def capture_progress(job):
            progress_calls.append(job.progress_pct)

        pipeline = DubbingPipeline(on_progress=capture_progress)

        config = DubbingConfig(language='es')
        job = DubbingJob(
            job_id='test-1',
            video_path=Path('/tmp/video.mp4'),
            srt_path=Path('/tmp/subs.srt'),
            output_path=Path('/tmp/output.mkv'),
            config=config
        )

        pipeline._update(job, 50, "Test message")
        assert len(progress_calls) > 0


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
