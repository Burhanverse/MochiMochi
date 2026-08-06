"""Mochibot CLI main module."""

import asyncio
import logging
import sys

from bot import create_bot
from handlers.stickers import session_cleanup_loop
from resources import resources
from storage import storage

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger("mochibot")
logging.getLogger("pyrogram").setLevel(logging.WARNING)


async def async_main():
    app, _bot_token, _owner_id = create_bot()
    async with resources:
        asyncio.create_task(session_cleanup_loop())
        await app.start()
        logger.info("Starting Mochibot (Sticker Pack Bot)...")
        logger.info(f"Loaded {len(storage.get_authorized_chats())} authorized chats.")
        logger.info(f"Config: {storage.config.to_dict()}")
        try:
            await asyncio.Event().wait()
        finally:
            await app.stop()


def main():
    try:
        asyncio.run(async_main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Mochibot stopped.")
    except Exception as e:
        logger.critical(f"Fatal error running mochibot: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()
