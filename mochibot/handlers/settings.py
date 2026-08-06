"""Resource tuning /settings command handlers."""

import logging
import os

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import CONFIG_DEFAULTS
from resources import resources
from storage import storage

logger = logging.getLogger(__name__)

_SETTINGS_META = {
    "max_concurrent": {
        "label": "Parallel",
        "desc": "Downloads/Conversions",
        "min": 1, "max": 20, "step": 1, "unit": ""
    },
    "process_pool_workers": {
        "label": "TGS Workers",
        "desc": "Render Processes",
        "min": 1, "max": 8, "step": 1, "unit": ""
    },
    "ffmpeg_threads": {
        "label": "FFmpeg",
        "desc": "Decode Threads",
        "min": 1, "max": 16, "step": 1, "unit": ""
    },
    "tgs_render_timeout": {
        "label": "Timeout",
        "desc": "TGS Render",
        "min": 10, "max": 300, "step": 10, "unit": "s"
    },
}


def _settings_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for key, meta in _SETTINGS_META.items():
        val = storage.get(key)
        unit = meta["unit"]
        rows.append([
            InlineKeyboardButton("➖", callback_data=f"cfg_dec_{key}"),
            InlineKeyboardButton(f"{meta['label']}: {val}{unit}",
                                 callback_data=f"cfg_noop_{key}"),
            InlineKeyboardButton("➕", callback_data=f"cfg_inc_{key}")
        ])
    rows.append([InlineKeyboardButton("Reset to defaults", callback_data="cfg_reset")])
    return InlineKeyboardMarkup(rows)


def _settings_text() -> str:
    cpu_count = os.cpu_count() or 1
    lines = [f"**Resource & CPU settings** (Host Cores: `{cpu_count}`)\n"]
    for key, meta in _SETTINGS_META.items():
        val = storage.get(key)
        default = CONFIG_DEFAULTS[key]
        unit = meta["unit"]
        marker = "" if val == default else " ✏️"
        lines.append(f"• {meta['label']}: `{val}{unit}`{marker}")
    lines.append("\nUse the buttons below to tune up or down.")
    lines.append("💡 *Recommendation for 1–2 vCPU VPS:* `Parallel: 1-2`, `TGS Workers: 1`, `FFmpeg: 1`.")
    return "\n".join(lines)


def register_settings_handlers(app: Client, owner_id: int):

    @app.on_message(filters.command("settings") & filters.private)
    async def settings_command(client: Client, message: Message):
        if message.from_user.id != owner_id:
            await message.reply_text("❌ Only the bot owner can adjust settings.")
            return
        await message.reply_text(_settings_text(), reply_markup=_settings_keyboard())

    @app.on_callback_query(filters.regex(r"^cfg_(inc|dec|reset|noop)_?(.*)$"))
    async def settings_callback(client: Client, callback_query):
        if callback_query.from_user.id != owner_id:
            await callback_query.answer("Not authorised.", show_alert=True)
            return

        action = callback_query.matches[0].group(1)
        key = callback_query.matches[0].group(2)

        if action == "noop":
            await callback_query.answer()
            return

        if action == "reset":
            storage.reset_config()
            resources.rebuild_process_pool(storage.get("process_pool_workers"))
            resources.rebuild_cpu_pool(storage.get("max_concurrent"))
            await callback_query.answer("Reset to defaults.")
            try:
                await callback_query.message.edit_text(_settings_text(), reply_markup=_settings_keyboard())
            except Exception:
                pass
            return

        if key not in _SETTINGS_META:
            await callback_query.answer("Unknown setting.", show_alert=True)
            return

        meta = _SETTINGS_META[key]
        current = storage.get(key)
        step = meta["step"]

        if action == "inc":
            new_val = min(current + step, meta["max"])
        else:
            new_val = max(current - step, meta["min"])

        if new_val == current:
            await callback_query.answer(f"Already at {'maximum' if action == 'inc' else 'minimum'}.")
            return

        storage.update_config(key, new_val)

        if key == "process_pool_workers":
            resources.rebuild_process_pool(new_val)
        if key == "max_concurrent":
            resources.rebuild_cpu_pool(new_val)

        await callback_query.answer(f"{meta['label']} → {new_val}{meta['unit']}")
        try:
            await callback_query.message.edit_text(_settings_text(), reply_markup=_settings_keyboard())
        except Exception:
            pass
