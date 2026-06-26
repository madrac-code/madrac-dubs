# MADRAC-SUBS Integration Guide

## Overview

The MADRAC Dubbing Extension is designed to integrate seamlessly with **madrac-subs** subtitle editor without modifying the core application. Integration is achieved through:

1. **HTTP API** - Long-running server handling dubbing jobs
2. **File Exchange** - Input/output files passed via paths
3. **Process Management** - Subprocess invocation with monitoring

## Architecture

```
┌─────────────────────────────────────────────┐
│     MADRAC-SUBS (Existing Application)      │
│                                             │
│  ┌──────────────────────────────────────┐   │
│  │  Subtitle Editor                     │   │
│  │  - Load video                        │   │
│  │  - Create/Edit subtitles             │   │
│  │  - Export SRT                        │   │
│  └──────────────────────────────────────┘   │
│           ↓                                  │
│  ┌──────────────────────────────────────┐   │
│  │  [Dub Now Button]                    │   │
│  │  - Launch extension                  │   │
│  │  - Submit job                        │   │
│  │  - Show progress                     │   │
│  │  - Import dubbed video               │   │
│  └──────────────────────────────────────┘   │
└──────────────────────┬──────────────────────┘
                       │
        ┌──────────────┴──────────────┐
        ↓                             ↓
    (HTTP POST)                  (File I/O)
        │                             │
┌───────┴──────────────────────────────────────┐
│   MADRAC-DUBBING (Separate Extension)        │
│                                              │
│  ┌──────────────────────────────────────┐    │
│  │  API Server (localhost:5000)         │    │
│  │  - /dubbing POST (submit jobs)       │    │
│  │  - /dubbing/{id} GET (check status) │    │
│  │  - /health GET (health check)        │    │
│  └──────────────────────────────────────┘    │
│           ↓                                   │
│  ┌──────────────────────────────────────┐    │
│  │  Dubbing Pipeline                    │    │
│  │  - Extract audio                     │    │
│  │  - Generate TTS                      │    │
│  │  - Reduce vocals                     │    │
│  │  - Mix & normalize                   │    │
│  │  - Export dubbed video               │    │
│  └──────────────────────────────────────┘    │
└─────────────────────────────────────────────┘
```

## Integration Steps

### Step 1: Add Dubbing Button to madrac-subs UI

Add this to the subtitle editor UI (Python/PySide6):

```python
# In your QMainWindow or similar
from PySide6.QtWidgets import QPushButton
import subprocess
import time

dub_button = QPushButton("🎙️ Dub with AI")
dub_button.clicked.connect(self.on_dub_click)
# Add to toolbar or menu

def on_dub_click(self):
    """Handle dub button click"""
    if not self.current_video_path:
        self.show_error("No video loaded")
        return
    
    if not self.has_subtitles():
        self.show_error("No subtitles to dub")
        return
    
    # Launch dubbing dialog
    dialog = DubbingDialog(parent=self)
    if dialog.exec() == QDialog.Accepted:
        config = dialog.get_config()
        self.start_dubbing(config)
```

### Step 2: Create Dubbing Configuration Dialog

```python
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QSlider, QPushButton, QProgressBar
)
from PySide6.QtCore import Qt

class DubbingDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dub with AI")
        self.setup_ui()
    
    def setup_ui(self):
        layout = QVBoxLayout()
        
        # Language selection
        language_label = QLabel("Target Language:")
        self.language_combo = QComboBox()
        self.language_combo.addItems([
            "Spanish (Español)",
            "English (English)",
            "French (Français)",
            "Portuguese (Português)",
            "Italian (Italiano)",
            "German (Deutsch)",
        ])
        layout.addWidget(language_label)
        layout.addWidget(self.language_combo)
        
        # Voice selection
        voice_label = QLabel("Voice:")
        self.voice_combo = QComboBox()
        self.voice_combo.addItems(["Female", "Male", "Neutral"])
        layout.addWidget(voice_label)
        layout.addWidget(self.voice_combo)
        
        # Vocal reduction slider
        vocal_label = QLabel("Vocal Reduction:")
        self.vocal_slider = QSlider(Qt.Horizontal)
        self.vocal_slider.setMinimum(0)
        self.vocal_slider.setMaximum(100)
        self.vocal_slider.setValue(70)
        layout.addWidget(vocal_label)
        layout.addWidget(self.vocal_slider)
        
        # Buttons
        buttons_layout = QHBoxLayout()
        ok_btn = QPushButton("Start Dubbing")
        cancel_btn = QPushButton("Cancel")
        ok_btn.clicked.connect(self.accept)
        cancel_btn.clicked.connect(self.reject)
        buttons_layout.addWidget(ok_btn)
        buttons_layout.addWidget(cancel_btn)
        layout.addLayout(buttons_layout)
        
        self.setLayout(layout)
    
    def get_config(self):
        language_map = {
            "Spanish (Español)": "es",
            "English (English)": "en",
            "French (Français)": "fr",
            "Portuguese (Português)": "pt",
            "Italian (Italiano)": "it",
            "German (Deutsch)": "de",
        }
        
        return {
            "language": language_map.get(self.language_combo.currentText(), "es"),
            "voice": self.voice_combo.currentText().lower(),
            "reduce_vocals": self.vocal_slider.value() / 100.0,
        }
```

