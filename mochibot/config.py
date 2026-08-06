"""Configuration defaults, dataclasses, and WhatsApp sticker format constants."""

import logging
import os
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Base directory
BASE_DIR = Path(__file__).resolve().parent
AUTHORIZED_CHATS_FILE = BASE_DIR / "authorized_chats.json"
CONFIG_FILE = BASE_DIR / "config.json"
APP_URL = "http://github.com/maxcodl/MochiMochi/releases/"

# ── WhatsApp sticker hard limits ─────────────────────────────────────────────
WA_MAX_BYTES = 499_000
WA_ANIM_TARGET = 494_000
WA_MAX_ANIM_DURATION_MS = 9_800

# ── Sticker thumbnail settings ────────────────────────────────────────────────
STICKER_THUMB_SIZE = 100
STICKER_THUMB_QUALITY = 80

# ── Host CPU-aware default settings ──────────────────────────────────────────
# Dynamically sized to host core count so 1-2 vCPU / 3GB VPS boxes don't peg CPU to 100%
_CPU_COUNT = os.cpu_count() or 2

DEFAULT_MAX_CONCURRENT = max(1, min(4, _CPU_COUNT - 1 if _CPU_COUNT > 1 else 1))
DEFAULT_PROCESS_POOL_WORKERS = max(1, min(2, _CPU_COUNT // 2 if _CPU_COUNT > 1 else 1))
DEFAULT_FFMPEG_THREADS = 1
DEFAULT_TGS_RENDER_TIMEOUT = 60

CONFIG_DEFAULTS = {
    "max_concurrent": DEFAULT_MAX_CONCURRENT,        # simultaneous sticker downloads/conversions
    "process_pool_workers": DEFAULT_PROCESS_POOL_WORKERS,  # TGS lottie render worker processes
    "ffmpeg_threads": DEFAULT_FFMPEG_THREADS,        # threads passed for video decode
    "tgs_render_timeout": DEFAULT_TGS_RENDER_TIMEOUT, # seconds before an in-process TGS render is aborted
}


@dataclass
class BotConfig:
    max_concurrent: int = DEFAULT_MAX_CONCURRENT
    process_pool_workers: int = DEFAULT_PROCESS_POOL_WORKERS
    ffmpeg_threads: int = DEFAULT_FFMPEG_THREADS
    tgs_render_timeout: int = DEFAULT_TGS_RENDER_TIMEOUT

    def to_dict(self) -> dict:
        return {
            "max_concurrent": self.max_concurrent,
            "process_pool_workers": self.process_pool_workers,
            "ffmpeg_threads": self.ffmpeg_threads,
            "tgs_render_timeout": self.tgs_render_timeout,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "BotConfig":
        merged = {**CONFIG_DEFAULTS, **data}
        return cls(
            max_concurrent=merged.get("max_concurrent", DEFAULT_MAX_CONCURRENT),
            process_pool_workers=merged.get("process_pool_workers", DEFAULT_PROCESS_POOL_WORKERS),
            ffmpeg_threads=merged.get("ffmpeg_threads", DEFAULT_FFMPEG_THREADS),
            tgs_render_timeout=merged.get("tgs_render_timeout", DEFAULT_TGS_RENDER_TIMEOUT),
        )
