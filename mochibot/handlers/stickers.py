"""Sticker processing handlers for /loadsticker, /converts, and /wast."""

import asyncio
import logging
import time
import traceback
from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile

from pyrogram import Client, filters
from pyrogram.enums import ChatType
from pyrogram.errors import FloodWait
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from conversion.static import _convert_static_bytes_to_webp
from conversion.tgs import convert_to_whatsapp_animated
from conversion.tray import optimize_tray_icon
from resources import resources
from sticker_pack.filenames import SimpleSticker, _format_elapsed, sanitize_filename
from sticker_pack.wasticker_zip import (
    _build_wasticker_zip_from_valid_entries,
    create_simple_zip,
    create_wastickers_zip,
    generate_thumbnail_from_webp_bytes,
)
from storage import storage
from telegram_api import (
    download_file_by_id,
    fetch_pack_emoji_map,
    get_sticker_set_via_bot_api,
)

logger = logging.getLogger(__name__)

# ── Per-user rate limiting & active sessions ─────────────────────────────────
_user_last_command: dict[int, float] = {}
_RATE_LIMIT_SECONDS = 10
_RATE_LIMIT_PRUNE_INTERVAL = 3600

active_sticker_sessions = {}
_SESSION_TTL = 3600


def _prune_rate_limit_dict():
    cutoff = time.monotonic() - _RATE_LIMIT_PRUNE_INTERVAL
    stale = [uid for uid, ts in _user_last_command.items() if ts < cutoff]
    for uid in stale:
        del _user_last_command[uid]
    if stale:
        logger.debug(f"Pruned {len(stale)} stale rate-limit entries")


def _is_rate_limited(user_id: int) -> bool:
    _prune_rate_limit_dict()
    now = time.monotonic()
    last = _user_last_command.get(user_id, 0)
    if now - last < _RATE_LIMIT_SECONDS:
        return True
    _user_last_command[user_id] = now
    return False


async def session_cleanup_loop():
    """Background task: evict sticker sessions older than SESSION_TTL."""
    while True:
        await asyncio.sleep(300)
        cutoff = time.monotonic() - _SESSION_TTL
        stale = [k for k, v in active_sticker_sessions.items() if v.get("created_at", 0) < cutoff]
        for k in stale:
            active_sticker_sessions.pop(k, None)
        if stale:
            logger.info(f"Session cleanup: evicted {len(stale)} expired session(s)")


