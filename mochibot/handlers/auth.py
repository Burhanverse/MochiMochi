"""Authorization commands for bot owner."""

import logging

from pyrogram import Client, filters
from pyrogram.types import Message

from storage import storage

logger = logging.getLogger(__name__)


def register_auth_handlers(app: Client, owner_id: int):

    @app.on_message(filters.command("auth") & filters.private)
    async def authorize_chat(client: Client, message: Message):
        if message.from_user.id != owner_id:
            await message.reply_text("❌ Only the bot owner can use this command.")
            return
        if len(message.command) < 2:
            await message.reply_text("Usage: `/auth <chat_id>`")
            return
        try:
            chat_id = int(message.command[1])
            storage.add_authorized_chat(chat_id)
            await message.reply_text(f"✅ Chat `{chat_id}` authorized.")
        except ValueError:
            await message.reply_text("❌ Invalid chat ID.")

    @app.on_message(filters.command("deauth") & filters.private)
    async def deauthorize_chat(client: Client, message: Message):
        if message.from_user.id != owner_id:
            await message.reply_text("❌ Only the bot owner can use this command.")
            return
        if len(message.command) < 2:
            await message.reply_text("Usage: `/deauth <chat_id>`")
            return
        try:
            chat_id = int(message.command[1])
            storage.remove_authorized_chat(chat_id)
            await message.reply_text(f"✅ Chat `{chat_id}` deauthorized.")
        except ValueError:
            await message.reply_text("❌ Invalid chat ID.")

    @app.on_message(filters.command("listauth") & filters.private)
    async def list_authorized_chats(client: Client, message: Message):
        if message.from_user.id != owner_id:
            await message.reply_text("❌ Only the bot owner can use this command.")
            return
        auth_chats = storage.get_authorized_chats()
        if not auth_chats:
            await message.reply_text("No authorized chats.")
        else:
            chats_list = "\n".join(str(c) for c in sorted(auth_chats))
            await message.reply_text(f"Authorized chats:\n`{chats_list}`")
