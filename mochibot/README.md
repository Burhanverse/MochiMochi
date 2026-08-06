# Mochibot 🍡

**Telegram to WhatsApp sticker pack converter bot.**

## 🚀 Quickstart

```bash
cp .env.example .env   # fill in your bot token and API keys
uv sync
uv run mochibot
```

## 🛠 Features & Commands

- `/wast` — Reply to a sticker to convert its pack to WhatsApp format (`.wasticker`)
- `/wast -z` — Convert and package stickers into a WebP `.zip` archive
- `/wast -z -c` — Package raw stickers into a `.zip` archive without conversion
- `/loadsticker` — Reply to a sticker to import it to WhatsApp
- `/converts` — Get raw converted `.webp` file for a sticker
- `/local` — Process sticker files from a local `stickers/` folder
- `/upload` — Upload all `.wasticker` files from `wasticker_packs/` folder
- `/settings` — Tune CPU and RAM concurrency limits (Owner only)
- `/help` & `/start` — Show help and instructions

## ⚡ Concurrency & Tuning

Resource settings (`max_concurrent`, `process_pool_workers`, `ffmpeg_threads`) are auto-tuned based on host CPU core count (`os.cpu_count()`) and can be adjusted at runtime via `/settings`.

Recommended settings for a 1–2 vCPU / 3GB VPS:
- `Parallel`: 1–2
- `TGS Workers`: 1
- `FFmpeg`: 1
