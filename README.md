# MADRAC Dubbing Extension v1.0-rc1

AI-powered text-to-speech dubbing extension for **madrac-subs** subtitle editor. Automatically generate professional voiceovers in multiple languages with automatic vocal reduction and audio mixing.

## Features

✨ **AI Text-to-Speech Dubbing**
- Microsoft Edge TTS (200+ voices, 50+ languages, free, no API key required)
- Support for Spanish, English, French, Portuguese, Italian, German, Japanese, Chinese, Russian, Arabic
- Automatic voice gender selection (male/female)

🎙️ **Professional Audio Processing**
- Automatic vocal reduction from original audio
- Audio synchronization to subtitle timing
- LUFS loudness normalization for broadcast-quality output
- Multi-track audio mixing (original + dubbed)

🔧 **Multiple Integration Modes**
- **CLI**: Standalone command-line tool
- **HTTP API**: Local REST endpoints for madrac-subs integration
- **Subprocess**: Direct invocation with arguments

⚡ **Performance**
- Fast TTS generation (~1-2 seconds per subtitle)
- Real-time vocal reduction
- Full pipeline: ~5-15 minutes for 1-hour video

## Installation

### Requirements
- Python 3.11+
- FFmpeg (for audio/video processing)
- Internet connection (for Edge TTS)

### From Source

```bash
git clone https://github.com/yourusername/madrac-subs-dubbing.git
cd madrac-subs-dubbing

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Run CLI
python -m madrac_dubbing dub-cmd \
  --video input.mp4 \
  --srt subtitles.srt \
  --output output_dubbed.mkv \
  --language es \
  --voice female
```

### Standalone Executable

Download `madrac-dubbing.exe` from releases (no installation needed):

```bash
madrac-dubbing.exe dub-cmd \
  --video input.mp4 \
  --srt subtitles.srt \
  --output output.mkv \
  --language es
```

## Usage

### Command-Line Mode

```bash
python -m madrac_dubbing dub-cmd \
  --video myvideo.mp4 \
  --srt subtitles.srt \
  --output dubbed.mkv \
  --language es \
  --voice female \
  --reduce-vocals 0.7 \
  --tts-engine edge
```

**Arguments:**
- `--video` *(required)*: Input video file
- `--srt` *(required)*: SRT subtitle file
- `--output` *(required)*: Output dubbed video (MKV format)
- `--language` *(default: es)*: Target language (es, en, fr, pt, it, de, ja, zh, ru, ar)
- `--voice` *(default: female)*: Voice preference (female, male, neutral)
- `--reduce-vocals` *(default: 0.7)*: Vocal reduction strength (0.0-1.0)
- `--tts-engine` *(default: edge)*: TTS engine (edge, elevenlabs, pyttsx3)

### HTTP API Mode

Start the API server:

```bash
python -m madrac_dubbing api --port 5000
```

Submit a dubbing job:

```bash
curl -X POST http://localhost:5000/dubbing \
  -H "Content-Type: application/json" \
  -d '{
    "video_path": "/path/to/video.mp4",
    "srt_path": "/path/to/subs.srt",
    "output_path": "/path/to/output.mkv",
    "config": {
      "language": "es",
      "voice": "female",
      "tts_engine": "edge",
      "reduce_vocals": 0.7
    }
  }'
```

Response:
```json
{
  "job_id": "a1b2c3d4-e5f6-...",
  "status": "pending"
}
```

Check job status:

```bash
curl http://localhost:5000/dubbing/a1b2c3d4-e5f6-...
```

Response:
```json
{
  "job_id": "a1b2c3d4-e5f6-...",
  "status": "generating_tts",
  "progress_pct": 45,
  "message": "Generated TTS for 15 segments",
  "error": null,
  "output_path": "/path/to/output.mkv"
}
```

### Integration with madrac-subs

```python
import requests
import subprocess
import time

dubbing_exe = "madrac-dubbing.exe"

# Start API server
process = subprocess.Popen([dubbing_exe, "api", "--port", "5000"])
time.sleep(2)

# Submit job
response = requests.post('http://localhost:5000/dubbing', json={
    'video_path': '/path/to/video.mp4',
    'srt_path': '/path/to/subs.srt',
    'output_path': '/path/to/output.mkv',
    'config': {
        'language': 'es',
        'voice': 'female',
        'reduce_vocals': 0.7
    }
})

job_id = response.json()['job_id']

# Poll for completion
while True:
    status = requests.get(f'http://localhost:5000/dubbing/{job_id}').json()
    print(f"[{status['progress_pct']}%] {status['message']}")
    
    if status['status'] == 'completed':
        print(f"Done: {status['output_path']}")
        break
    elif status['status'] == 'failed':
        print(f"Error: {status['error']}")
        break
    
    time.sleep(1)

process.terminate()
```

