"""Environment-backed backend configuration."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass


class ConfigurationError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


def _required(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ConfigurationError(f"Missing required environment variable: {name}")
    return value


def _positive_int(env: Mapping[str, str], name: str, default: int) -> int:
    raw = env.get(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ConfigurationError(f"{name} must be an integer") from exc
    if value <= 0:
        raise ConfigurationError(f"{name} must be greater than zero")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    discord_bot_token: str
    openai_api_key: str | None
    gemini_api_key: str | None
    openai_model: str
    gemini_model: str
    system_prompt: str
    history_message_limit: int
    http_timeout_seconds: float = 30.0

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> Settings:
        return cls(
            discord_bot_token=_required(env, "DISCORD_BOT_TOKEN"),
            openai_api_key=env.get("OPENAI_API_KEY") or None,
            gemini_api_key=env.get("GEMINI_API_KEY") or None,
            openai_model=env.get("OPENAI_MODEL", "gpt-4o-mini").strip(),
            gemini_model=env.get("GEMINI_MODEL", "gemini-2.5-flash").strip(),
            system_prompt=env.get(
                "SYSTEM_PROMPT",
                "あなたは優秀なアシスタントです。質問に対して、正確かつ簡潔に日本語で回答してください。",
            ).strip(),
            history_message_limit=_positive_int(env, "HISTORY_MESSAGE_LIMIT", 20),
        )
