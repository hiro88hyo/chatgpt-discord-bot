"""Discord interaction validation and parsing."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from nacl.exceptions import BadSignatureError
from nacl.signing import VerifyKey

PING = 1
APPLICATION_COMMAND = 2
CHAT_COMMAND = "chat"
SUPPORTED_PROVIDERS = {"openai", "gemini"}


class InteractionError(ValueError):
    """Raised when a Discord interaction cannot be processed."""


@dataclass(frozen=True, slots=True)
class ChatRequest:
    application_id: str
    interaction_token: str
    channel_id: str
    channel_type: int
    prompt: str
    provider: str | None

    def to_dict(self) -> dict[str, str | int | None]:
        return {
            "application_id": self.application_id,
            "interaction_token": self.interaction_token,
            "channel_id": self.channel_id,
            "channel_type": self.channel_type,
            "prompt": self.prompt,
            "provider": self.provider,
        }


def verify_request_signature(
    headers: Mapping[str, str], raw_body: bytes, public_key: str
) -> bool:
    signature = headers.get("X-Signature-Ed25519")
    timestamp = headers.get("X-Signature-Timestamp")
    if not signature or not timestamp:
        return False

    try:
        VerifyKey(bytes.fromhex(public_key)).verify(
            timestamp.encode("utf-8") + raw_body,
            bytes.fromhex(signature),
        )
    except (BadSignatureError, ValueError):
        return False
    return True


def _required_string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InteractionError(f"{label}が見つかりません。")
    return value.strip()


def parse_chat_request(body: Mapping[str, Any]) -> ChatRequest:
    data = body.get("data")
    channel = body.get("channel")
    if not isinstance(data, Mapping) or not isinstance(channel, Mapping):
        raise InteractionError("Discord のリクエスト情報が不足しています。")
    if data.get("name") != CHAT_COMMAND:
        raise InteractionError("未対応のコマンドです。")

    raw_options = data.get("options", [])
    if not isinstance(raw_options, list):
        raise InteractionError("コマンド引数の形式が正しくありません。")
    options = {
        option["name"]: option.get("value")
        for option in raw_options
        if isinstance(option, Mapping) and isinstance(option.get("name"), str)
    }

    prompt = _required_string(options.get("prompt"), "プロンプト")
    raw_provider = options.get("provider")
    provider = str(raw_provider).lower() if raw_provider is not None else None
    if provider is not None and provider not in SUPPORTED_PROVIDERS:
        raise InteractionError("指定された AI プロバイダーには対応していません。")

    try:
        channel_type = int(channel["type"])
    except (KeyError, TypeError, ValueError) as exc:
        raise InteractionError("チャンネル情報が正しくありません。") from exc

    return ChatRequest(
        application_id=_required_string(body.get("application_id"), "Application ID"),
        interaction_token=_required_string(body.get("token"), "Interaction token"),
        channel_id=_required_string(channel.get("id"), "Channel ID"),
        channel_type=channel_type,
        prompt=prompt,
        provider=provider,
    )
