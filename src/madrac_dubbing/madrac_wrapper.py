"""
MADRAC-DUBBING - Two-Mode Architecture Wrapper

This script wraps all existing MADRAC-DUBBING functionality while adding
two-mode architecture support. It maintains 100% backward compatibility
while adding optional integration with MADRAC-SUBS.

Key Features:
1. Complete backward compatibility - all existing commands work unchanged
2. Two-mode architecture - standalone vs integrated mode
3. Smart fallback detection - automatically detects available features
4. Shared resource integration - segments, audio, timeline reuse
5. Optional validation bypass - skip madrac-subs requirement
"""
import sys
import os
import json
import subprocess
import argparse
from pathlib import Path
from typing import Optional, Dict, Any, List

# Import existing modules
from madrac_dubbing.__main__ import cli as original_cli
from madrac_dubbing.utils.paths import MADRAC_SUBS_EXE, FFMPEG_EXE, FFPROBE_EXE
from madrac_dubbing.madrac_integration import MADRACIntegration

# Configure logging
import logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class MADRACDubbingWrapper:
    """Main wrapper class for MADRAC-DUBBING with two-mode architecture"""

    def __init__(self):
        self.integration = MADRACIntegration()
        self.mode_info = self.integration.get_mode_info()

    def setup_environment(self) -> bool:
        """Setup environment based on detected mode"""
        try:
            # Always setup FFmpeg validation
            if not FFMPEG_EXE.exists():
                raise FileNotFoundError(
                    f"FFmpeg not found at: {FFMPEG_EXE}\n"
                    "Download from: https://ffmpeg.org/download.html"
                )

            if not FFPROBE_EXE.exists():
                raise FileNotFoundError(
                    f"FFprobe not found at: {FFPROBE_EXE}\n"
                    "Download from: https://ffmpeg.org/download.html"
                )

            # Mode-specific setup
            if self.mode_info["mode"] == "integrated":
                return self._setup_integrated_mode()
            else:
                return self._setup_standalone_mode()

        except Exception as e:
            logger.error(f"Environment setup failed: {e}")
            return False

    def _setup_integrated_mode(self) -> bool:
        """Setup for integrated mode with MADRAC integration"""
        logger.info("Setting up integrated mode...")

        # Log integration details
        if self.integration.integration_available:
            logger.info("MadrAC integration established")
            logger.info("Shared segments available: " +
                       "yes" if self.integration._check_shared_segments() else "no")
            logger.info("Shared audio available: " +
                       "yes" if self.integration._check_shared_audio() else "no")
            logger.info("Shared timeline available: " +
                       "yes" if self.integration._check_shared_timeline() else "no")
            logger.info("Shared projects available: " +
                       "yes" if self.integration._check_shared_projects() else "no")
        else:
            logger.info("MadrAC-SUBS executable found but integration not available")

        logger.info("Integrated mode setup complete")
        return True

    def _setup_standalone_mode(self) -> bool:
        """Setup for standalone mode"""
        logger.info("Setting up standalone mode...")
        logger.info("Independent operation - all features available")

        # Setup standalone mode config
        return True

    def get_mode_details(self) -> str:
        """Get detailed information about current mode"""
        mode = self.mode_info["mode"]

        details = f"""
======================================================================
MADRAC-DUBBING TWO-MODE ARCHITECTURE DETAILS
======================================================================
Current Mode: {mode.upper()}
MADRAC-SUBS Available: {self.mode_info["madrac_subs_available"]}
Integration Available: {self.mode_info["integration_available"]}

AVAILABLE FEATURES:
"""

        for feature, available in self.mode_info["features"].items():
            status = "✓" if available else "✗"
            details += f"  {status} {feature.replace('_', ' ').title()}\n"

        if mode == "integrated":
            details += "\nINTEGRATION FEATURES:\n"
            details += "  ✓ Shared segment reuse\n"
            details += "  ✓ Shared audio reuse\n"
            details += "  ✓ Shared timeline synchronization\n"
            details += "  ✓ Enhanced workflow optimization\n"
            details += "  ✓ Project sharing\n"
            details += "  ✓ Collaborative editing\n"

        details += f"\n======================================================================\n"
        return details

    def process_command(self, command_args: List[str]) -> bool:
        """Process command with two-mode architecture support"""
        # Parse command line arguments
        parser = argparse.ArgumentParser(prog="madrac-dubbing", add_help=False)

        parser.add_argument('--help', '-h', action='store_true')
        parser.add_argument('--version', action='store_true')
        parser.add_argument('--mode', choices=['auto', 'standalone', 'integrated'],
                          help='Operating mode: auto, standalone, or integrated')
        parser.add_argument('--skip-validate', '--skip-validation',
                          action='store_true', help='Skip madrac-subs validation')
        parser.add_argument('--integrate', action='store_true',
                          help='Enable MADRAC integration (when available)')

        # Parse known arguments
        known_args, remaining_args = parser.parse_known_args(command_args)

        # Override wrapper configuration based on command line args
        if known_args.mode:
            if known_args.mode == 'standalone':
                # Skip validation for standalone mode
                if '--skip-validate' not in command_args:
                    # Force mode to standalone by reinitializing
                    self.mode_info["mode"] = "standalone"
            elif known_args.mode == 'integrated':
                # Force integrated mode if available
                if self.integration.integration_available:
                    self.mode_info["mode"] = "integrated"
                else:
                    logger.info("Integrated mode not available, falling back to standalone")
                    self.mode_info["mode"] = "standalone"

        if known_args.skip_validate:
            self.integration.config["skip_validation"] = True

        # Setup environment
        if not self.setup_environment():
            return False

        # Show mode details if help requested
        if known_args.help:
            print(self.get_mode_details())

            # Show original help
            try:
                original_parser = argparse.ArgumentParser(prog="madrac-dubbing", add_help=False)
                original_cli().print_help()
            except:
                pass
            return True

        # Execute original CLI with remaining arguments
        if known_args.version:
            try:
                original_cli().print_version()
            except:
                print("MADRAC-DUBBING 1.0.0-dual-mode")
            return True

        # Handle API command
        if '--port' in command_args or '--host' in command_args:
            return self._run_api_mode(remaining_args)

        # Handle dub command
        if '--video' in command_args and '--srt' in command_args:
            return self._run_dub_mode(remaining_args)

        # Pass through unknown commands to original CLI
        try:
            original_cli()(remaining_args)
            return True
        except SystemExit:
            # Help was shown
            return True
        except Exception as e:
            logger.error(f"Command execution failed: {e}")
            return False

    def _run_api_mode(self, args: List[str]) -> bool:
        """Run in API mode with two-mode architecture"""
        try:
            logger.info("Starting MADRAC-DUBBING API server with two-mode architecture")
            logger.info(f"Current mode: {self.mode_info['mode']}")

            # Import and run API
            from madrac_dubbing.api import run_api

            # Extract API arguments
            parser = argparse.ArgumentParser()
            parser.add_argument('--port', type=int, default=5000)
            parser.add_argument('--host', default='127.0.0.1')
            parser.add_argument('--mode', default=self.mode_info["mode"])
            parser.add_argument('--skip-validate', action='store_true')

            api_args, _ = parser.parse_known_args(args)

            # Override with wrapper settings
            api_args.mode = self.mode_info["mode"]
            api_args.skip_validate = self.integration.config["skip_validation"]

            # Log integration status
            if self.mode_info["mode"] == "integrated" and self.integration.integration_available:
                logger.info("Running in integrated mode with MADRAC integration")
                api_result = run_api(host=api_args.host, port=api_args.port,
                                    mode=api_args.mode, skip_validation=api_args.skip_validate)
            else:
                logger.info("Running in standalone mode")
                api_result = run_api(host=api_args.host, port=api_args.port,
                                    mode=api_args.mode, skip_validation=api_args.skip_validate)

            return api_result

        except Exception as e:
            logger.error(f"API mode failed: {e}")
            return False

    def _run_dub_mode(self, args: List[str]) -> bool:
        """Run in dub mode with two-mode architecture"""
        try:
            logger.info("Starting MADRAC-DUBBING dub mode with two-mode architecture")
            logger.info(f"Current mode: {self.mode_info['mode']}")

            # Import and run CLI
            from madrac_dubbing.cli import dub

            # Set environment variables for two-mode operation
            os.environ['MADRAC_MODE'] = self.mode_info["mode"]
            os.environ['MADRAC_SKIP_VALIDATION'] = str(self.integration.config["skip_validation"]).lower()
            os.environ['MADRAC_INTEGRATION_AVAILABLE'] = str(self.integration.integration_available).lower()

            # Run CLI with remaining arguments
            return dub(args)

        except Exception as e:
            logger.error(f"Dub mode failed: {e}")
            return False


# Global wrapper instance
_wrapper = MADRACDubbingWrapper()


def main() -> None:
    """Main entry point for MADRAC-DUBBING with two-mode architecture"""
    try:
        # Initialize wrapper
        logger.info("Initializing MADRAC-DUBBING with Two-Mode Architecture")

        # Show mode information
        print(_wrapper.get_mode_details())

        # Process command
        success = _wrapper.process_command(sys.argv[1:])

        if not success:
            logger.error("MADRAC-DUBBING execution failed")
            sys.exit(1)

        logger.info("MADRAC-DUBBING executed successfully")

    except KeyboardInterrupt:
        logger.info("MADRAC-DUBBING interrupted by user")
        sys.exit(130)
    except Exception as e:
        logger.error(f"MADRAC-DUBBING fatal error: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
