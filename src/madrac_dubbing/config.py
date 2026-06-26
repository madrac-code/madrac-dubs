"""Configuration management"""
import os
import json
from pathlib import Path
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class Config:
    """Application configuration"""
    tts_engine: str = "edge"
    api_host: str = "127.0.0.1"
    api_port: int = 5000
    default_language: str = "es"
    default_voice: str = "female"
    reduce_vocals_default: float = 0.7
    target_lufs: float = -20.0

    # Two-mode architecture settings
    standalone_mode: bool = field(default=False)
    require_madrac_subs: bool = field(default=False)
    skip_validation: bool = field(default=False)

    # Workspace settings
    workspace_path: Optional[str] = field(default=None)
    workspace_enabled: bool = field(default=True)

    def __post_init__(self):
        env_mode = os.environ.get('MADRAC_OPERATING_MODE', '').lower()
        if env_mode == 'standalone':
            self.standalone_mode = True
            self.require_madrac_subs = False
        elif env_mode == 'integrated':
            self.standalone_mode = False
            self.require_madrac_subs = True

        if os.environ.get('MADRAC_SKIP_VALIDATION', '').lower() == 'true':
            self.skip_validation = True

    @classmethod
    def load(cls, config_path: Optional[Path] = None):
        if config_path and config_path.exists():
            with open(config_path, 'r') as f:
                data = json.load(f)
                return cls(**{k: v for k, v in data.items() if hasattr(cls, k)})
        return cls()

    def save(self, config_path: Path):
        config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(config_path, 'w') as f:
            json.dump(self.__dict__, f, indent=2)

    def to_dict(self):
        return self.__dict__


_config = Config()


def get_config() -> Config:
    return _config


def set_config(config: Config):
    global _config
    _config = config