async def process_stickers(
    client: Client,
    bot_token: str,
    msg: Message,
    message_text: str,
    target_chat: int,
    set_title: str,
    stickers: list,
    use_simple_zip: bool,
    skip_conversion: bool,
    author_name: str,
    pack_name: str,
    send_to_private: bool,
    from_user_id: int
):
    try:
        _pack_start_time = time.monotonic()
        set_name_sanitized = sanitize_filename(set_title)
        if not stickers:
            await msg.edit_text("No stickers provided.")
            return

        first_sticker = stickers[0]
        tray_data = await download_file_by_id(bot_token, first_sticker.file_id)
        optimized_tray_bytes = await resources.run_cpu_bound(
            optimize_tray_icon, tray_data, first_sticker.is_animated or first_sticker.is_video
        )

        if use_simple_zip:
            await msg.edit_text(f"Creating {'raw' if skip_conversion else 'converted'} ZIP with {len(stickers)} stickers...")

            _last_edit_simple = [0.0]
            async def update_progress_simple(current, total):
                now = time.monotonic()
                if current != total and now - _last_edit_simple[0] < 4.0:
                    return
                _last_edit_simple[0] = now
                bar = "█" * int(current / total * 20) + "░" * (20 - int(current / total * 20))
                action = "Downloading" if skip_conversion else "Converting"
                try:
                    await msg.edit_text(f"{action} stickers\n\n{bar} {int(current/total*100)}%\nSticker {current}/{total}")
                except Exception:
                    pass

            zip_path, valid_count = await create_simple_zip(
                bot_token, set_name_sanitized, stickers, convert=not skip_conversion,
                progress_callback=update_progress_simple
            )
            await msg.edit_text("Uploading ZIP file...")
            mode_desc = "Raw stickers" if skip_conversion else "Converted stickers"
            elapsed = _format_elapsed(time.monotonic() - _pack_start_time)
            await client.send_document(
                chat_id=target_chat,
                document=str(zip_path),
                file_name=zip_path.name,
                caption=f"{mode_desc}: {valid_count} files\n{set_title}\nConverted in {elapsed}",
                disable_notification=True
            )
            try:
                zip_path.unlink(missing_ok=True)
            except Exception as ce:
                logger.warning(f"Cleanup error: {ce}")
            try:
                await msg.reply_text(f"Successfully zipped {valid_count} stickers!")
            except Exception:
                pass
            return

        has_animated = any(s.is_animated or s.is_video for s in stickers)
        type_name = "Animated" if has_animated else "Static"
        await msg.edit_text(f"Processing {len(stickers)} stickers as {type_name} pack...")

        _last_edit_pack = [0.0]
        async def update_progress_pack(current, total):
            now = time.monotonic()
            if current != total and now - _last_edit_pack[0] < 4.0:
                return
            _last_edit_pack[0] = now
            bar = "█" * int(current / total * 20) + "░" * (20 - int(current / total * 20))
            try:
                await msg.edit_text(
                    f"Processing **{type_name}** stickers\n\n{bar} {int(current/total*100)}%\nSticker {current}/{total}"
                )
            except Exception:
                pass

        type_letter = type_name[0].lower()
        prep_name = f"{set_name_sanitized}_{type_letter}_prep"
        valid_entries, stats = await create_wastickers_zip(
            bot_token, prep_name, optimized_tray_bytes, stickers, set_title,
            author=author_name, progress_callback=update_progress_pack,
            return_valid_results=True,
        )

        valid_count_total = len(valid_entries)
        if valid_count_total == 0:
            raise ValueError("No valid stickers found in the pack.")
        if valid_count_total < 3:
            logger.warning(f"Pack has only {valid_count_total} valid sticker(s) — WhatsApp requires ≥3. Skipping.")
            await msg.edit_text(f"❌ Only {valid_count_total} valid sticker(s) — WhatsApp requires at least 3.")
            return

        internal_name = f"{set_name_sanitized}_{type_letter}"
        zip_path = await resources.run_cpu_bound(
            _build_wasticker_zip_from_valid_entries,
            internal_name, optimized_tray_bytes, valid_entries, set_title, author_name, has_animated,
        )

        caption = f"{type_name} Stickers: {valid_count_total} stickers"
        if stats['skipped'] > 0:
            caption += f"\nSkipped {stats['skipped']} invalid"
            if stats.get('skipped_reasons'):
                reason_counts = {}
                for entry in stats['skipped_reasons']:
                    reason = entry.split(': ', 1)[1] if ': ' in entry else entry
                    reason_counts[reason] = reason_counts.get(reason, 0) + 1
                top_reasons = sorted(reason_counts.items(), key=lambda x: x[1], reverse=True)[:3]
                if top_reasons:
                    caption += "\nTop skip reasons:"
                    for reason, count in top_reasons:
                        caption += f"\n- {count}x {reason}"
        if valid_count_total > 30:
            caption += f"\n\n{valid_count_total} stickers"

        elapsed = _format_elapsed(time.monotonic() - _pack_start_time)
        caption += f"\nConverted in {elapsed}"

        try:
            await msg.edit_text(f"Uploading {type_name} pack ({valid_count_total} stickers)...")
        except Exception:
            pass

        while True:
            try:
                await client.send_document(
                    chat_id=target_chat,
                    document=str(zip_path),
                    file_name=zip_path.name,
                    caption=caption,
                    disable_notification=True
                )
                break
            except FloodWait as fw:
                logger.warning(f"FloodWait on send_document: waiting {fw.value}s")
                await asyncio.sleep(fw.value)

        try:
            zip_path.unlink(missing_ok=True)
        except Exception as ce:
            logger.warning(f"Cleanup error: {ce}")

        try:
            sent_success_msg = await msg.reply_text(f"Successfully sent {valid_count_total} stickers!")

            async def _delete_after_delay(target_msg, delay_secs: float = 10.0):
                try:
                    await asyncio.sleep(delay_secs)
                    await target_msg.delete()
                except Exception as de:
                    logger.debug(f"Could not auto-delete success message: {de}")

            asyncio.create_task(_delete_after_delay(sent_success_msg))
        except Exception:
            pass

    except FloodWait as e:
        logger.warning(f"FloodWait for pack {pack_name}: waiting {e.value}s")
        await asyncio.sleep(e.value)
        try:
            await msg.edit_text("⏳ Rate limit hit. Please try again in a moment.")
        except Exception:
            pass
    except Exception as e:
        logger.error(f"Pack conversion failed for pack {pack_name}: {e}")
        logger.error(traceback.format_exc())
        error_message = str(e).lower()
        if "bot was kicked" in error_message:
            await msg.edit_text("I've been kicked from the group. Please re-add me!")
        elif "not enough rights" in error_message or "chat write forbidden" in error_message:
            await msg.edit_text("I need permissions to send messages and files in this group!")
        elif "chat not found" in error_message:
            await msg.edit_text("I cannot access this group. Please ensure I'm added and have permissions!")
        else:
            await msg.edit_text(f"An unexpected error occurred: `{e!s}`")


