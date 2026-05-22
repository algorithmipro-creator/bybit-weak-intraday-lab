from __future__ import annotations

import requests

from bybit_weak_intraday.notifications.telegram import TelegramConfig, send_telegram_message, telegram_status


class FakeResponse:
    def __init__(self, payload=None):
        self.payload = payload or {"ok": True}

    def raise_for_status(self) -> None:
        return None

    def json(self):
        return self.payload


class FakeSession:
    def __init__(self, response=None, error: Exception | None = None):
        self.response = response or FakeResponse()
        self.error = error
        self.calls = []

    def post(self, url, *, json, timeout):
        self.calls.append({"url": url, "json": json, "timeout": timeout})
        if self.error:
            raise self.error
        return self.response


def test_telegram_status_redacts_token_and_chat_id() -> None:
    status = telegram_status(TelegramConfig(enabled=True, bot_token="secret-token", chat_id="123"))

    assert status == {"enabled": True, "bot_token_configured": True, "chat_id_configured": True}
    assert "secret-token" not in str(status)
    assert "123" not in str(status)


def test_send_telegram_message_returns_disabled_without_network() -> None:
    session = FakeSession()

    result = send_telegram_message(
        TelegramConfig(enabled=False, bot_token="secret", chat_id="123"),
        "hello",
        session=session,
    )

    assert result.status == "disabled"
    assert session.calls == []


def test_send_telegram_message_returns_not_configured_without_token_or_chat() -> None:
    result = send_telegram_message(TelegramConfig(enabled=True, bot_token="", chat_id=""), "hello", session=FakeSession())

    assert result.status == "not_configured"


def test_send_telegram_message_posts_to_bot_api_without_returning_secret() -> None:
    session = FakeSession()

    result = send_telegram_message(
        TelegramConfig(enabled=True, bot_token="secret-token", chat_id="123"),
        "Signal qualified",
        session=session,
    )

    assert result.status == "sent"
    assert session.calls[0]["url"] == "https://api.telegram.org/botsecret-token/sendMessage"
    assert session.calls[0]["json"] == {"chat_id": "123", "text": "Signal qualified"}
    assert "secret-token" not in str(result)


def test_send_telegram_message_sanitizes_transport_errors() -> None:
    result = send_telegram_message(
        TelegramConfig(enabled=True, bot_token="secret-token", chat_id="123"),
        "hello",
        session=FakeSession(error=requests.RequestException("failed with secret-token")),
    )

    assert result.status == "error"
    assert result.error == "telegram_request_failed"
    assert "secret-token" not in str(result)
