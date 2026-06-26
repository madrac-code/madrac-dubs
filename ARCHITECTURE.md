# MADRAC Dubbing Extension - Architecture

## Design Overview

The MADRAC Dubbing Extension is a **standalone AI dubbing service** that integrates with madrac-subs without modifying the core application. The architecture follows these principles:

1. **Decoupled**: Separate executable, no core modifications
2. **Scalable**: HTTP API for future integrations
3. **Modular**: Clear separation of concerns (TTS, audio, pipeline)
4. **Extensible**: Abstract interfaces for TTS engines and audio processors

## Component Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                         CLI/API Entry Points                     │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │ __main__.py: Click CLI (dub-cmd, api)                   │   │
│  │ cli.py: CLI command handler                             │   │
│  │ api.py: Flask HTTP API server                           │   │
│  └──────────────────────────────────────────────────────────┘   │
│                          ↓                                       │
│  ┌──────────────────────────────────────────────────────────┐   │
│  │              DubbingPipeline (Orchestrator)              │   │
│  │  - Coordinates all stages                               │   │
│  │  - Manages progress/logging                             │   │
│  │  - Handles errors & cleanup                             │   │
│  └──────────────────────────────────────────────────────────┘   │
│    ↓           ↓              ↓           ↓           ↓          │
└────┼───────────┼──────────────┼───────────┼───────────┼──────────┘
     │           │              │           │           │
  ┌──┴──┐  ┌─────┴────┐  ┌──────┴─────┐  ┌─┴──┐  ┌───┴─────┐
  │ TTS │  │ Audio    │  │ FFmpeg     │  │Cfg │  │Logging  │
  │ Eng │  │Processing│  │ Wrappers   │  │    │  │         │
  └─────┘  └──────────┘  └────────────┘  └────┘  └─────────┘
    │          │              │
    │      (mixer.py)     (ffmpeg.py)
    │       - Reduce      - Extract
    │       - Sync        - Mux
    │       - Normalize   - Info
    │       - Mix
    │
  (engine.py) TTSEngine (Abstract)
    │
    └─── (edge_tts.py) EdgeTTSEngine
```

## Data Flow

### CLI Mode
```
User Input
    ↓
arguments → DubbingConfig
    ↓
cli.py → create DubbingJob
    ↓
DubbingPipeline.process(job)
    ↓
Output video
```

### API Mode
```
POST /dubbing (JSON)
    ↓
api.py → create DubbingJob
    ↓
Background thread → DubbingPipeline.process(job)
    ↓
GET /dubbing/{job_id} → job status (async)
    ↓
Output video ready
```

## Module Responsibilities

### `pipeline/` - Orchestration
- **models.py**: Data structures (DubbingJob, DubbingConfig, Segment, TTSSegment)
- **dubbing_pipeline.py**: Main workflow orchestrator
  - Validates inputs
  - Extracts audio
  - Calls TTS engine
  - Reduces vocals
  - Mixes tracks
  - Exports output

### `tts/` - Text-to-Speech
- **engine.py**: Abstract TTSEngine interface
  - `synthesize()`: Convert text to audio
  - `list_voices()`: Available voices
  - `supported_languages`: Language support

- **edge_tts.py**: Microsoft Edge TTS implementation
  - Async TTS generation
  - 200+ voices, 50+ languages
  - Free, no API key needed
  - Internet required

### `audio/` - Audio Processing
- **mixer.py**: Audio operations
  - `reduce_vocals()`: Center channel cancellation + EQ
  - `sync_tts_to_subtitle()`: Time-stretch TTS to subtitle timing
  - `normalize_loudness()`: LUFS normalization
  - `mix_audio_tracks()`: Blend original + dubbed audio

### `utils/` - Utilities
- **audio.py**: Audio helpers
  - `parse_srt_file()`: SRT parsing
  - `timecode_to_ms()`: Timecode conversion
  - `get_audio_duration_ms()`: Audio duration detection

- **ffmpeg.py**: FFmpeg wrappers
  - `extract_audio()`: Extract audio from video
  - `mux_audio_to_video()`: Add audio to video
  - `get_video_duration()`: Video metadata
  - `get_audio_info()`: Audio metadata

### Top-level
- **__main__.py**: Entry point (Click CLI)
- **cli.py**: CLI command handler (legacy, merged into __main__)
- **api.py**: Flask HTTP API server
- **config.py**: Configuration management
- **logging.py**: (Optional) Logging setup

## Pipeline Stages

```
Stage 1: Validation (10%)
  └─ Check video/SRT exist, readable

Stage 2: Audio Extraction (25%)
  └─ ffmpeg -i video.mp4 → original.wav

Stage 3: TTS Generation (50%)
  └─ For each subtitle: text → TTS audio

Stage 4: Vocal Reduction (60%)
  └─ original.wav → [center cancel + EQ] → reduced.wav

Stage 5: TTS Sync (70%)
  └─ TTS segments → [time-stretch] → synchronized audio

Stage 6: Normalization (75%)
  └─ Audio → [loudness meter] → normalized audio

Stage 7: Audio Mixing (80%)
  └─ reduced + TTS → [blend 30%/70%] → final audio

Stage 8: Video Muxing (95%)
  └─ ffmpeg -i video.mp4 -i audio.wav → output.mkv

Stage 9: Cleanup (100%)
  └─ Remove temp files
