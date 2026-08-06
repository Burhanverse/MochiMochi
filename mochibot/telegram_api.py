"""Telegram Bot API helpers and raw Kurigram calls."""

import logging
from io import BytesIO

from resources import resources

logger = logging.getLogger(__name__)

_MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024  # 20 MB cap


async def download_file_by_id(bot_token: str, file_id: str) -> bytes:
    """Downloads a Telegram file by file_id using chunked streaming to cap RAM usage."""
    session = await resources.get_http_session()

    get_url = f"https://api.telegram.org/bot{bot_token}/getFile"
    async with session.get(get_url, params={"file_id": file_id}) as resp:
        data = await resp.json()
        if not data.get("ok"):
            raise Exception(data.get("description", "Unknown error in getFile"))
        file_path = data["result"]["file_path"]

    download_url = f"https://api.telegram.org/file/bot{bot_token}/{file_path}"
    CHUNK = 64 * 1024
    async with session.get(download_url) as resp:
        if resp.status != 200:
            raise Exception(f"Failed to download file: HTTP {resp.status}")
        content_length = resp.headers.get("Content-Length")
        if content_length and int(content_length) > _MAX_DOWNLOAD_BYTES:
            raise Exception(
                f"File too large ({int(content_length) // 1024}KB), refusing download"
            )
        buf = BytesIO()
        async for chunk in resp.content.iter_chunked(CHUNK):
            buf.write(chunk)
            if buf.tell() > _MAX_DOWNLOAD_BYTES:
                buf.close()
                raise Exception("File exceeded 20MB limit mid-download, aborting")
        val = buf.getvalue()
        buf.close()
        return val


async def get_sticker_set_via_bot_api(bot_token: str, name: str) -> dict:
    """Fetches sticker set info using Telegram Bot API HTTP endpoint."""
    session = await resources.get_http_session()
    url = f"https://api.telegram.org/bot{bot_token}/getStickerSet"
    async with session.get(url, params={"name": name}) as resp:
        data = await resp.json()
        if not data.get("ok"):
            raise Exception(data.get("description", "Unknown error in getStickerSet"))
        return data["result"]


async def fetch_pack_emoji_map(app, set_name: str) -> dict:
    """Fetches pack emoji map via kurigram raw MTProto calls."""
    try:
        from pyrogram import raw as _raw
        result = await app.invoke(
            _raw.functions.messages.GetStickerSet(
                stickerset=_raw.types.InputStickerSetShortName(short_name=set_name),
                hash=0,
            )
        )
        doc_emoji: dict[int, list[str]] = {}
        for pack in result.packs:
            for doc_id in pack.documents:
                lst = doc_emoji.setdefault(doc_id, [])
                if pack.emoticon not in lst and len(lst) < 3:
                    lst.append(pack.emoticon)

        index_map: dict[int, list[str]] = {}
        for idx, doc in enumerate(result.documents):
            emojis = doc_emoji.get(doc.id)
            if emojis:
                index_map[idx] = emojis

        logger.info(
            f"fetch_pack_emoji_map '{set_name}': "
            f"{sum(len(v) for v in index_map.values())} total emojis across "
            f"{len(index_map)} stickers"
        )
        return index_map
    except Exception as e:
        logger.warning(f"fetch_pack_emoji_map failed for '{set_name}': {e}")
        return {}