def register_sticker_handlers(app: Client, bot_token: str):

    @app.on_message(filters.command("start") & (filters.group | filters.private))
    async def start_command(client: Client, message: Message):
        instructions = """
🤖 **Telegram to WhatsApp Sticker Converter**

**Commands:**
• `/wast` - Reply to any sticker to convert its entire pack to WhatsApp format
• `/wast CustomName` - Convert with a custom pack name
• `/wast -z` - Download and ZIP all stickers (converted to WebP)
• `/wast -z -c` - Download and ZIP raw stickers (no conversion)
• `/loadsticker` - Reply to a sticker to import it to WhatsApp
• `/loadsticker PackName` - Import to a named pack
• `/converts` - Reply to a sticker to get the raw converted .webp file
• `/local` - Process sticker files from a local 'stickers' folder
• `/upload` - Upload all .wasticker files from current directory
• `/help` - How to import stickers to WhatsApp
• `/settings` - Tune CPU/RAM usage (owner only)
• `/start` - Show this help message
"""
        await message.reply_text(instructions)

    @app.on_message(filters.command("help") & (filters.group | filters.private))
    async def help_command(client: Client, message: Message):
        help_text = """
**How to import stickers to WhatsApp**

Download the app using the button below, tap the .wasticker file, then tap "Import to WhatsApp".

If you're on iOS, tap the .wasticker file and it should prompt you directly.
"""
        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                "Download MochiMochi (Android)",
                url="https://github.com/maxcodl/MochiMochi/releases"
            )
        ]])
        await message.reply_text(help_text, reply_markup=keyboard)

    @app.on_message(filters.command("loadsticker") & (filters.group | filters.private))
    async def loadsticker_command(client: Client, message: Message):
        if message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP] and not storage.is_authorized(message.chat.id):
            await message.reply_text("❌ This chat is not authorized.")
            return
        if _is_rate_limited(message.from_user.id):
            await message.reply_text(f"⏳ Please wait {_RATE_LIMIT_SECONDS}s between commands.")
            return

        replied = message.reply_to_message
        if not replied or not replied.sticker:
            await message.reply_text(
                "❌ Please reply to a sticker with `/loadsticker` to import it to WhatsApp.\n\n"
                "**Usage:**\n"
                "• `/loadsticker` — import to default pack (My Stickers)\n"
                "• `/loadsticker MyPack` — import to a named pack"
            )
            return

        user_id = message.from_user.id
        sticker = replied.sticker
        is_animated = sticker.is_animated or sticker.is_video
        author_name = message.from_user.first_name or "Telegram User"
        args = message.command[1:] if len(message.command) > 1 else []
        pack_title = " ".join(args) if args else "My Stickers"
        msg = await message.reply_text("📥 Downloading sticker...")

        try:
            sticker_data = await download_file_by_id(bot_token, sticker.file_id)
            if not sticker_data or len(sticker_data) == 0:
                await msg.edit_text("❌ Failed to download sticker.")
                return

            await msg.edit_text("🔄 Converting to WhatsApp format...")
            if is_animated:
                converted = await convert_to_whatsapp_animated(sticker_data, sticker.is_animated)
            else:
                converted = await resources.run_cpu_bound(_convert_static_bytes_to_webp, sticker_data)
            converted_bytes = converted.getvalue()
            converted.close()

            tray_bytes = await resources.run_cpu_bound(optimize_tray_icon, converted_bytes, False)
            await msg.edit_text("📦 Packaging .wasticker file...")

            thumb_bytes = await resources.run_cpu_bound(generate_thumbnail_from_webp_bytes, converted_bytes)

            wasticker_bio = BytesIO()
            with ZipFile(wasticker_bio, 'w', ZIP_DEFLATED) as zipf:
                zipf.writestr('title.txt', pack_title)
                zipf.writestr('author.txt', author_name)
                zipf.writestr('tray.png', tray_bytes.getvalue())
                zipf.writestr('sticker_001.webp', converted_bytes)
                zipf.writestr('thumb_sticker_001.webp', thumb_bytes)
            wasticker_bio.seek(0)
            tray_bytes.close()

            wasticker_name = f"{sanitize_filename(pack_title)}.idwasticker"
            await msg.edit_text("Sending file...")
            caption = f"**{pack_title}**\nsticker ready to import"
            await client.send_document(
                chat_id=message.chat.id,
                document=wasticker_bio,
                file_name=wasticker_name,
                caption=caption,
                disable_notification=True
            )
            wasticker_bio.close()
            await msg.delete()

        except Exception as e:
            logger.error(f"Loadsticker failed for user {user_id}: {e}")
            logger.error(traceback.format_exc())
            await msg.edit_text(f"Failed to load sticker: `{e!s}`")

    @app.on_message(filters.command("converts") & (filters.group | filters.private))
    async def converts_command(client: Client, message: Message):
        if message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP] and not storage.is_authorized(message.chat.id):
            await message.reply_text("❌ This chat is not authorized.")
            return
        if _is_rate_limited(message.from_user.id):
            await message.reply_text(f"⏳ Please wait {_RATE_LIMIT_SECONDS}s between commands.")
            return

        replied = message.reply_to_message
        if not replied or not replied.sticker:
            await message.reply_text("❌ Please reply to a sticker with `/converts`.")
            return

        user_id = message.from_user.id
        sticker = replied.sticker
        is_animated = sticker.is_animated or sticker.is_video
        msg = await message.reply_text("📥 Downloading sticker for conversion...")

        try:
            sticker_data = await download_file_by_id(bot_token, sticker.file_id)
            if not sticker_data or len(sticker_data) == 0:
                await msg.edit_text("❌ Failed to download sticker.")
                return

            await msg.edit_text("🔄 Converting sticker to WebP format...")
            if is_animated:
                converted = await convert_to_whatsapp_animated(sticker_data, sticker.is_animated)
            else:
                converted = await resources.run_cpu_bound(_convert_static_bytes_to_webp, sticker_data)
            converted_bytes = converted.getvalue()
            converted.close()

            await msg.edit_text("Sending file...")
            file_bio = BytesIO(converted_bytes)
            file_bio.name = "converted_sticker.webp"
            await client.send_document(
                chat_id=message.chat.id,
                document=file_bio,
                caption="Here is your converted sticker file.",
                disable_notification=True
            )
            file_bio.close()
            await msg.delete()

        except Exception as e:
            logger.error(f"Converts failed for user {user_id}: {e}")
            logger.error(traceback.format_exc())
            await msg.edit_text(f"Failed to convert sticker: `{e!s}`")

    @app.on_message(filters.command("wast") & (filters.group | filters.private))
    async def convert_pack(client: Client, message: Message):
        if message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP] and not storage.is_authorized(message.chat.id):
            await message.reply_text("This chat is not authorized. Contact the bot owner to authorize it with `/auth <chat_id>` in private.")
            return
        if _is_rate_limited(message.from_user.id):
            await message.reply_text(f"⏳ Please wait {_RATE_LIMIT_SECONDS}s between commands.")
            return

        args = message.command[1:] if len(message.command) > 1 else []
        flags = [a for a in args if a.startswith('-')]
        name_parts = [a for a in args if not a.startswith('-')]

        use_simple_zip = '-z' in flags
        skip_conversion = '-c' in flags
        is_session_mode = '-s' in flags
        custom_name = " ".join(name_parts) if name_parts else None

        if skip_conversion and not use_simple_zip:
            await message.reply_text("Flag `-c` (no conversion) requires `-z` flag.\nUsage: `/wast -z -c`")
            return

        if is_session_mode:
            session_key = (message.chat.id, message.from_user.id)
            keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Make Sticker Pack", callback_data="make_pack")]])
            mode_text = " (Raw ZIP)" if (use_simple_zip and skip_conversion) else " (Converted ZIP)" if use_simple_zip else ""
            name_text = f" as **{custom_name}**" if custom_name else ""
            msg = await message.reply_text(
                f"Send stickers one by one to create a pack{name_text}{mode_text}.\n\nStickers added: 0",
                reply_markup=keyboard
            )
            active_sticker_sessions[session_key] = {
                "message_id": msg.id,
                "chat_id": message.chat.id,
                "stickers": [],
                "use_simple_zip": use_simple_zip,
                "skip_conversion": skip_conversion,
                "custom_name": custom_name,
                "source_message_text": message.text,
                "from_user": message.from_user,
                "created_at": time.monotonic(),
            }
            return

        replied = message.reply_to_message
        if not replied or not replied.sticker:
            await message.reply_text("❌ Please reply to a sticker with `/wast` or use `/wast -s` to select multiple stickers.")
            return
        if not replied.sticker.set_name:
            await message.reply_text("❌ This sticker doesn't belong to a pack.")
            return

        pack_name = replied.sticker.set_name
        mode_text = " (Raw ZIP)" if (use_simple_zip and skip_conversion) else " (Converted ZIP)" if use_simple_zip else ""
        msg = await message.reply_text(f"📦 Processing pack: **{pack_name}**{mode_text}...")

        try:
            sticker_set = await get_sticker_set_via_bot_api(bot_token, pack_name)
            set_title = custom_name if custom_name else sticker_set["title"]
            emoji_index_map = await fetch_pack_emoji_map(app, pack_name)

            seen_ids = set()
            stickers = []
            for idx, s in enumerate(sticker_set["stickers"]):
                fid = s["file_id"]
                if fid not in seen_ids:
                    seen_ids.add(fid)
                    emojis = emoji_index_map.get(idx) or [s.get("emoji", "\U0001F600")]
                    stickers.append(SimpleSticker(fid, s.get("is_animated", False), s.get("is_video", False), emojis))

            if len(seen_ids) < len(sticker_set["stickers"]):
                logger.warning(f"Removed {len(sticker_set['stickers']) - len(seen_ids)} duplicate stickers")

            send_to_private = "private" in message.text.lower() if message.text else False
            target_chat = message.from_user.id if send_to_private and message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP] else message.chat.id

            await process_stickers(
                client=client, bot_token=bot_token, msg=msg, message_text=message.text,
                target_chat=target_chat, set_title=set_title, stickers=stickers,
                use_simple_zip=use_simple_zip, skip_conversion=skip_conversion,
                author_name=message.from_user.first_name or "Telegram User",
                pack_name=pack_name, send_to_private=send_to_private,
                from_user_id=message.from_user.id
            )
        finally:
            try:
                await msg.delete()
            except Exception:
                pass

    @app.on_message(filters.sticker & (filters.group | filters.private))
    async def handle_individual_stickers(client: Client, message: Message):
        session_key = (message.chat.id, message.from_user.id)
        if session_key not in active_sticker_sessions:
            return
        if time.monotonic() - active_sticker_sessions[session_key].get("created_at", 0) > _SESSION_TTL:
            active_sticker_sessions.pop(session_key, None)
            return

        session = active_sticker_sessions[session_key]
        session["stickers"].append(SimpleSticker(
            message.sticker.file_id,
            message.sticker.is_animated,
            message.sticker.is_video,
            [message.sticker.emoji or "\U0001F600"]
        ))
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Make Sticker Pack", callback_data="make_pack")]])
        try:
            await client.edit_message_text(
                chat_id=session["chat_id"],
                message_id=session["message_id"],
                text=f"⏳ Send stickers one by one.\n\nStickers added: {len(session['stickers'])}",
                reply_markup=keyboard
            )
        except Exception:
            pass

    @app.on_callback_query(filters.regex("^make_pack$"))
    async def make_pack_callback(client: Client, callback_query):
        session_key = (callback_query.message.chat.id, callback_query.from_user.id)
        if session_key not in active_sticker_sessions:
            await callback_query.answer("No active session or you didn't start it.", show_alert=True)
            return

        session = active_sticker_sessions.pop(session_key)
        stickers_list = session["stickers"]
        if not stickers_list:
            await callback_query.answer("No stickers added!", show_alert=True)
            return

        await callback_query.answer("Processing stickers...")
        msg = callback_query.message
        await msg.edit_text("📦 Processing your custom sticker pack...", reply_markup=None)

        message_text = session["source_message_text"]
        from_user = session["from_user"]
        send_to_private = message_text and "private" in message_text.lower()
        target_chat = from_user.id if send_to_private and msg.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP] else msg.chat.id
        set_title = session["custom_name"] or "Random Stickers"

        try:
            await process_stickers(
                client=client, bot_token=bot_token, msg=msg, message_text=message_text,
                target_chat=target_chat, set_title=set_title,
                stickers=stickers_list,
                use_simple_zip=session["use_simple_zip"],
                skip_conversion=session["skip_conversion"],
                author_name=from_user.first_name or "Telegram User",
                pack_name=set_title, send_to_private=send_to_private,
                from_user_id=from_user.id
            )
        finally:
            try:
                await msg.delete()
            except Exception:
                pass
