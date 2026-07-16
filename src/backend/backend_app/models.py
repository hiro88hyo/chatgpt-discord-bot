"""Domain models and Pub/Sub event decoding."""

from __future__ import annotations

import base64
import json
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

THREAD_CHANNEL_TYPES = {10, 11, 12}
SUPPORTED_PROVIDERS = {"openai", "gemini"}


@dataclass(frozen=True, slots=True)
class ConversationMessage:
    role: str
    content: str


@dataclass(frozen=True, slots=True)
class ChatJob:
    application_id: str
    interaction_token: str
    channel_id: str
    channel_type: int
    prompt: str
    provider: str

    @property
    def is_thread(self) -> bool:
        return self.channel_type in THREAD_CHANNEL_TYPES

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> ChatJob:
        required = (
            "application_id",
            "interaction_token",
            "channel_id",
            "channel_type",
            "prompt",
            "provider",
        )
        missing = [name for name in required if payload.get(name) in (None, "")]
        if missing:
            raise ValueError(f"Pub/Sub payload is missing: {', '.join(missing)}")

        provider = str(payload["provider"]).lower()
        if provider not in SUPPORTED_PROVIDERS:
            raise ValueError(f"Unsupported AI provider: {provider}")

        return cls(
            application_id=str(payload["application_id"]),
            interaction_token=str(payload["interaction_token"]),
            channel_id=str(payload["channel_id"]),
            channel_type=int(payload["channel_type"]),
            prompt=str(payload["prompt"]),
            provider=provider,
        )


def decode_pubsub_event(cloud_event: Any) -> ChatJob:
    """Decode a Gen 2 CloudEvent, with legacy event support for local tests."""
    event_data = getattr(cloud_event, "data", cloud_event)
    if not isinstance(event_data, Mapping):
        raise ValueError("Pub/Sub event data must be an object")

    message = event_data.get("message")
    encoded = (
        message.get("data") if isinstance(message, Mapping) else event_data.get("data")
    )
    if not isinstance(encoded, str):
        raise ValueError("Pub/Sub event does not contain message data")

    try:
        payload = json.loads(base64.b64decode(encoded, validate=True).decode("utf-8"))
    except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError("Pub/Sub message data is not valid base64 JSON") from exc
    if not isinstance(payload, Mapping):
        raise ValueError("Pub/Sub message payload must be an object")
    return ChatJob.from_dict(payload)
