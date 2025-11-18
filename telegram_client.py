"""Telegram bridge client for sending prompts to the A2A agent."""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass
from typing import Optional

from fasta2a.client import A2AClient, Message, UnexpectedResponseError
from fasta2a.schema import TextPart
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

LOGGER = logging.getLogger(__name__)


@dataclass
class BotConfig:
    """Holds runtime configuration for the Telegram bot."""

    token: str
    chat_id: int
    a2a_base_url: str = "http://localhost:7000"
    poll_interval: float = 1.5


class A2ATelegramBridge:
    """Minimal helper that talks to the A2A server."""

    def __init__(self, base_url: str, poll_interval: float = 1.5, client: Optional[A2AClient] = None) -> None:
        self._client = client or A2AClient(base_url=base_url)
        self._poll_interval = poll_interval
        self._final_states = {"completed", "failed", "canceled", "rejected"}

    async def ask_agent(self, prompt: str) -> str:
        """Send *prompt* to the agent and wait for a final response."""

        user_message = Message(
            role="user",
            parts=[TextPart(text=prompt, kind="text", metadata={})],
            kind="message",
            message_id=str(uuid.uuid4()),
            metadata={},
        )

        send_response = await self._client.send_message(message=user_message)
        task = send_response["result"]
        task_id = task["id"]
        current_task = task

        while current_task["status"]["state"] not in self._final_states:
            await asyncio.sleep(self._poll_interval)
            get_response = await self._client.get_task(task_id)
            current_task = get_response["result"]

        status = current_task["status"]["state"]
        if status == "completed":
            artifacts = current_task.get("artifacts") or []
            if artifacts and artifacts[0].get("parts"):
                first_part = artifacts[0]["parts"][0]
                return first_part.get("text", "(No text returned from agent)")
            return "(Agent completed without returning text.)"

        message = current_task.get("status", {}).get("message")
        raise RuntimeError(f"Task ended in state '{status}'. Message: {message}")


class TelegramBotHandlers:
    """Collection of handler callbacks bound to a chat id and bridge."""

    def __init__(self, chat_id: int, bridge: A2ATelegramBridge) -> None:
        self.chat_id = chat_id
        self.bridge = bridge

    async def _is_authorized(self, update: Update) -> bool:
        chat = update.effective_chat
        if not chat or chat.id != self.chat_id:
            if update.message:
                await update.message.reply_text("This bot is restricted to a single chat.")
            return False
        return True

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._is_authorized(update):
            return
        await update.message.reply_text("Hi! Send me a prompt and I'll forward it to the agent.")

    async def handle_text(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if not await self._is_authorized(update):
            return

        assert update.message  # pragma: no cover - guaranteed when handler triggers
        await context.bot.send_chat_action(chat_id=self.chat_id, action=ChatAction.TYPING)

        try:
            reply_text = await self.bridge.ask_agent(update.message.text)
        except UnexpectedResponseError as exc:  # pragma: no cover - defensive
            LOGGER.exception("Unexpected response from A2A server")
            await update.message.reply_text(f"A2A server error: {exc.status_code}")
            return
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.exception("Failed to reach A2A server")
            await update.message.reply_text(f"Couldn't contact agent: {exc}")
            return

        await update.message.reply_text(reply_text)


def load_config() -> BotConfig:
    """Create a :class:`BotConfig` from environment variables."""

    token = os.getenv("TELEGRAM_BOT_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")
    base_url = os.getenv("A2A_BASE_URL", "http://localhost:7000")
    poll_interval = float(os.getenv("A2A_POLL_INTERVAL", "1.5"))

    if not token:
        raise ValueError("TELEGRAM_BOT_TOKEN is required")
    if not chat_id:
        raise ValueError("TELEGRAM_CHAT_ID is required")

    return BotConfig(token=token, chat_id=int(chat_id), a2a_base_url=base_url, poll_interval=poll_interval)


def build_application(config: BotConfig, bridge: Optional[A2ATelegramBridge] = None) -> Application:
    """Build the :class:`telegram.ext.Application` with all handlers attached."""

    bridge = bridge or A2ATelegramBridge(base_url=config.a2a_base_url, poll_interval=config.poll_interval)
    handlers = TelegramBotHandlers(chat_id=config.chat_id, bridge=bridge)

    application = ApplicationBuilder().token(config.token).build()
    application.add_handler(CommandHandler("start", handlers.start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_text))
    return application


def main() -> None:
    """Entrypoint used when running ``python telegram_client.py``."""

    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")

    config = load_config()
    application = build_application(config)
    application.run_polling()


if __name__ == "__main__":
    main()
