"""MADRAC Dubbing Extension - Main Application"""
__version__ = "1.0.0-rc1"
__author__ = "MADRAC Team"

from .pipeline.models import DubbingJob, DubbingConfig, DubbingStatus

__all__ = ["DubbingJob", "DubbingConfig", "DubbingStatus", "__version__"]
