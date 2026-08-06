"""Filename sanitization, chunking, and sticker classification helpers."""

import re
from pathlib import Path

from PIL import Image


class SimpleSticker:
    def __init__(self, file_id: str, is_animated: bool, is_video: bool, emojis):
        self.file_id = file_id
        self.is_animated = is_animated
        self.is_video = is_video
        if isinstance(emojis, str):
            self.emojis: list[str] = [emojis] if emojis else ["\U0001F600"]
        else:
            self.emojis: list[str] = list(emojis)[:3] if emojis else ["\U0001F600"]

    @property
    def emoji(self) -> str:
        return self.emojis[0] if self.emojis else "\U0001F600"


def sanitize_filename(name: str) -> str:
    name = name.lstrip("@")
    name = name.replace(".", "")
    name = name.encode("ascii", "ignore").decode("ascii")
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    name = re.sub(r'[\s-]+', '_', name).strip("_")
    return name[:50] if name else "sticker_pack"


def _format_elapsed(seconds: float) -> str:
    """Human-readable elapsed time for pack captions, e.g. '8m 12s' or '43s'."""
    total = round(seconds)
    m, s = divmod(total, 60)
    return f"{m}m {s}s" if m else f"{s}s"


def split_into_chunks(items: list, max_per_chunk: int = 30) -> list:
    return [items[i:i + max_per_chunk] for i in range(0, len(items), max_per_chunk)]


def split_stickers_by_type(stickers: list):
    static = [s for s in stickers if not (s.is_animated or s.is_video)]
    animated = [s for s in stickers if s.is_animated or s.is_video]
    return static, animated


def classify_sticker_files(files: list) -> tuple[list, list]:
    static_files = []
    animated_files = []
    for f in files:
        f_path = Path(f)
        ext = f_path.suffix.lower()
        if ext in ['.webm', '.tgs']:
            animated_files.append(f_path)
        elif ext == '.webp':
            try:
                with Image.open(f_path) as img:
                    if getattr(img, "is_animated", False):
                        animated_files.append(f_path)
                    else:
                        static_files.append(f_path)
            except Exception:
                static_files.append(f_path)
        else:
            static_files.append(f_path)
    return static_files, animated_files
