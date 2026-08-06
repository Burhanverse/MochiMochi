"""Storage manager for persistent configuration and authorized chat lists."""

import json
import logging

from config import AUTHORIZED_CHATS_FILE, CONFIG_DEFAULTS, CONFIG_FILE, BotConfig

logger = logging.getLogger(__name__)


class StorageManager:
    """Manages persistent state for authorized chats and bot resource configuration."""

    def __init__(self):
        self._authorized_chats: set[int] = set()
        self._config: BotConfig = BotConfig()
        self.load_all()

    def load_all(self):
        self.load_authorized_chats()
        self.load_config()

    def load_authorized_chats(self):
        try:
            if AUTHORIZED_CHATS_FILE.exists():
                with open(AUTHORIZED_CHATS_FILE, "r") as f:
                    self._authorized_chats = set(json.load(f))
            else:
                self._authorized_chats = set()
        except Exception as e:
            logger.error(f"Error loading authorized chats: {e}")
            self._authorized_chats = set()

    def save_authorized_chats(self):
        try:
            with open(AUTHORIZED_CHATS_FILE, "w") as f:
                json.dump(list(self._authorized_chats), f)
            logger.info("Authorized chats saved.")
        except Exception as e:
            logger.error(f"Error saving authorized chats: {e}")

    def is_authorized(self, chat_id: int) -> bool:
        return chat_id in self._authorized_chats

    def add_authorized_chat(self, chat_id: int):
        self._authorized_chats.add(chat_id)
        self.save_authorized_chats()

    def remove_authorized_chat(self, chat_id: int):
        self._authorized_chats.discard(chat_id)
        self.save_authorized_chats()

    def get_authorized_chats(self) -> set[int]:
        return set(self._authorized_chats)

    def load_config(self):
        try:
            if CONFIG_FILE.exists():
                with open(CONFIG_FILE, "r") as f:
                    data = json.load(f)
                self._config = BotConfig.from_dict(data)
            else:
                self._config = BotConfig()
        except Exception as e:
            logger.error(f"Error loading config: {e}")
            self._config = BotConfig()

    def save_config(self):
        try:
            with open(CONFIG_FILE, "w") as f:
                json.dump(self._config.to_dict(), f, indent=2)
            logger.info(f"Config saved: {self._config.to_dict()}")
        except Exception as e:
            logger.error(f"Error saving config: {e}")

    @property
    def config(self) -> BotConfig:
        return self._config

    def get(self, key: str, default=None):
        cfg_dict = self._config.to_dict()
        return cfg_dict.get(key, default if default is not None else CONFIG_DEFAULTS.get(key))

    def update_config(self, key: str, value: int):
        cfg_dict = self._config.to_dict()
        cfg_dict[key] = value
        self._config = BotConfig.from_dict(cfg_dict)
        self.save_config()

    def reset_config(self):
        self._config = BotConfig()
        self.save_config()


# Global default instance
storage = StorageManager()
