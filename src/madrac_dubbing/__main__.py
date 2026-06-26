"""Main entry point for madrac-dubbing"""
import sys
import os
import logging
import click
from pathlib import Path

from .cli import dub
from .api import run_api
from .utils.profiler import StartupProfiler

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Workspace initialisation (runs once at startup)
# ---------------------------------------------------------------------------

def _initialize_workspace(profiler: StartupProfiler) -> bool:
    """
    Initialise the MADRAC Shared Workspace.
    Creates directories and registers resources.  Never raises.
    """
    try:
        from .workspace_manager import get_manager
        mgr = get_manager()
        ok = mgr.init_workspace()
        profiler.mark("Workspace initialised")

        if ok:
            # Activate the legacy shared_workspace singleton for gui.py
            from .shared_workspace import workspace
            workspace.is_available = True
            workspace.__post_init__()
            profiler.mark("Shared workspace activated")

            # Initialise ModelManager with plugins root
            from .core.model_manager import ModelManager
            ModelManager.init(mgr.plugins_root)
            profiler.mark("ModelManager initialised")

        return ok
    except Exception as e:
        logger.warning("Workspace initialisation skipped: %s", e)
        return False


# ---------------------------------------------------------------------------
# Two-mode architecture helpers
# ---------------------------------------------------------------------------

def _get_operating_mode():
    from .integration_layer import detect_capabilities, determine_mode

    args = sys.argv
    cli_standalone = '--standalone' in args
    cli_skip_validate = '--skip-validate-madrac-subs' in args
    cli_integrated = '--integrated' in args

    cli_mode = None
    if cli_standalone:
        cli_mode = 'standalone'
    elif cli_integrated:
        cli_mode = 'integrated'
    elif '--mode' in args:
        try:
            idx = args.index('--mode')
            if idx + 1 < len(args):
                cli_mode = args[idx + 1]
        except (ValueError, IndexError):
            pass

    capabilities = detect_capabilities()
    mode, skip = determine_mode(
        capabilities,
        cli_mode=cli_mode,
        cli_standalone=cli_standalone,
        cli_skip_validate=cli_skip_validate,
    )
    return mode, skip


def validate_installation(operating_mode: str = 'integrated',
                          skip_validation: bool = False) -> bool:
    if skip_validation:
        logger.info("Skipping installation validation")
        return True

    from .utils.paths import FFMPEG_EXE, FFPROBE_EXE

    if not FFMPEG_EXE.exists():
        raise FileNotFoundError(
            f"ffmpeg.exe no encontrado en: {FFMPEG_EXE}\n"
            "Descargue desde https://ffmpeg.org/download.html"
        )
    if not FFPROBE_EXE.exists():
        raise FileNotFoundError(
            f"ffprobe.exe no encontrado en: {FFPROBE_EXE}\n"
            "Descargue desde https://ffmpeg.org/download.html"
        )

    if operating_mode == 'integrated':
        from .integration_layer import capabilities
        if not capabilities.any_integration_available():
            logger.warning(
                "Integrated mode requested but no MADRAC modules detected. "
                "Falling back to standalone mode. "
                "Use '--standalone' to suppress this warning."
            )
    else:
        logger.info("Standalone mode: no integration modules required")

    return True


def _warn_inactive_mode(mode: str):
    if mode == 'standalone':
        logger.info(
            "Running in standalone mode. Integration features "
            "(shared caching, timeline sync, project sharing) are disabled. "
            "Start with '--integrated' when MADRAC modules are available."
        )
    else:
        logger.info("Running in integrated mode with detected MADRAC modules.")


# ---------------------------------------------------------------------------
# CLI group
# ---------------------------------------------------------------------------

@click.group()
@click.version_option()
def cli():
    """MADRAC Dubbing Extension - AI text-to-speech dubbing for videos"""
    pass


@cli.command()
@click.option('--port', type=int, default=5000, help='API port')
@click.option('--host', default='127.0.0.1', help='API host')
@click.option('--mode', type=click.Choice(['standalone', 'integrated'],
              case_sensitive=False), default=None,
              help='Operating mode (standalone or integrated)')
@click.option('--skip-validate-madrac-subs', is_flag=True,
              help='Skip validation of MADRAC modules')
@click.option('--gui', is_flag=True, help='Launch Qt GUI (instead of API)')
def api(port, host, mode, skip_validate_madrac_subs, gui):
    """Start HTTP API server (or Qt GUI)"""
    if gui:
        _launch_gui_qt()
        return
    run_api(host=host, port=port, mode=mode,
            skip_validate_madrac_subs=skip_validate_madrac_subs)