```

## Design Decisions

### 1. Separate Process
**Decision**: Run as standalone `.exe` instead of library
**Rationale**:
- No core modifications needed
- Independent versioning/updates
- Isolate dependencies (scipy, librosa, edge-tts)
- Can be shared/distributed separately

### 2. HTTP API
**Decision**: Flask-based REST API for local communication
**Rationale**:
- Language-agnostic (can call from any language)
- Easy testing/debugging
- Can be extended to cloud in future
- Simple request/response format (JSON)

### 3. Abstract TTS Interface
**Decision**: TTSEngine abstract base class
**Rationale**:
- Support multiple TTS engines (Edge, ElevenLabs, pyttsx3)
- Easy to add future engines
- Switch engines without changing pipeline

### 4. Edge TTS as Primary
**Decision**: Microsoft Edge TTS (free, online, 200+ voices)
**Rationale**:
- No API keys needed (free tier problem solved)
- Natural sounding voices
- Fast generation (~1-2 sec per segment)
- Wide language support

### 5. Vocal Reduction Algorithm
**Decision**: Center channel cancellation + EQ filtering
**Rationale**:
- Fast (real-time)
- Works for stereo mix without manual training
- Fallback to simple EQ for mono
- Blendable with original for natural sound

### 6. Time-Stretch Sync
**Decision**: librosa time-stretch to match subtitle duration
**Rationale**:
- Automatic sync without quality loss (vs. speed change)
- Handles variable speech rate
- PSOLA-based stretching preserves pitch

### 7. Temporary File Management
**Decision**: Use `tempfile.mkdtemp()` with cleanup
**Rationale**:
- Automatic temp directory creation
- Cleanup on completion/error
- No user-facing temp file management

### 8. LUFS Normalization
**Decision**: pyloudnorm for loudness consistency
**Rationale**:
- Broadcast standard (-18 to -23 LUFS for streaming)
- Consistent output across different original audios
- Prevents distortion from audio mixing

## Error Handling Strategy

```
Pipeline Execution
    ├─ Validation Error
    │   └─ FileNotFoundError → FAILED status
    │
    ├─ TTS Error
    │   └─ Network error → FAILED status + error message
    │
    ├─ Audio Processing Error
    │   └─ Soundfile error → FAILED status
    │
    └─ Cleanup
        └─ Remove temp files (try/finally)
```

## Performance Characteristics

| Operation | Time | Notes |
|-----------|------|-------|
| TTS synthesis | 1-2 sec/segment | Network-dependent |
| Audio extraction | ~10% video length | ffmpeg stream copy |
| Vocal reduction | ~90% video length | Real-time audio processing |
| Muxing | ~10% video length | Stream copy, no re-encode |
| **Total** | 5-15 min/hour | ~100 segments per hour |

### Optimization Opportunities
- Parallel TTS generation for multiple segments
- GPU acceleration for audio processing (scipy)
- Stream processing to avoid loading full audio
- Caching of TTS results

## Extensibility Points

### 1. New TTS Engines
```python
class GoogleTTSEngine(TTSEngine):
    def synthesize(self, segments, language, voice):
        # Implement Google TTS
        pass
```

### 2. Advanced Audio Processing
```python
# Replace reduce_vocals with Spleeter or Demucs
from spleeter.separator import Separator

def reduce_vocals_demucs(audio_path, reduction_factor=0.7):
    # Advanced vocal separation
    pass
```

### 3. Custom Voice Cloning
```python
# Future: Train voice model from user's voice samples
class CustomVoiceEngine(TTSEngine):
    def train(self, audio_samples):
        pass
    
    def synthesize(self, segments, language, voice):
        pass
```

### 4. Real-time Progress Streaming
```python
# Future: WebSocket support for live progress
@app.websocket('/dubbing/<job_id>')
def stream_progress(job_id):
    # Stream progress updates
    pass
```

## Security Considerations

1. **Input Validation**
   - File path validation (no path traversal)
   - SRT format validation
   - Config parameter validation

2. **File Operations**
   - Temporary files created in isolated temp dir
   - No arbitrary code execution from config
   - Cleanup on error (no leftover files)

3. **API Security**
   - Local-only binding (127.0.0.1)
   - No authentication (trusted network)
   - Input validation on all endpoints

4. **Subprocess Safety**
   - FFmpeg called with escaped paths
   - No shell=True usage
   - Subprocess output captured (not echoed)

## Testing Strategy

### Unit Tests
- Model creation and validation
- Timecode conversion functions
- TTS engine interface compliance
- Audio utility functions

### Integration Tests
- Full pipeline with mock files
- API endpoint testing
- TTS synthesis (live test)
- Audio mixing quality

### End-to-End Tests
- Real video/SRT files
- Complete dubbing workflow
- Output verification (file exists, valid format)

## Deployment

### Development
```bash
python -m venv venv
pip install -r requirements.txt
python -m madrac_dubbing dub-cmd --video test.mp4 --srt test.srt --output out.mkv
```

### Production
```bash
pyinstaller madrac-dubbing.spec --onedir
# Produces: dist/madrac-dubbing/madrac-dubbing.exe (~300MB)
```

### Integration with madrac-subs
```python
subprocess.Popen(["madrac-dubbing.exe", "api", "--port", "5000"])
requests.post("http://localhost:5000/dubbing", json=job_config)
```

---

## Future Roadmap

- **Phase 2**: Voice cloning from user audio
- **Phase 3**: Advanced vocal separation (Spleeter/Demucs)
- **Phase 4**: Multi-language auto-detection
- **Phase 5**: GPU acceleration
- **Phase 6**: Cloud backend option
- **Phase 7**: Real-time audio preview
- **Phase 8**: Multi-track audio editing UI