## Supported Languages

| Code | Language | Voices |
|------|----------|--------|
| es | Spanish | Alvaro (M), Elvira (F) |
| en | English | Guy (M), Jenny (F) |
| fr | French | Denise (F), Henri (M) |
| pt | Portuguese | Antonio (M), Francisca (F) |
| it | Italian | Diego (M), Isabella (F) |
| de | German | Conrad (M), Katja (F) |
| ja | Japanese | Daichi (M), Nanami (F) |
| zh | Chinese | Yunxi (M), Xiaoyu (F) |
| ru | Russian | Dmitry (M), Svetlana (F) |
| ar | Arabic | Ammar (M), Salma (F) |

## Output

The extension produces:
- **Dubbed video** (MKV format) with:
  - Original video stream
  - Mixed audio (original + TTS dubbed)
  - Original audio track (preserved)
  - Dubbed TTS track (separate for editing)

## Configuration

Create `config.json` in the working directory:

```json
{
  "tts_engine": "edge",
  "api_host": "127.0.0.1",
  "api_port": 5000,
  "default_language": "es",
  "default_voice": "female",
  "reduce_vocals_default": 0.7,
  "target_lufs": -20.0
}
```

## Troubleshooting

### "FFmpeg not found"
Install FFmpeg:
- **Windows**: `choco install ffmpeg` or download from ffmpeg.org
- **macOS**: `brew install ffmpeg`
- **Linux**: `apt-get install ffmpeg`

### "Internet connection required for Edge TTS"
Edge TTS requires internet. Ensure you're connected before starting.

### "Audio quality is poor"
- Increase `--reduce-vocals` (0.8-1.0) to reduce original audio
- Adjust `--target-lufs` for loudness normalization

### "TTS is too fast/slow"
The extension automatically time-stretches TTS to match subtitle duration. If audio sounds distorted, try:
- Shorter subtitle segments
- Different voice gender
- Alternative TTS engine (ElevenLabs for paid premium quality)

## Performance

| Task | Time | Notes |
|------|------|-------|
| TTS generation | 1-2 sec/segment | Depends on segment length, internet |
| Audio extraction | ~10% video duration | Fast, parallelizable |
| Vocal reduction | ~90% video duration | Real-time processing |
| Muxing | ~10% video duration | Fast, copies streams |
| **Total** | ~5-15 min/hour video | Varies by hardware, internet, TTS load |

## Architecture

```
Video Input
    ↓
[Extract Audio] → Original WAV
    ↓
[Generate TTS] → TTS Audio Segments (synchronized to subtitles)
    ↓
[Reduce Vocals] → Reduced Original Audio
    ↓
[Mix Tracks] → Original + TTS Mixed Audio
    ↓
[Normalize] → Broadcast-quality audio
    ↓
[Mux Video + Audio] → Dubbed MKV Output
```

## Development

### Project Structure

```
madrac-dubbing/
├── src/madrac_dubbing/
│   ├── __init__.py
│   ├── __main__.py          # Entry point
│   ├── cli.py               # CLI interface
│   ├── api.py               # HTTP API
│   ├── config.py            # Configuration
│   ├── pipeline/
│   │   ├── models.py        # Data structures
│   │   └── dubbing_pipeline.py  # Main workflow
│   ├── tts/
│   │   ├── engine.py        # TTS abstraction
│   │   └── edge_tts.py      # Edge TTS implementation
│   ├── audio/
│   │   └── mixer.py         # Audio processing
│   └── utils/
│       ├── audio.py         # Audio utilities
│       └── ffmpeg.py        # FFmpeg wrappers
├── tests/                   # Unit & integration tests
├── requirements.txt
├── pyproject.toml
├── madrac-dubbing.spec      # PyInstaller configuration
└── README.md
```

### Running Tests

```bash
pip install -e ".[dev]"
pytest tests/ -v
```

### Building Executable

```bash
pip install -e ".[build]"
pyinstaller madrac-dubbing.spec --onedir --distpath dist/
# Result: dist/madrac-dubbing/madrac-dubbing.exe
```

## Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

## License

MIT License - See LICENSE file

## Support

For issues, feature requests, or questions:
- GitHub Issues: https://github.com/yourusername/madrac-subs-dubbing/issues
- Email: support@madrac.dev

---

**Status**: v1.0-rc1 Ready for Production  
**Last Updated**: June 2026  
**Maintainer**: MADRAC Team
