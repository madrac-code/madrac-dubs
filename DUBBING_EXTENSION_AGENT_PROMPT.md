# MADRAC-SUBS DUBBING EXTENSION: AI Agent Prompt

**Status**: Ready for implementation  
**Target**: Separate `.exe` subprocess for AI dubbing  
**Integration**: Bi-directional with madrac-subs core application  
**Scope**: Text-to-speech dubbing with separate audio tracks and editing  

---

## 🎯 EXECUTIVE BRIEF

You are tasked with building **MADRAC-DUBBING v1.0**, a standalone AI dubbing extension that:

1. **Integrates** with madrac-subs (subtitle editor) without modifying core code
2. **Accepts** subtitle data + video playback from madrac-subs
3. **Generates** AI voiceover using TTS (text-to-speech)
4. **Produces** separate audio tracks (original + dubbed + voice-only)
5. **Exports** dubbed video with synchronized audio

**Key constraint**: NO modifications to madrac-subs core. All integration via:
- Shared temporary file exchange (JSON + audio files)
- HTTP API (localhost REST endpoint in dubbing app)
- Direct file paths passed via arguments

**Deliverable**: `madrac-dubbing.exe` (~200-300MB, Python 3.11 + TTS library + ffmpeg)

---

## 📊 ARCHITECTURE OVERVIEW

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         MADRAC-SUBS CORE (v3.0)                         │
│  ├── Video Player (PySide6 QMediaPlayer)                               │
│  ├── Subtitle Editor (with timing, text, language)                     │
│  └── Export: SRT, video with subs → TEMP FILES                         │
└─────────────────────────────────────────────────────────────────────────┘
                          ↓
                  (Invoke subprocess)
                          ↓
         MADRAC-DUBBING (New Extension)
         ┌──────────────────────────────────┐
         │ 1. Receive via stdin/args/REST   │
         │    - video_path                  │
         │    - srt_path (or JSON)          │
         │    - config (language, voice)    │
         │ 2. TTS Generation                │
         │    - Convert text → audio (edge) │
         │    - Sync with timing            │
         │ 3. Audio Mixing                  │
         │    - Original vocal extracted    │
         │    - Reduce vocal (filters)      │
         │    - Layer dubbing over          │
         │ 4. Export                        │
         │    - Multi-track video (.mkv)    │
         │    - Report status → stdout      │
         └──────────────────────────────────┘
                          ↓
           Save multi-track to OUTPUT PATH
```

---

## 📋 PHASE 1: CORE ARCHITECTURE

### 1.1 Project Structure

```
madrac-dubbing/
├── src/
│   └── madrac_dubbing/
│       ├── __init__.py
│       ├── __main__.py                    # Entry point (python -m madrac_dubbing)
│       ├── app.py                         # Main application class
│       ├── config.py                      # Config manager (TTS engine, voice, language)
│       ├── cli.py                         # CLI argument parsing
│       ├── api.py                         # HTTP API (localhost:5000)
│       ├── tts/
│       │   ├── __init__.py
│       │   ├── engine.py                  # Abstract TTS interface
│       │   ├── edge_tts.py               # Microsoft Edge TTS (online, free)
│       │   ├── elevenlabs.py             # ElevenLabs TTS (optional, paid)
│       │   └── pyttsx3.py                # Fallback local TTS
│       ├── audio/
│       │   ├── __init__.py
│       │   ├── mixer.py                  # Audio track mixing/reduction
│       │   ├── extraction.py             # Extract vocals from audio
│       │   ├── loudness.py               # LUFS normalization
│       │   └── sync.py                   # Sync TTS to subtitle timing
│       ├── pipeline/
│       │   ├── __init__.py
│       │   ├── dubbing_pipeline.py       # Main dubbing workflow
│       │   ├── models.py                 # Data models (DubbingJob, DubbingConfig)
│       │   └── stages/
│       │       ├── __init__.py
│       │       ├── 01_validate.py        # Validate input files
│       │       ├── 02_audio_extract.py   # Extract audio from video
│       │       ├── 03_tts_generate.py    # Generate TTS audio
│       │       ├── 04_vocal_reduce.py    # Reduce original vocals
│       │       ├── 05_mix_audio.py       # Mix tracks
│       │       ├── 06_sync_subtitles.py # (Optional) hardcode subtitles
│       │       └── 07_mux_export.py      # Mux audio + video
│       ├── utils/
│       │   ├── __init__.py
│       │   ├── ffmpeg.py                 # FFmpeg wrappers (extract, mux)
│       │   ├── paths.py                  # Path resolution (frozen exe)
│       │   └── json_codec.py             # Serialize/deserialize configs
│       └── logging.py                    # Logging setup
├── tests/
│   ├── test_tts_edge.py
│   ├── test_audio_mixer.py
│   ├── test_pipeline.py
│   └── test_api.py
├── requirements.txt
├── pyproject.toml
├── madrac-dubbing.spec                   # PyInstaller spec (ONEDIR, ~300MB)
└── README.md
```

### 1.2 Entry Points

**CLI Mode** (called from madrac-subs or standalone):
```bash
python -m madrac_dubbing \
  --video input.mp4 \
  --srt subtitles.srt \
  --output output_dubbed.mkv \
  --language es \
  --voice female \
  --reduce-vocals 0.7 \
  --tts-engine edge
