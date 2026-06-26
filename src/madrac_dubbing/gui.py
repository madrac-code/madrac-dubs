import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import logging
from pathlib import Path
import tempfile
import os

from .pipeline.dubbing_pipeline import DubbingPipeline
from .pipeline.models import DubbingJob, DubbingConfig
from .tts.edge_tts import EdgeTTSEngine
from .integration_layer import capabilities, current_mode
from .shared_workspace import workspace

logger = logging.getLogger(__name__)

class DubbingGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("MADRAC Dubbing")
        self.root.geometry("900x600")
        
        self.tts_engine = EdgeTTSEngine()
        self.pipeline = DubbingPipeline(
            on_progress=self.on_pipeline_progress,
            on_log=self.on_pipeline_log
        )
        
        # Variables
        self.video_path_var = tk.StringVar()
        self.srt_path_var = tk.StringVar()
        self.output_path_var = tk.StringVar()
        
        self.language_var = tk.StringVar(value="es")
        self.voice_var = tk.StringVar()
        
        self.progress_var = tk.DoubleVar()
        
        self.create_widgets()
        self.refresh_voices()

    def create_widgets(self):
        # Configure layout
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky="nsew")
        
        main_frame.columnconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.columnconfigure(2, weight=1)
        main_frame.rowconfigure(0, weight=1)
        
        # LEFT: File Selectors
        left_frame = ttk.LabelFrame(main_frame, text="Files", padding="10")
        left_frame.grid(row=0, column=0, sticky="nsew", padx=5)
        
        ttk.Label(left_frame, text="Video File:").pack(anchor=tk.W)
        video_frame = ttk.Frame(left_frame)
        video_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Entry(video_frame, textvariable=self.video_path_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(video_frame, text="Browse", command=self.browse_video).pack(side=tk.RIGHT)
        
        ttk.Label(left_frame, text="SRT File:").pack(anchor=tk.W)
        srt_frame = ttk.Frame(left_frame)
        srt_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Entry(srt_frame, textvariable=self.srt_path_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(srt_frame, text="Browse", command=self.browse_srt).pack(side=tk.RIGHT)
        
        ttk.Label(left_frame, text="Output File:").pack(anchor=tk.W)
        output_frame = ttk.Frame(left_frame)
        output_frame.pack(fill=tk.X)
        ttk.Entry(output_frame, textvariable=self.output_path_var).pack(side=tk.LEFT, fill=tk.X, expand=True)
        ttk.Button(output_frame, text="Browse", command=self.browse_output).pack(side=tk.RIGHT)
        
        # CENTER: Voice Settings
        center_frame = ttk.LabelFrame(main_frame, text="Voice Settings", padding="10")
        center_frame.grid(row=0, column=1, sticky="nsew", padx=5)
        
        ttk.Label(center_frame, text="Language:").pack(anchor=tk.W)
        self.language_cb = ttk.Combobox(center_frame, textvariable=self.language_var, state="readonly")
        self.language_cb.pack(fill=tk.X, pady=(0, 10))
        self.language_cb.bind("<<ComboboxSelected>>", self.on_language_change)
        
        ttk.Label(center_frame, text="Voice:").pack(anchor=tk.W)
        self.voice_cb = ttk.Combobox(center_frame, textvariable=self.voice_var, state="readonly")
        self.voice_cb.pack(fill=tk.X, pady=(0, 10))
        
        btn_frame = ttk.Frame(center_frame)
        btn_frame.pack(fill=tk.X, pady=(10, 0))
        ttk.Button(btn_frame, text="Refresh Voices", command=self.refresh_voices_thread).pack(side=tk.LEFT, fill=tk.X, expand=True, padx=2)
        ttk.Button(btn_frame, text="Preview Voice", command=self.preview_voice_thread).pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=2)
        
        # RIGHT: Workspace Status
        right_frame = ttk.LabelFrame(main_frame, text="System Status", padding="10")
        right_frame.grid(row=0, column=2, sticky="nsew", padx=5)
        
        ttk.Label(right_frame, text="Operating Mode:", font=("TkDefaultFont", 9, "bold")).pack(anchor=tk.W)
        ttk.Label(right_frame, text=current_mode).pack(anchor=tk.W, pady=(0, 10))
        
        ttk.Label(right_frame, text="Workspace:", font=("TkDefaultFont", 9, "bold")).pack(anchor=tk.W)
        ws_status = "Detected" if workspace.is_available else "Not Available"
        ttk.Label(right_frame, text=ws_status).pack(anchor=tk.W, pady=(0, 5))
        
        if workspace.is_available:
            resources = workspace.available_resources()
            res_text = "\n".join([f"- {r} available" for r in resources]) if resources else "- No resources"
            ttk.Label(right_frame, text=res_text).pack(anchor=tk.W, pady=(0, 10))
        else:
            ttk.Label(right_frame, text="").pack(anchor=tk.W, pady=(0, 10))
        
        ttk.Label(right_frame, text="MADRAC Capabilities:", font=("TkDefaultFont", 9, "bold")).pack(anchor=tk.W)
        caps = [k for k, v in capabilities.to_dict().items() if v]
        caps_text = "\n".join([f"- {c}" for c in caps]) if caps else "- None"
        ttk.Label(right_frame, text=caps_text).pack(anchor=tk.W)
        
        # BOTTOM: Log and Progress
        bottom_frame = ttk.Frame(main_frame)
        bottom_frame.grid(row=1, column=0, columnspan=3, sticky="nsew", pady=(10, 0))
        bottom_frame.rowconfigure(0, weight=1)
        bottom_frame.columnconfigure(0, weight=1)
        
        self.log_text = tk.Text(bottom_frame, height=10, state="disabled")
        self.log_text.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        
        scrollbar = ttk.Scrollbar(bottom_frame, command=self.log_text.yview)
        scrollbar.grid(row=0, column=1, sticky="ns", pady=(0, 10))
        self.log_text['yscrollcommand'] = scrollbar.set
        
        self.progress_bar = ttk.Progressbar(bottom_frame, variable=self.progress_var, maximum=100)
        self.progress_bar.grid(row=1, column=0, columnspan=2, sticky="ew", pady=(0, 10))
        
        self.start_btn = ttk.Button(bottom_frame, text="Start Dubbing", command=self.start_dubbing_thread)
        self.start_btn.grid(row=2, column=0, columnspan=2, sticky="ew", ipady=5)

    def browse_video(self):
        path = filedialog.askopenfilename(filetypes=[("Video files", "*.mp4 *.mkv *.avi")])
        if path:
            self.video_path_var.set(path)
            if not self.output_path_var.get():
                p = Path(path)
                self.output_path_var.set(str(p.with_name(f"{p.stem}_dubbed.mkv")))

    def browse_srt(self):
        path = filedialog.askopenfilename(filetypes=[("Subtitle files", "*.srt")])
        if path:
            self.srt_path_var.set(path)

    def browse_output(self):
        path = filedialog.asksaveasfilename(defaultextension=".mkv", filetypes=[("Video files", "*.mkv *.mp4")])
        if path:
            self.output_path_var.set(path)

    def log(self, message):
        self.log_text.configure(state="normal")
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.log_text.configure(state="disabled")

    def refresh_voices_thread(self):
        threading.Thread(target=self.refresh_voices, daemon=True).start()

    def refresh_voices(self):
        self.start_btn.config(state="disabled")
        self.log("Refreshing voices...")
        try:
            langs = self.tts_engine.supported_languages
            self.root.after(0, self._update_langs_ui, langs)
        except Exception as e:
            self.root.after(0, self.log, f"Failed to refresh voices: {e}")
        finally:
            self.root.after(0, lambda: self.start_btn.config(state="normal"))

    def _update_langs_ui(self, langs):
        self.language_cb['values'] = langs
        if langs and self.language_var.get() not in langs:
            self.language_var.set(langs[0])
        self.on_language_change(None)
        self.log("Voices refreshed.")

    def on_language_change(self, event):
        lang = self.language_var.get()
        voices = self.tts_engine.list_voices(lang)
        self.voice_cb['values'] = voices
        if voices:
            self.voice_var.set(voices[0])

    def preview_voice_thread(self):
        threading.Thread(target=self.preview_voice, daemon=True).start()

    def preview_voice(self):
        lang = self.language_var.get()
        voice = self.voice_var.get()
        if not voice:
            self.root.after(0, messagebox.showerror, "Error", "Select a voice to preview.")
            return

        self.log(f"Generating preview for {voice} ({lang})...")
        try:
            audio_bytes = self.tts_engine.preview_voice(lang, voice)
            
            # Save to temp file and play
            fd, path = tempfile.mkstemp(suffix=".wav")
            with os.fdopen(fd, 'wb') as f:
                f.write(audio_bytes)
                
            self.log("Preview audio generated. Playing...")
            # On windows we can use winsound for wav
            import winsound
            winsound.PlaySound(path, winsound.SND_FILENAME)
            
            os.unlink(path)
        except Exception as e:
            self.root.after(0, self.log, f"Preview failed: {e}")

    def on_pipeline_progress(self, job):
        self.root.after(0, self._update_progress, job.progress_pct, job.message)
        
    def _update_progress(self, pct, msg):
        self.progress_var.set(pct)
        if msg:
            self.log(f"[{pct}%] {msg}")

    def on_pipeline_log(self, msg):
        self.root.after(0, self.log, msg)

    def start_dubbing_thread(self):
        if not self.video_path_var.get() or not self.srt_path_var.get() or not self.output_path_var.get():
            messagebox.showerror("Error", "Please select Video, SRT, and Output files.")
            return
            
        self.start_btn.config(state="disabled")
        threading.Thread(target=self.start_dubbing, daemon=True).start()

    def start_dubbing(self):
        config = DubbingConfig(
            language=self.language_var.get(),
            voice=self.voice_var.get(),
            tts_engine="edge"
        )
        
        job = DubbingJob(
            job_id="gui-job",
            video_path=Path(self.video_path_var.get()),
            srt_path=Path(self.srt_path_var.get()),
            output_path=Path(self.output_path_var.get()),
            config=config
        )
        
        self.log("Starting dubbing job...")
        success = self.pipeline.process(job)
        
        if success:
            self.root.after(0, self.log, "Dubbing completed successfully!")
            self.root.after(0, messagebox.showinfo, "Success", "Dubbing completed successfully!")
        else:
            self.root.after(0, self.log, f"Dubbing failed: {job.error}")
            self.root.after(0, messagebox.showerror, "Error", f"Dubbing failed:\n{job.error}")
            
        self.root.after(0, lambda: self.start_btn.config(state="normal"))

def run_gui():
    root = tk.Tk()
    app = DubbingGUI(root)
    root.mainloop()