@cli.command(context_settings=dict(ignore_unknown_options=True))
@click.option('--video', type=click.Path(exists=True), required=True,
              help='Path to input video file')
@click.option('--srt', type=click.Path(exists=True), required=True,
              help='Path to SRT subtitle file')
@click.option('--output', type=click.Path(), required=True,
              help='Path to output dubbed video')
@click.option('--language', default='es',
              help='Target language')
@click.option('--voice', default='female',
              help='Voice preference (female, male)')
@click.option('--reduce-vocals', type=float, default=0.7,
              help='Vocal reduction factor (0.0-1.0)')
@click.option('--tts-engine', default='edge',
              help='TTS engine (edge, elevenlabs, pyttsx3)')
@click.option('--config-json', type=str, default=None,
              help='JSON config string')
@click.option('--standalone', is_flag=True,
              help='Run in standalone mode (skip MADRAC module validation)')
@click.option('--skip-validate-madrac-subs', is_flag=True,
              help='Skip validation of MADRAC modules')
def dub_cmd(video, srt, output, language, voice, reduce_vocals, tts_engine,
            config_json, standalone, skip_validate_madrac_subs):
    """Dub a video with AI text-to-speech"""
    import json
    from .pipeline.models import DubbingJob, DubbingConfig
    from .pipeline.dubbing_pipeline import DubbingPipeline

    config_dict = {
        'language': language,
        'voice': voice,
        'tts_engine': tts_engine,
        'reduce_vocals': reduce_vocals,
    }

    if config_json:
        try:
            config_dict.update(json.loads(config_json))
        except json.JSONDecodeError as e:
            click.echo(f"Invalid JSON config: {e}", err=True)
            return 1

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
    click.echo(f"Starting dubbing: {Path(video).name} → {Path(output).name}")
    success = pipeline.process(job)

    if success:
        click.echo(f"\n✓ Dubbing completed!")
        return 0
    else:
        click.echo(f"\n✗ Dubbing failed: {job.error}", err=True)
        return 1


@cli.command()
@click.argument('model', type=click.Choice(['demucs', 'all']))
def download_models(model):
    """Download AI models (Demucs source separation)."""
    from .core.model_manager import ModelManager

    models = ["demucs"] if model == "demucs" else ["demucs"]
    for name in models:
        click.echo(f"Downloading {name}...")
        success = ModelManager.download(name)
        if success:
            click.echo(f"✓ {name} installed successfully.")
        else:
            click.echo(f"✗ {name} installation failed.", err=True)
            return 1
    return 0


# ---------------------------------------------------------------------------
# Qt GUI launcher
# ---------------------------------------------------------------------------

def _launch_gui_qt():
    """Launch the Qt main window."""
    try:
        from .gui_qt import run_gui_qt
        run_gui_qt()
    except ImportError as e:
        logger.error("Qt GUI unavailable: %s", e)
        logger.info("Falling back to tkinter GUI...")
        from .gui import run_gui
        run_gui()
    except Exception as e:
        logger.error("Qt GUI error: %s", e)
        logger.info("Falling back to tkinter GUI...")
        from .gui import run_gui
        run_gui()


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    """Main entry point execution logic"""
    profiler = StartupProfiler()
    try:
        from .integration_layer import set_mode, reload_capabilities

        # Initialise workspace (creates folders, detects modules)
        _initialize_workspace(profiler)

        # Reload capabilities now that workspace has been initialised
        reload_capabilities()
        profiler.mark("Capabilities reloaded")

        # Detect operating mode
        mode, skip = _get_operating_mode()
        profiler.mark(f"Mode detected: {mode}")

        os.environ['MADRAC_OPERATING_MODE'] = mode
        os.environ['MADRAC_SKIP_VALIDATION'] = str(skip).lower()
        set_mode(mode, skip)

        logger.info("Iniciando MADRAC-DUBBING en modo: %s", mode)
        _warn_inactive_mode(mode)

        validate_installation(mode, skip)
        profiler.mark("Installation validated")

        # Save profile before launching GUI or CLI
        try:
            from .workspace_manager import get_manager
            mgr = get_manager()
            profile_path = mgr.plugins_root / "logs" / "startup_profile.json"
            profiler.save(profile_path)
        except Exception:
            pass

        if len(sys.argv) == 1 or '--gui' in sys.argv:
            _launch_gui_qt()
        else:
            cli()

        profiler.log_summary()
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
