"""Bot application construction and handler binding."""

import logging
import os
import sys

from dotenv import load_dotenv
from pyrogram import Client

from handlers.auth import register_auth_handlers
from handlers.local_folder import register_local_handlers
from handlers.settings import register_settings_handlers
from handlers.stickers import register_sticker_handlers
from handlers.zip_upload import register_zip_upload_handlers

logger = logging.getLogger(__name__)


def create_bot() -> tuple[Client, str, int]:
    """Loads environment variables and constructs Kurigram Client."""
    load_dotenv()

    api_id = os.getenv("API_ID")
    api_hash = os.getenv("API_HASH")
    bot_token = os.getenv("BOT_TOKEN")
    owner_id_raw = os.getenv("OWNER_ID", "0")
    owner_id = int(owner_id_raw) if owner_id_raw.isdigit() else 0

    if not api_id or not api_hash or not bot_token:
        logger.error("Missing environment variables in .env file!")
        logger.info("Please create a .env file with API_ID, API_HASH, and BOT_TOKEN")
        sys.exit(1)
    if not owner_id:
        logger.warning("OWNER_ID not set in .env. Authorization commands will be disabled!")

    app = Client(
        "sticker_pack_bot",
        api_id=int(api_id),
        api_hash=api_hash,
        bot_token=bot_token
    )

    # Register handlers
    register_auth_handlers(app, owner_id)
    register_settings_handlers(app, owner_id)
    register_sticker_handlers(app, bot_token)
    register_zip_upload_handlers(app)
    register_local_handlers(app)

    return app, bot_token, owner_id
