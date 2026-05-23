from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

import requests


class TelegramSession(Protocol):
    def post(self, url: str, *, json: dict, timeout: int):
        ...


@dataclass(frozen=True)
class TelegramConfig:
    enabled: bool = False
    bot_token: str = ""
    chat_id: str = ""
    timeout_seconds: int = 10


@dataclass(frozen=True)
class TelegramResult:
    status: str
    error: str = ""


def telegram_status(config: TelegramConfig) -> dict[str, bool]:
    return {
        "enabled": bool(config.enabled),
        "bot_token_configured": bool(config.bot_token.strip()),
        "chat_id_configured": bool(config.chat_id.strip()),
    }


def send_telegram_message(
    config: TelegramConfig,
    text: str,
    *,
    session: TelegramSession | None = None,
) -> TelegramResult:
    if not config.enabled:
        return TelegramResult(status="disabled")
    token = config.bot_token.strip()
    chat_id = config.chat_id.strip()
    if not token or not chat_id:
        return TelegramResult(status="not_configured")
    try:
        timeout = int(config.timeout_seconds)
    except (TypeError, ValueError):
        return TelegramResult(status="error", error="telegram_request_failed")
    if timeout <= 0:
        return TelegramResult(status="error", error="telegram_request_failed")

    client = session or requests.Session()
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        response = client.post(url, json={"chat_id": chat_id, "text": text}, timeout=timeout)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict) or payload.get("ok") is not True:
            return TelegramResult(status="error", error="telegram_request_failed")
    except ValueError:
        return TelegramResult(status="error", error="telegram_request_failed")
    except requests.RequestException:
        return TelegramResult(status="error", error="telegram_request_failed")
    return TelegramResult(status="sent")
