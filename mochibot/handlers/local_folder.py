"""Local sticker directory /local and /upload handlers."""

import asyncio
import logging
import shutil
import zipfile
from pathlib import Path

from pyrogram import Client, filters
from pyrogram.enums import ChatType
from pyrogram.types import Message

from conversion.static import _convert_static_bytes_to_webp
from conversion.tgs import convert_to_whatsapp_animated
from conversion.tray import optimize_tray_icon
from resources import resources
from sticker_pack.filenames import classify_sticker_files, split_into_chunks
from storage import storage

logger = logging.getLogger(__name__)


def register_local_handlers(app: Client):

    @app.on_message(filters.command("upload") & (filters.group | filters.private))
    async def upload_wasticker_files(client: Client, message: Message):
        if message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP] and not storage.is_authorized(message.chat.id):
            await message.reply_text("❌ This chat is not authorized.")
            return

        packs_dir = Path("wasticker_packs")
        if not packs_dir.exists():
            await message.reply_text("❌ No wasticker_packs folder found. Process some stickers first with `/wast`.")
            return

        wasticker_files = list(packs_dir.glob("*.wasticker"))
        if not wasticker_files:
            await message.reply_text("❌ No .wasticker files found in the wasticker_packs folder.")
            return

        msg = await message.reply_text(f"📤 Found {len(wasticker_files)} .wasticker file(s). Uploading...")
        send_to_private = "private" in message.text.lower()
        target_chat = message.from_user.id if send_to_private and message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP] else message.chat.id

        uploaded_count = 0
        for i, wasticker_file in enumerate(wasticker_files, 1):
            try:
                await msg.edit_text(f"📤 Uploading {i}/{len(wasticker_files)}: {wasticker_file.name}")
                await client.send_document(
                    chat_id=target_chat,
                    document=str(wasticker_file),
                    file_name=wasticker_file.name,
                    caption=f"Sticker Pack: {wasticker_file.stem}",
                    disable_notification=True
                )
                uploaded_count += 1
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Failed to upload {wasticker_file.name}: {e}")
                continue

        cleanup_success = False
        try:
            if packs_dir.exists():
                shutil.rmtree(packs_dir, ignore_errors=True)
                cleanup_success = True
        except Exception as ce:
            logger.warning(f"Cleanup error: {ce}")

        success_msg = f"✅ Uploaded {uploaded_count}/{len(wasticker_files)} sticker packs!"
        if cleanup_success:
            success_msg += "\n🗑️ Cleaned up temporary files."
        await message.reply_text(success_msg)
        try:
            await msg.delete()
        except Exception:
            pass

    @app.on_message(filters.command("local") & (filters.group | filters.private))
    async def process_local_folder(client: Client, message: Message):
        if message.chat.type in [ChatType.GROUP, ChatType.SUPERGROUP] and not storage.is_authorized(message.chat.id):
            await message.reply_text("❌ This chat is not authorized.")
            return

        stickers_dir = Path("stickers")
        if not stickers_dir.exists():
            await message.reply_text("❌ No 'stickers' folder found. Create one and put .webm/.tgs/.png/.jpg/.webp files there.")
            return

        sticker_files = []
        for ext in ['*.webm', '*.tgs', '*.png', '*.jpg', '*.jpeg', '*.webp']:
            sticker_files.extend(stickers_dir.glob(ext))

        if not sticker_files:
            await message.reply_text("❌ No sticker files found. Supported: .webm .tgs .png .jpg .jpeg .webp")
            return

        msg = await message.reply_text(f"📦 Processing {len(sticker_files)} local sticker files...")

        try:
            static_files, animated_files = classify_sticker_files(sticker_files)
            types_to_process = []
            if static_files:
                types_to_process.append(("Static", static_files))
            if animated_files:
                types_to_process.append(("Animated", animated_files))

            total_processed = 0
            zip_paths = []
            local_sem = resources.get_cpu_semaphore()

            for type_name, files in types_to_process:
                chunks = split_into_chunks(files, 30)
                num_parts = len(chunks)
                for part_num, chunk in enumerate(chunks, 1):
                    type_letter = type_name[0].lower()
                    processing_dir = Path(f"processed_{type_letter}_{part_num}")
                    processing_dir.mkdir(exist_ok=True)
                    processed_count = 0

                    async def _convert_local_file(sf, _sem=local_sem):
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

                    _local_tasks = [asyncio.create_task(_convert_local_file(sf)) for sf in chunk]
                    _local_done = 0
                    for _fut in asyncio.as_completed(_local_tasks):
                        sf, data, _err = await _fut
                        _local_done += 1
                        try:
                            part_suffix = f" (Part {part_num}/{num_parts})" if num_parts > 1 else ""
                            await msg.edit_text(f"📦 Processing {type_name}{part_suffix}: {_local_done}/{len(chunk)}")
                        except Exception:
                            pass
                        if data is not None:
                            output_name = f"{sf.stem}_whatsapp.webp"
                            with open(processing_dir / output_name, 'wb') as fh:
                                fh.write(data)
                            processed_count += 1

                    if processed_count == 0:
                        shutil.rmtree(processing_dir, ignore_errors=True)
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

                    part_title = f"Converted {type_name}" + (f" Part {part_num}" if num_parts > 1 else "")
                    zip_name = f"whatsapp_{type_name.lower()}_{part_num}.wastickers"
                    zip_path = Path(zip_name)
                    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                        if tray_path.exists():
                            zipf.write(tray_path, 'tray.png')
                        author_name = message.from_user.first_name or "Telegram User"
                        zipf.writestr('author.txt', author_name.encode('utf-8'))
                        zipf.writestr('title.txt', part_title.encode('utf-8'))
                        for webp_file in processing_dir.glob("*.webp"):
                            zipf.write(webp_file, f"sticker_{webp_file.stem[-8:]}.webp")

                    zip_paths.append(zip_name)
                    total_processed += processed_count
                    shutil.rmtree(processing_dir, ignore_errors=True)

            if total_processed > 0:
                await msg.edit_text(f"✅ Processed {total_processed} stickers! ZIP files: {', '.join(zip_paths)}")
            else:
                await msg.edit_text("❌ Failed to process any stickers.")

        except Exception as e:
            logger.error(f"Local processing failed: {e}")
            await msg.edit_text(f"❌ Processing failed: {e!s}")
        finally:
            try:
                await msg.delete()
            except Exception:
                pass
