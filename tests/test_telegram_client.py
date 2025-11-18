import os
import types
import unittest
from unittest.mock import AsyncMock

from telegram_client import A2ATelegramBridge, BotConfig, TelegramBotHandlers, load_config


class _DummyMessage:
    def __init__(self, text: str):
        self.text = text
        self.replies: list[str] = []

    async def reply_text(self, text: str) -> None:
        self.replies.append(text)


class _DummyBot:
    def __init__(self):
        self.send_chat_action = AsyncMock()


class BridgeTests(unittest.IsolatedAsyncioTestCase):
    async def test_bridge_returns_text_when_task_completes(self) -> None:
        class FakeClient:
            async def send_message(self, message):
                return {
                    "result": {
                        "id": "task-1",
                        "status": {"state": "running"},
                    }
                }

            def __init__(self):
                self._calls = 0

            async def get_task(self, task_id):
                self._calls += 1
                return {
                    "result": {
                        "id": task_id,
                        "status": {"state": "completed"},
                        "artifacts": [
                            {"parts": [{"text": "Agent reply"}]},
                        ],
                    }
                }

        bridge = A2ATelegramBridge(base_url="http://example", poll_interval=0, client=FakeClient())
        text = await bridge.ask_agent("Hello")
        self.assertEqual(text, "Agent reply")

    async def test_bridge_raises_when_task_fails(self) -> None:
        class FailingClient:
            async def send_message(self, message):
                return {
                    "result": {
                        "id": "task-2",
                        "status": {"state": "running"},
                    }
                }

            async def get_task(self, task_id):
                return {
                    "result": {
                        "id": task_id,
                        "status": {"state": "failed", "message": "boom"},
                    }
                }

        bridge = A2ATelegramBridge(base_url="http://example", poll_interval=0, client=FailingClient())
        with self.assertRaises(RuntimeError):
            await bridge.ask_agent("Hello")


class TelegramHandlersSmokeTests(unittest.IsolatedAsyncioTestCase):
    async def test_handler_replies_with_agent_response(self) -> None:
        bridge = types.SimpleNamespace(ask_agent=AsyncMock(return_value="Agent reply"))
        handlers = TelegramBotHandlers(chat_id=123, bridge=bridge)

        update = types.SimpleNamespace(
            effective_chat=types.SimpleNamespace(id=123),
            message=_DummyMessage("Hello"),
        )
        context = types.SimpleNamespace(bot=_DummyBot())

        await handlers.handle_text(update, context)

        bridge.ask_agent.assert_awaited_once_with("Hello")
        self.assertEqual(update.message.replies[-1], "Agent reply")


class ConfigTests(unittest.TestCase):
    def test_load_config_reads_environment(self) -> None:
        os.environ["TELEGRAM_BOT_TOKEN"] = "token"
        os.environ["TELEGRAM_CHAT_ID"] = "456"
        os.environ["A2A_BASE_URL"] = "http://agent"
        os.environ["A2A_POLL_INTERVAL"] = "0.1"

        config = load_config()

        self.assertEqual(config, BotConfig(token="token", chat_id=456, a2a_base_url="http://agent", poll_interval=0.1))

        for key in ["TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID", "A2A_BASE_URL", "A2A_POLL_INTERVAL"]:
            os.environ.pop(key, None)


if __name__ == "__main__":
    unittest.main()