### Step 3: Implement Dubbing Job Handler

```python
import requests
import json
import tempfile
from pathlib import Path
import subprocess
import time
import threading

class DubbingManager:
    """Manage dubbing jobs with madrac-dubbing extension"""
    
    def __init__(self, madrac_dubbing_exe_path: str):
        self.exe_path = madrac_dubbing_exe_path
        self.api_url = "http://localhost:5000"
        self.process = None
    
    def ensure_api_running(self):
        """Ensure API server is running"""
        try:
            response = requests.get(f"{self.api_url}/health", timeout=1)
            if response.status_code == 200:
                return True
        except:
            pass
        
        # Start API server
        self.process = subprocess.Popen(
            [self.exe_path, "api", "--port", "5000"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        time.sleep(2)  # Wait for server to start
        return True
    
    def submit_job(self, video_path: str, srt_path: str, config: dict) -> str:
        """Submit dubbing job and return job ID"""
        self.ensure_api_running()
        
        output_path = str(Path(video_path).parent / 
                         f"{Path(video_path).stem}_dubbed.mkv")
        
        payload = {
            "video_path": video_path,
            "srt_path": srt_path,
            "output_path": output_path,
            "config": {
                "language": config.get("language", "es"),
                "voice": config.get("voice", "female"),
                "reduce_vocals": config.get("reduce_vocals", 0.7),
                "tts_engine": "edge",
            }
        }
        
        response = requests.post(f"{self.api_url}/dubbing", json=payload)
        response.raise_for_status()
        
        return response.json()["job_id"], output_path
    
    def get_job_status(self, job_id: str) -> dict:
        """Get job status"""
        response = requests.get(f"{self.api_url}/dubbing/{job_id}")
        response.raise_for_status()
        return response.json()
    
    def wait_for_completion(self, job_id: str, callback=None) -> bool:
        """Wait for job to complete, calling callback with progress"""
        while True:
            status = self.get_job_status(job_id)
            
            if callback:
                callback(status)
            
            if status["status"] == "completed":
                return True
            elif status["status"] == "failed":
                raise Exception(f"Dubbing failed: {status['error']}")
            
            time.sleep(1)
    
    def cleanup(self):
        """Stop API server"""
        if self.process:
            self.process.terminate()
            self.process.wait(timeout=5)
```

### Step 4: Add Progress Dialog

```python
from PySide6.QtWidgets import QProgressDialog, QLabel
from PySide6.QtCore import Qt, QTimer

class DubbingProgressDialog(QProgressDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Dubbing in Progress...")
        self.setRange(0, 100)
        self.setAutoClose(False)
        self.setAutoReset(False)
        
        self.message_label = QLabel()
        self.setLabel(self.message_label)
    
    def update_progress(self, status: dict):
        """Update progress from job status"""
        self.setValue(status.get("progress_pct", 0))
        self.message_label.setText(status.get("message", ""))
```

### Step 5: Integrate into Subtitle Editor

