"""ZIP file document upload handler with Zip Slip prevention."""

import asyncio
import logging
import os
import tempfile
import zipfile
from pathlib import Path

from pyrogram import Client, filters
from pyrogram.enums import ChatType
from pyrogram.types import Message

from conversion.static import _convert_static_bytes_to_webp
from conversion.tgs import convert_to_whatsapp_animated
from conversion.tray import optimize_tray_icon
from resources import resources
from sticker_pack.filenames import (
    classify_sticker_files,
    sanitize_filename,
    split_into_chunks,
)
from storage import storage

logger = logging.getLogger(__name__)


def register_zip_upload_handlers(app: Client):

    @app.on_message(filters.document & (filters.group | filters.private))
    async def process_zip_upload(client: Client, message: Message):
        if message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP] and not storage.is_authorized(message.chat.id):
            await message.reply_text("❌ This chat is not authorized.")
            return
        if not message.document.file_name or not message.document.file_name.lower().endswith('.zip'):
            return

        msg = await message.reply_text("📥 Downloading ZIP file...")

        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_path = Path(tmpdir)
                zip_path = await message.download(file_name=str(tmp_path / message.document.file_name))

                await msg.edit_text("📦 Extracting ZIP file...")
                extract_dir = tmp_path / "extracted"
                extract_dir.mkdir()

                extract_dir_resolved = extract_dir.resolve()
                with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                    for member in zip_ref.infolist():
                        member_path = (extract_dir_resolved / member.filename).resolve()
                        if not str(member_path).startswith(str(extract_dir_resolved) + os.sep):
                            logger.warning(f"Zip Slip blocked: '{member.filename}'")
                            continue
                        zip_ref.extract(member, extract_dir)

                sticker_files = []
                for ext in ['*.webm', '*.tgs', '*.png', '*.jpg', '*.jpeg', '*.webp']:
                    sticker_files.extend(extract_dir.rglob(ext))

                if not sticker_files:
                    await msg.edit_text("❌ No supported sticker files found in the ZIP.")
                    return

                static_files, animated_files = classify_sticker_files(sticker_files)
                types_to_process = []
                if static_files:
                    types_to_process.append(("Static", static_files))
                if animated_files:
                    types_to_process.append(("Animated", animated_files))

                pack_name_base = message.document.file_name[:-4]
                author_name = message.from_user.first_name or "Telegram User"
                total_packs_sent = 0
                send_to_private = bool(message.caption and "private" in message.caption.lower())
                target_chat = (
                    message.from_user.id if send_to_private and message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP]
                    else message.chat.id
                )
                zip_sem = resources.get_cpu_semaphore()

                for type_name, files in types_to_process:
                    chunks = split_into_chunks(files, 30)
                    num_parts = len(chunks)

                    for part_num, chunk in enumerate(chunks, 1):
                        type_letter = type_name[0].lower()
                        part_title = pack_name_base + (f" - Part {part_num}" if num_parts > 1 else "")
                        processing_dir = tmp_path / f"processed_{type_letter}_{part_num}"
                        processing_dir.mkdir()
                        processed_count = 0

                        async def _convert_zip_file(sf, _sem=zip_sem):
                            async with _sem:
                                try:
                                    with open(sf, 'rb') as fh:
                                        fdata = fh.read()
                                    is_tgs = sf.suffix.lower() == '.tgs'
                                    if sf in animated_files:
                                        conv = await convert_to_whatsapp_animated(fdata, is_tgs)
                                    else:
                                        conv = await resources.run_cpu_bound(_convert_static_bytes_to_webp, fdata)
                                    conv_bytes = conv.getvalue()
                                    conv.close()
                                    return sf, conv_bytes, None
                                except Exception as exc:
                                    logger.error(f"Error processing {sf.name}: {exc}")
                                    return sf, None, str(exc)

                        _zip_tasks = [asyncio.create_task(_convert_zip_file(sf)) for sf in chunk]
                        _zip_done = 0
                        for _fut in asyncio.as_completed(_zip_tasks):
                            sf, data, _err = await _fut
                            _zip_done += 1
                            try:
                                part_suffix = f" (Part {part_num}/{num_parts})" if num_parts > 1 else ""
                                await msg.edit_text(f"📦 Processing {type_name}{part_suffix}: {_zip_done}/{len(chunk)}")
                            except Exception:
                                pass
                            if data is not None:
                                output_name = f"{sf.stem}_whatsapp.webp"
                                with open(processing_dir / output_name, 'wb') as fh:
                                    fh.write(data)
                                processed_count += 1

                        if processed_count == 0:
                            continue

                        tray_path = processing_dir / "tray.png"
                        try:
                            first_file = chunk[0]
                            with open(first_file, 'rb') as f:
                                tray_data = f.read()
                            is_animated = first_file in animated_files
                            optimized_tray = await resources.run_cpu_bound(optimize_tray_icon, tray_data, is_animated)
                            with open(tray_path, 'wb') as f:
                                f.write(optimized_tray.getvalue())
                            optimized_tray.close()
                        except Exception as e:
                            logger.warning(f"Could not create tray icon: {e}")

                        wasticker_name = f"{sanitize_filename(part_title)}.wasticker"
                        wasticker_path = tmp_path / wasticker_name
                        with zipfile.ZipFile(wasticker_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                            if tray_path.exists():
                                zipf.write(tray_path, 'tray.png')
                            zipf.writestr('author.txt', author_name.encode('utf-8'))
                            zipf.writestr('title.txt', part_title.encode('utf-8'))
                            for idx, webp_file in enumerate(sorted(processing_dir.glob("*.webp")), start=1):
                                zipf.write(webp_file, f"sticker_{idx:03d}.webp")

                        await msg.edit_text(f"📤 Uploading {type_name} sticker pack...")
                        part_suffix = f" (Part {part_num}/{num_parts})" if num_parts > 1 else ""
                        caption = f"✅ {type_name} Stickers{part_suffix}\nProcessed {processed_count} stickers from {message.document.file_name}"

                        await client.send_document(
                            chat_id=target_chat,
                            document=str(wasticker_path),
                            file_name=wasticker_name,
                            caption=caption,
                            disable_notification=True
                        )
                        total_packs_sent += 1

                if total_packs_sent == 0:
                    await msg.edit_text("❌ Failed to process any sticker packs from the ZIP.")
                else:
                    try:
                        await msg.delete()
                    except Exception:
                        pass

        except Exception as e:
            logger.error(f"ZIP processing failed: {e}")
            try:
                await msg.edit_text(f"Processing failed: {e!s}")
            except Exception:
                pass