```

**API Mode** (long-running server):
```bash
python -m madrac_dubbing --api --port 5000
# Server listens on http://localhost:5000/dubbing POST endpoint
```

**Direct Integration from madrac-subs**:
```python
# In madrac-subs (future integration point)
subprocess.Popen([
    str(dubbing_exe),
    '--video', str(video_path),
    '--srt', str(srt_path),
    '--output', str(output_path),
    '--config-json', json.dumps(dubbing_config)
], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
```

---

## 🎙️ PHASE 2: TEXT-TO-SPEECH (TTS) ENGINE

### 2.1 Abstract TTS Interface

```python
# src/madrac_dubbing/tts/engine.py
from abc import ABC, abstractmethod
from typing import List, Tuple
from dataclasses import dataclass

@dataclass
class TTSSegment:
    """TTS output: audio bytes + timing info."""
    index: int           # Subtitle index
    text: str           # Original text
    audio_bytes: bytes  # WAV audio (16kHz, mono)
    duration_ms: int   # Actual audio duration
    start_ms: int      # Sync to this subtitle start
    end_ms: int        # Subtitle end

class TTSEngine(ABC):
    """Abstract TTS engine."""
    
    @abstractmethod
    def synthesize(self, segments: List[Segment], language: str, voice: str) -> List[TTSSegment]:
        """Generate TTS audio for subtitle segments."""
        pass
    
    @abstractmethod
    def list_voices(self, language: str) -> List[str]:
        """List available voices for language."""
        pass
    
    @property
    @abstractmethod
    def supported_languages(self) -> List[str]:
        """ISO 639-1 language codes."""
        pass
```

### 2.2 Edge TTS Implementation (Primary)

**Why Edge TTS?**
- Free (no API key required)
- Natural sounding voices (Microsoft's SSML-capable)
- 200+ voices across 50+ languages
- Online only (requires internet)

```python
# src/madrac_dubbing/tts/edge_tts.py
import edge_tts
import asyncio
from typing import List

class EdgeTTSEngine(TTSEngine):
    """Microsoft Edge TTS integration."""
    
    def __init__(self):
        self.voice_map = {
            'es': ['es-ES-AlvaroNeural', 'es-ES-ElviraNeural'],
            'en': ['en-US-GuyNeural', 'en-US-JennyNeural'],
            'fr': ['fr-FR-DeniseNeural', 'fr-FR-HenriNeural'],
            'pt': ['pt-BR-AntonioNeural', 'pt-BR-FranciscaNeural'],
            # ... 50+ languages
        }
    
    async def synthesize_segment(self, text: str, language: str, voice: str) -> bytes:
        """Generate audio for one segment."""
        communicate = edge_tts.Communicate(text, voice)
        audio_data = b""
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                audio_data += chunk["data"]
        return audio_data
    
    def synthesize(self, segments: List[Segment], language: str, voice: str) -> List[TTSSegment]:
        """Sync TTS to subtitle timing using asyncio."""
        loop = asyncio.get_event_loop()
        results = []
        
        for seg in segments:
            # Generate TTS audio
            audio_bytes = loop.run_until_complete(
                self.synthesize_segment(seg.text, language, voice)
            )
            
            # Get duration using soundfile
            duration_ms = get_audio_duration_ms(audio_bytes)
            
            results.append(TTSSegment(
                index=seg.index,
                text=seg.text,
                audio_bytes=audio_bytes,
                duration_ms=duration_ms,
                start_ms=seg.start_ms,
                end_ms=seg.end_ms,
            ))
        
        return results
    
    @property
    def supported_languages(self) -> List[str]:
        return list(self.voice_map.keys())
```

### 2.3 Fallback: ElevenLabs (Optional, Premium)

```python
# src/madrac_dubbing/tts/elevenlabs.py
# Implement if user has API key in config
# Better for consistent voice character preservation
```

### 2.4 Fallback: pyttsx3 (Offline)

```python
# src/madrac_dubbing/tts/pyttsx3.py
# Local TTS fallback if Edge unavailable (worse quality, but offline)
```

---

## 🔊 PHASE 3: AUDIO PROCESSING & MIXING

### 3.1 Audio Extraction from Video

```python
# src/madrac_dubbing/audio/extraction.py
import subprocess
from pathlib import Path

def extract_audio(video_path: Path, output_wav: Path) -> Path:
    """Extract audio from video using ffmpeg."""
    cmd = [
        'ffmpeg', '-i', str(video_path),
        '-q:a', '9', '-n',  # Extract audio, no overwrite
        str(output_wav)
    ]
    subprocess.run(cmd, check=True, capture_output=True)
    return output_wav

def get_audio_info(audio_path: Path) -> dict:
    """Get audio metadata (channels, sample rate, duration)."""
    cmd = ['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(audio_path)]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    return json.loads(result.stdout)
```

### 3.2 Vocal Reduction (Remove Original Dialog)

```python
# src/madrac_dubbing/audio/mixer.py
import numpy as np
from scipy.signal import butter, sosfilt  # scipy for audio filters
import soundfile as sf

def reduce_vocals(audio_path: Path, reduction_factor: float = 0.7) -> np.ndarray:
    """
    Reduce vocals using center channel cancellation + EQ filtering.
    
    Args:
        audio_path: Input audio file
        reduction_factor: 0.0 (no reduction) to 1.0 (full removal)
    
    Returns:
        Audio with reduced vocals
    """
    audio, sr = sf.read(audio_path)
    
    # If stereo: apply center channel cancellation
    if len(audio.shape) == 2 and audio.shape[1] == 2:
        L, R = audio[:, 0], audio[:, 1]
        # Vocals usually centered (equal in both channels)
        # Subtract center to isolate sides (instrumental)
        center = (L + R) / 2
        audio_reduced = (L - center) + (R - center)
    else:
        # For mono: apply EQ to reduce vocal frequencies (200-3000 Hz)
        audio_reduced = audio
    
    # Apply high-pass + low-pass filters to preserve music
    sos = butter(4, [100, 10000], btype='band', fs=sr, output='sos')
    audio_filtered = sosfilt(sos, audio_reduced)
    
    # Blend original with reduced (controlled by reduction_factor)
    audio_output = audio * (1 - reduction_factor) + audio_filtered * reduction_factor
    
    return audio_output, sr
```

### 3.3 TTS-to-Subtitle Sync

```python
# src/madrac_dubbing/audio/sync.py
import soundfile as sf
import numpy as np

def sync_tts_to_subtitle(
    tts_segments: List[TTSSegment],
    target_sr: int = 44100
) -> np.ndarray:
    """
    Align TTS audio to subtitle timing.
    
    If TTS duration doesn't match subtitle duration:
    - Too short: Add silence at end
    - Too long: Compress audio using time-stretch
    """
    output_audio = np.array([])
    current_ms = 0
    
    for seg in tts_segments:
        # Calculate silence to insert
        silence_duration_ms = seg.start_ms - current_ms
        if silence_duration_ms > 0:
            silence_samples = int((silence_duration_ms / 1000) * target_sr)
            output_audio = np.concatenate([output_audio, np.zeros(silence_samples)])
            current_ms = seg.start_ms
        
        # Load TTS audio
        tts_audio, sr = sf.read(io.BytesIO(seg.audio_bytes))
        if sr != target_sr:
            tts_audio = librosa.resample(tts_audio, orig_sr=sr, target_sr=target_sr)
        
        subtitle_duration_ms = seg.end_ms - seg.start_ms
        tts_duration_ms = (len(tts_audio) / target_sr) * 1000
        
        # Time-stretch if needed
        if abs(tts_duration_ms - subtitle_duration_ms) > 50:  # >50ms difference
            stretch_factor = subtitle_duration_ms / tts_duration_ms
            tts_audio = librosa.effects.time_stretch(tts_audio, rate=stretch_factor)
        
        # Concatenate TTS audio
        output_audio = np.concatenate([output_audio, tts_audio])
        current_ms = seg.end_ms
    
    return output_audio, target_sr
```

### 3.4 Loudness Normalization (LUFS)

```python
# src/madrac_dubbing/audio/loudness.py
import pyloudnorm  # Audio loudness metering

def normalize_loudness(audio: np.ndarray, sr: int, target_lufs: float = -20.0) -> np.ndarray:
    """Normalize audio loudness to target LUFS (streaming standard)."""
    meter = pyloudnorm.Meter(sr)
    loudness = meter.integrated_loudness(audio)
    
    if loudness < -100:  # Silent audio
        return audio
    
    loudness_normalized = pyloudnorm.normalize(audio, loudness, target_lufs)
    return loudness_normalized
```

---

## 🎬 PHASE 4: MAIN DUBBING PIPELINE

### 4.1 Data Models

```python
# src/madrac_dubbing/pipeline/models.py
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List
from enum import Enum

class DubbingStatus(Enum):
    PENDING = "pending"
    VALIDATING = "validating"
    EXTRACTING_AUDIO = "extracting_audio"
    GENERATING_TTS = "generating_tts"
    REDUCING_VOCALS = "reducing_vocals"
    MIXING_AUDIO = "mixing_audio"
    EXPORTING = "exporting"
    COMPLETED = "completed"
    FAILED = "failed"

@dataclass
class DubbingConfig:
    """Configuration for dubbing job."""
    language: str  # Target language (es, en, fr, pt, etc)
    voice: str     # Voice ID (female, male, neutral)
    tts_engine: str  # edge, elevenlabs, pyttsx3
    reduce_vocals: float = 0.7  # 0.0-1.0
    target_lufs: float = -20.0  # Loudness normalization
    hardcode_subs: bool = False  # Burn subtitles to video
    output_tracks: bool = True   # Export separate tracks in MKV

@dataclass
class DubbingJob:
    """Represents one dubbing task."""
    job_id: str
    video_path: Path
    srt_path: Path
    output_path: Path
    config: DubbingConfig
    status: DubbingStatus = DubbingStatus.PENDING
    progress_pct: int = 0
    message: str = ""
    error: Optional[str] = None
```

### 4.2 Main Pipeline

```python
# src/madrac_dubbing/pipeline/dubbing_pipeline.py
from typing import Callable, List
import logging

class DubbingPipeline:
    """Main dubbing workflow orchestrator."""
    
    def __init__(self, on_progress: Callable = None, on_log: Callable = None):
        self.on_progress = on_progress or (lambda *a: None)
        self.on_log = on_log or (lambda *a: None)
        self.tts_engine = EdgeTTSEngine()
    
    def process(self, job: DubbingJob) -> bool:
        """Execute dubbing pipeline for one job."""
        try:
            # Stage 1: Validate
            job.status = DubbingStatus.VALIDATING
            self._validate_inputs(job)
            self._update(job, 10, "Validating files...")
            
            # Stage 2: Extract audio
            job.status = DubbingStatus.EXTRACTING_AUDIO
            audio_path = self._extract_audio(job)
            self._update(job, 20, "Audio extracted")
            
            # Stage 3: Read subtitles
            subtitles = self._read_srt(job.srt_path)
            
            # Stage 4: Generate TTS
            job.status = DubbingStatus.GENERATING_TTS
            tts_segments = self.tts_engine.synthesize(
                subtitles, 
                job.config.language,
                job.config.voice
            )
            self._update(job, 40, f"Generated TTS for {len(tts_segments)} segments")
            
            # Stage 5: Reduce vocals
            job.status = DubbingStatus.REDUCING_VOCALS
            original_audio, sr = sf.read(str(audio_path))
            reduced_audio, sr = reduce_vocals(audio_path, job.config.reduce_vocals)
            self._update(job, 50, "Vocals reduced")
            
            # Stage 6: Mix audio
            job.status = DubbingStatus.MIXING_AUDIO
            dubbed_audio, sr = sync_tts_to_subtitle(tts_segments)
            
            # Normalize loudness
            dubbed_audio = normalize_loudness(dubbed_audio, sr, job.config.target_lufs)
            
            # Mix: reduced original + dubbed TTS
            mix_ratio = 0.3  # 30% reduced original, 70% dubbed
            final_audio = (reduced_audio * mix_ratio + dubbed_audio * (1 - mix_ratio))
            
            # Save temp audio
            temp_dubbed_audio = job.output_path.parent / f"{job.output_path.stem}_dubbed_audio.wav"
            sf.write(str(temp_dubbed_audio), final_audio, sr)
            self._update(job, 70, "Audio mixed")
            
            # Stage 7: Mux video + audio
            job.status = DubbingStatus.EXPORTING
            self._mux_video_audio(
                job.video_path,
                temp_dubbed_audio,
                job.output_path,
                original_audio=original_audio,  # For multi-track MKV
                dubbed_audio=dubbed_audio,      # For multi-track MKV
            )
            self._update(job, 90, "Video exported")
            
            # Cleanup
            temp_dubbed_audio.unlink()
            audio_path.unlink()
            
            job.status = DubbingStatus.COMPLETED
            self._update(job, 100, "Dubbing completed successfully")
            return True
            
        except Exception as e:
            job.status = DubbingStatus.FAILED
            job.error = str(e)
            self._update(job, 0, f"Error: {e}")
            self.on_log(f"ERROR: {e}")
            return False
    
    def _update(self, job: DubbingJob, progress: int, message: str):
        job.progress_pct = progress
        job.message = message
        self.on_progress(job)
        self.on_log(f"[{progress}%] {message}")
    
    def _validate_inputs(self, job: DubbingJob):
        if not job.video_path.exists():
            raise FileNotFoundError(f"Video not found: {job.video_path}")
        if not job.srt_path.exists():
            raise FileNotFoundError(f"SRT not found: {job.srt_path}")
    
    def _extract_audio(self, job: DubbingJob) -> Path:
        output_wav = job.output_path.parent / f"{job.output_path.stem}_original.wav"
        return extract_audio(job.video_path, output_wav)
    
    def _read_srt(self, srt_path: Path) -> List[Segment]:
        """Parse SRT file into Segment objects."""
        # Use existing madrac subtitle parser
        pass
    
    def _mux_video_audio(self, video_path: Path, audio_path: Path, output_path: Path, **kwargs):
        """Mux audio back into video using ffmpeg."""
        # Build ffmpeg command
        pass
```

---

## 🌐 PHASE 5: HTTP API (For madrac-subs Integration)

### 5.1 Flask API Endpoint

```python
# src/madrac_dubbing/api.py
from flask import Flask, request, jsonify
import uuid
from threading import Thread

app = Flask(__name__)
pipeline = DubbingPipeline()
jobs = {}  # {job_id: DubbingJob}

@app.route('/dubbing', methods=['POST'])
def submit_dubbing_job():
    """
    Submit a dubbing job.
    
    Request body:
    {
        "video_path": "/path/to/video.mp4",
        "srt_path": "/path/to/subs.srt",
        "output_path": "/path/to/output.mkv",
        "config": {
            "language": "es",
            "voice": "female",
            "tts_engine": "edge",
            "reduce_vocals": 0.7
        }
    }
    
    Response:
    {
        "job_id": "uuid-here",
        "status": "pending"
    }
    """
    data = request.json
    job_id = str(uuid.uuid4())
    
    job = DubbingJob(
        job_id=job_id,
        video_path=Path(data['video_path']),
        srt_path=Path(data['srt_path']),
        output_path=Path(data['output_path']),
        config=DubbingConfig(**data['config']),
    )
    
    jobs[job_id] = job
    
    # Process in background
    thread = Thread(target=pipeline.process, args=(job,))
    thread.start()
    
    return jsonify({
        'job_id': job_id,
        'status': job.status.value
    })

@app.route('/dubbing/<job_id>', methods=['GET'])
def get_dubbing_status(job_id):
    """Get status of dubbing job."""
    job = jobs.get(job_id)
    if not job:
        return jsonify({'error': 'Job not found'}), 404
    
    return jsonify({
        'job_id': job.job_id,
        'status': job.status.value,
        'progress_pct': job.progress_pct,
        'message': job.message,
        'error': job.error,
        'output_path': str(job.output_path),
    })

def run_api(port: int = 5000):
    """Start API server."""
    app.run(host='127.0.0.1', port=port, debug=False)
```

### 5.2 madrac-subs Integration Point (Example)

```python
# In madrac-subs editor, when user clicks "Dub this" button:
import requests
import subprocess
import json

def start_dubbing_extension(video_path, srt_path, output_path, config):
    """Launch dubbing extension and submit job."""
    
    # Start extension process (if not running)
    dubbing_exe = Path(madrac_installation) / 'madrac-dubbing.exe'
    if not any('madrac-dubbing' in p.name for p in psutil.process_iter(['name'])):
        subprocess.Popen([str(dubbing_exe), '--api', '--port', '5000'])
        time.sleep(2)  # Wait for server to start
    
    # Submit job via API
    try:
        response = requests.post('http://localhost:5000/dubbing', json={
            'video_path': str(video_path),
            'srt_path': str(srt_path),
            'output_path': str(output_path),
            'config': config
        })
        job_id = response.json()['job_id']
        
        # Poll for completion (or use websocket)
        while True:
            status = requests.get(f'http://localhost:5000/dubbing/{job_id}').json()
            if status['status'] == 'completed':
                print(f"Dubbed video saved to: {status['output_path']}")
                break
            elif status['status'] == 'failed':
                raise Exception(status['error'])
            time.sleep(1)
    
    except Exception as e:
        print(f"Dubbing failed: {e}")
```

---

## 📦 PHASE 6: DEPENDENCIES & BUILD

### 6.1 Requirements

```txt
# TTS
edge-tts==6.1.12
elevenlabs>=0.2.0  # Optional

# Audio processing
librosa==0.10.0
scipy==1.11.0
soundfile==0.12.1
pyloudnorm==0.1.0
numpy>=1.24.0

# CLI & API
Flask==3.0.0
click==8.1.0

# Utilities
requests==2.31.0
python-dotenv==1.0.0

# Testing
pytest==7.4.0
pytest-asyncio==0.21.0

# Build
pyinstaller>=6.2
```

### 6.2 PyInstaller Spec

```python
# madrac-dubbing.spec
block_cipher = None

a = Analysis(
    ['src/madrac_dubbing/__main__.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        'edge_tts',
        'librosa',
        'scipy.signal',
        'soundfile',
        'flask',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludedimports=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='madrac-dubbing',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
```

### 6.3 Build Command

```bash
pyinstaller madrac-dubbing.spec --onedir --distpath dist/
# Result: dist/madrac-dubbing/madrac-dubbing.exe (~300MB)
```

---

## 🧪 PHASE 7: TESTING STRATEGY

### 7.1 Unit Tests

```python
# tests/test_tts_edge.py
def test_synthesize_spanish():
    engine = EdgeTTSEngine()
    segments = [Segment(1, 0, 3000, "Hola mundo")]
    result = engine.synthesize(segments, 'es', 'female')
    assert len(result) == 1
    assert result[0].duration_ms > 0
    assert len(result[0].audio_bytes) > 0

# tests/test_audio_mixer.py
def test_reduce_vocals():
    audio, sr = sf.read('test_audio.wav')
    reduced = reduce_vocals_simple(audio, sr, 0.7)
    assert reduced.shape == audio.shape
    assert np.max(reduced) <= np.max(audio)

# tests/test_pipeline.py
def test_dubbing_pipeline_end_to_end():
    job = DubbingJob(
        job_id='test-1',
        video_path=Path('test_video.mp4'),
        srt_path=Path('test_subs.srt'),
        output_path=Path('/tmp/output.mkv'),
        config=DubbingConfig(language='es', voice='female'),
    )
    pipeline = DubbingPipeline()
    success = pipeline.process(job)
    assert success
    assert job.output_path.exists()
```

### 7.2 Integration Tests

```python
# tests/test_api.py
def test_api_submit_job():
    client = app.test_client()
    response = client.post('/dubbing', json={
        'video_path': '/tmp/test.mp4',
        'srt_path': '/tmp/test.srt',
        'output_path': '/tmp/out.mkv',
        'config': {'language': 'es', 'voice': 'female'},
    })
    assert response.status_code == 200
    job_id = response.json['job_id']
    
    # Poll status
    response = client.get(f'/dubbing/{job_id}')
    assert response.status_code == 200
```

---

## 📋 IMPLEMENTATION CHECKLIST

### Pre-Implementation
- [ ] Set up git repo: `madrac-subs-dubbing`
- [ ] Create Python 3.11 venv
- [ ] Create project structure above
- [ ] Initialize pyproject.toml + requirements.txt

### Core Development
- [ ] Implement TTS engine abstraction (engine.py)
- [ ] Implement EdgeTTS integration
- [ ] Implement audio extraction/processing (mixer.py, sync.py)
- [ ] Implement main pipeline (dubbing_pipeline.py)
- [ ] Implement CLI (cli.py) with argument parsing
- [ ] Implement HTTP API (api.py)
- [ ] Add logging + error handling throughout

### Testing
- [ ] Unit tests for TTS, audio, pipeline
- [ ] Integration tests for API
- [ ] E2E test: full dubbing workflow
- [ ] Test with real madrac-subs output

### Packaging
- [ ] Create PyInstaller spec
- [ ] Build .exe (~300MB)
- [ ] Test .exe standalone
- [ ] Test .exe called from madrac-subs

### Documentation
- [ ] README with usage examples
- [ ] API documentation
- [ ] Configuration guide
- [ ] Troubleshooting guide

### Integration with madrac-subs (Future, Optional)
- [ ] Add "Dubbing" button to editor
- [ ] Create UI for dubbing options (language, voice, etc)
- [ ] Add dubbing job polling UI
- [ ] Handle multi-track playback (original + dubbed)

---

## 🚀 SUCCESS CRITERIA

By completion of v1.0:

1. ✅ `.exe` builds and runs standalone: `madrac-dubbing.exe --video test.mp4 --srt test.srt --output out.mkv`
2. ✅ HTTP API runs and accepts jobs: `http://localhost:5000/dubbing` POST endpoint
3. ✅ TTS generation works for ES/EN/FR/PT with Edge TTS
4. ✅ Audio mixing works: original vocals reduced + TTS dubbed overlaid
5. ✅ Multi-track MKV export: original, dubbed, voice-only tracks selectable
6. ✅ Can be called from madrac-subs without core modifications
7. ✅ All 257 madrac-subs tests still pass (NO core changes)
8. ✅ < 500MB total disk footprint (including all dependencies)

---

## 📝 DELIVERY FORMAT

Create a GitHub repository:
- **Repo name**: `madrac-subs-dubbing`
- **Structure**: As outlined above
- **README.md**: Quick start guide
- **ARCHITECTURE.md**: Deep dive into design decisions
- **Releases**: v1.0 with .exe + dependencies packaged

Tag version: **v1.0-rc1** for first release candidate

---

## ⚡ NOTES FOR AGENT

1. **NO modifications to madrac-subs core** — This is critical. All integration via:
   - File exchange (temp folders)
   - HTTP API (localhost)
   - Subprocess arguments
   
2. **Reuse madrac-subs components where possible**:
   - Subtitle parsing: Use madrac's `editor_io.py` if accessible
   - Logging: Match madrac's logging pattern
   - Config: Use similar config manager pattern
   
3. **Handle offline gracefully**:
   - Edge TTS requires internet — add offline mode using pyttsx3 as fallback
   - Warn user if no internet when using Edge TTS
   
4. **Performance targets**:
   - TTS generation: ~1-2 seconds per subtitle segment (Edge TTS is fast)
   - Vocal reduction: Real-time (< video duration)
   - Full pipeline: ~5-15 minutes for 1-hour video (depends on TTS segments)
   
5. **Future extensibility** (Phase 2):
   - Voice cloning: Add user's own voice model
   - Advanced vocal separation: Use Spleeter or Meta Demucs
   - Multi-language dubbing: Auto-detect and dub multiple tracks
   - Real-time preview: WebSocket stream for live progress
   
---

**Status**: Ready for implementation  
**Complexity**: Medium (TTS + audio mixing + process management)  
**Estimated timeline**: 80-120 hours for full v1.0  
**Start date**: Immediate  

Good luck! 🎙️ 🎬