```python
# In your main editor class
def start_dubbing(self, config: dict):
    """Start dubbing job"""
    manager = DubbingManager(self.dubbing_exe_path)
    
    # Export SRT
    srt_path = tempfile.mktemp(suffix=".srt")
    self.export_srt(srt_path)
    
    # Submit job
    try:
        job_id, output_path = manager.submit_job(
            self.current_video_path,
            srt_path,
            config
        )
        
        # Show progress dialog
        progress_dialog = DubbingProgressDialog(parent=self)
        progress_dialog.show()
        
        # Poll in background thread
        def poll_job():
            try:
                manager.wait_for_completion(
                    job_id,
                    callback=lambda s: progress_dialog.update_progress(s)
                )
                progress_dialog.accept()
                self.show_success(f"Dubbed video saved to:\n{output_path}")
            except Exception as e:
                progress_dialog.reject()
                self.show_error(f"Dubbing failed: {e}")
            finally:
                manager.cleanup()
        
        thread = threading.Thread(target=poll_job)
        thread.daemon = True
        thread.start()
    
    except Exception as e:
        self.show_error(f"Failed to start dubbing: {e}")
```

## Configuration

Create `dubbing_config.json` in madrac-subs installation:

```json
{
  "dubbing_exe_path": "C:\\Program Files\\madrac\\madrac-dubbing.exe",
  "api_port": 5000,
  "default_language": "es",
  "default_voice": "female",
  "auto_reduce_vocals": true,
  "temp_dir": "%TEMP%\\madrac_dub"
}
```

## API Reference

### Submit Dubbing Job

**POST** `/dubbing`

Request:
```json
{
  "video_path": "/path/to/video.mp4",
  "srt_path": "/path/to/subs.srt",
  "output_path": "/path/to/output.mkv",
  "config": {
    "language": "es",
    "voice": "female",
    "tts_engine": "edge",
    "reduce_vocals": 0.7,
    "target_lufs": -20.0
  }
}
```

Response (200 OK):
```json
{
  "job_id": "a1b2c3d4-e5f6-...",
  "status": "pending"
}
```

### Get Job Status

**GET** `/dubbing/{job_id}`

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

### Health Check

**GET** `/health`

Response:
```json
{
  "status": "ok"
}
```

## Error Handling

Handle these common errors:

```python
try:
    job_id, output_path = manager.submit_job(...)
except requests.ConnectionError:
    show_error("Cannot connect to dubbing service. Make sure madrac-dubbing is installed.")
except requests.HTTPError as e:
    show_error(f"API error: {e.response.json()['error']}")
except Exception as e:
    show_error(f"Unexpected error: {e}")
```

## Performance Considerations

1. **Long-running operations**: Use threading to avoid UI freezing
2. **Progress updates**: Poll every 1-2 seconds for smooth UX
3. **Large files**: Expect 5-15 minutes for 1-hour videos
4. **API timeout**: Set appropriate timeouts for network requests
5. **Cleanup**: Always terminate the API server when done

## Testing

Test the integration:

```python
def test_dubbing_integration():
    """Test end-to-end dubbing integration"""
    from pathlib import Path
    
    manager = DubbingManager("madrac-dubbing.exe")
    
    # Use test files
    test_video = Path("test_samples/video.mp4")
    test_srt = Path("test_samples/subs.srt")
    
    if not test_video.exists() or not test_srt.exists():
        print("Skipping test - sample files not found")
        return
    
    # Submit job
    job_id, output = manager.submit_job(
        str(test_video),
        str(test_srt),
        {"language": "es", "voice": "female"}
    )
    
    print(f"Submitted job: {job_id}")
    
    # Wait for completion
    statuses = []
    manager.wait_for_completion(
        job_id,
        callback=lambda s: statuses.append(s)
    )
    
    print(f"Job completed. Status history: {statuses}")
    print(f"Output: {output}")
    assert Path(output).exists()
    print("✓ Integration test passed!")
```

## Troubleshooting

### API fails to start
```python
# Check if port is already in use
import socket
sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
result = sock.connect_ex(('127.0.0.1', 5000))
sock.close()
if result == 0:
    print("Port 5000 is already in use")
```

### Video codec issues
```python
# Ensure video is in H.264/AAC for compatibility
# Use: ffmpeg -i input.mp4 -c:v libx264 -c:a aac output.mp4
```

### Memory issues with large files
- Process videos in chunks
- Use temporary file cleanup
- Monitor memory usage

## Future Enhancements

- [ ] WebSocket for real-time progress streaming
- [ ] Voice cloning from audio samples
- [ ] Multi-language dubbing in one pass
- [ ] Batch processing
- [ ] Custom voice models
- [ ] Direct video import/export UI

---

For questions or issues, refer to the main README or submit an issue on GitHub.
