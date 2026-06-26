# QUICKSTART - MADRAC Dubbing Extension

Get started with AI dubbing in 5 minutes!

## Option 1: Standalone Executable (No Installation)

### 1. Download
Get `madrac-dubbing.exe` from releases and place it anywhere.

### 2. Prepare Files
- `video.mp4` - Your video file
- `subs.srt` - Your subtitle file

### 3. Run
```bash
madrac-dubbing.exe dub-cmd \
  --video video.mp4 \
  --srt subs.srt \
  --output dubbed.mkv \
  --language es
```

Done! Your dubbed video is ready in `dubbed.mkv`.

## Option 2: Python Installation

### 1. Install
```bash
git clone https://github.com/yourusername/madrac-subs-dubbing.git
cd madrac-subs-dubbing
pip install -r requirements.txt
```

### 2. Run
```bash
python -m madrac_dubbing dub-cmd \
  --video video.mp4 \
  --srt subs.srt \
  --output dubbed.mkv \
  --language es
```

## Common Commands

### Spanish dubbing with female voice
```bash
madrac-dubbing.exe dub-cmd --video video.mp4 --srt subs.srt --output out.mkv --language es --voice female
```

### English dubbing, reduce vocals aggressively
```bash
madrac-dubbing.exe dub-cmd --video video.mp4 --srt subs.srt --output out.mkv --language en --reduce-vocals 0.9
```

### Start API server
```bash
madrac-dubbing.exe api --port 5000
```

Then submit jobs:
```bash
curl -X POST http://localhost:5000/dubbing \
  -H "Content-Type: application/json" \
  -d '{
    "video_path": "C:\\path\\to\\video.mp4",
    "srt_path": "C:\\path\\to\\subs.srt",
    "output_path": "C:\\path\\to\\output.mkv",
    "config": {
      "language": "es",
      "voice": "female"
    }
  }'
```

## Options Reference

| Option | Default | Description |
|--------|---------|-------------|
| `--language` | `es` | Target language (es, en, fr, pt, it, de, ja, zh, ru, ar) |
| `--voice` | `female` | Voice preference (female, male, neutral) |
| `--reduce-vocals` | `0.7` | Vocal reduction (0.0=none, 1.0=max) |
| `--tts-engine` | `edge` | TTS engine (edge, elevenlabs, pyttsx3) |

## Supported Languages

- **es** - Spanish
- **en** - English  
- **fr** - French
- **pt** - Portuguese
- **it** - Italian
- **de** - German
- **ja** - Japanese
- **zh** - Chinese
- **ru** - Russian
- **ar** - Arabic

## Troubleshooting

### "FFmpeg not found"
Install FFmpeg: https://ffmpeg.org/download.html

### "Internet connection required"
Edge TTS requires internet. Check your connection.

### "Audio quality is poor"
Try `--reduce-vocals 0.8` or `--reduce-vocals 0.9` to reduce original audio more.

### "TTS is too fast or slow"
The extension automatically adjusts. If audio sounds distorted:
- Try different `--voice` option
- Break long subtitles into shorter segments

## Next Steps

- Check [README.md](README.md) for detailed documentation
- See [INTEGRATION_GUIDE.md](INTEGRATION_GUIDE.md) for madrac-subs integration
- Read [ARCHITECTURE.md](ARCHITECTURE.md) for technical details

## Need Help?

- Check README.md for detailed guides
- See INTEGRATION_GUIDE.md for madrac-subs integration
- Review test files for API usage examples
- Report issues on GitHub

---

**Time to first dubbing**: 5-15 minutes (depending on video length)  
**Output format**: Matroska video (.mkv) with separate audio tracks  
**Languages**: 10+ supported with professional voices
