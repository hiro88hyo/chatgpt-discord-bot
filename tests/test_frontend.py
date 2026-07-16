from __future__ import annotations

import pytest
from frontend_app.config import ConfigurationError, Settings
from frontend_app.discord import (
    ChatRequest,
    InteractionError,
    parse_chat_request,
    verify_request_signature,
)
from frontend_app.publisher import ChatPublisher
from nacl.signing import SigningKey


def test_frontend_settings_require_values() -> None:
    with pytest.raises(ConfigurationError, match="GCP_PROJECT_ID"):
        Settings.from_env({})


def test_signature_verification() -> None:
    signing_key = SigningKey.generate()
    body = b'{"type":1}'
    timestamp = "12345"
    signature = signing_key.sign(timestamp.encode() + body).signature.hex()
    headers = {
        "X-Signature-Ed25519": signature,
        "X-Signature-Timestamp": timestamp,
    }

    assert verify_request_signature(
        headers, body, signing_key.verify_key.encode().hex()
    )
    assert not verify_request_signature(
        headers, body + b" ", signing_key.verify_key.encode().hex()
    )


def test_parse_chat_request() -> None:
    request = parse_chat_request(
        {
            "application_id": "app",
            "token": "token",
            "channel": {"id": "channel", "type": 11},
            "data": {
                "name": "chat",
                "options": [
                    {"name": "prompt", "value": "  hello  "},
                    {"name": "provider", "value": "gemini"},
                ],
            },
        },
        "openai",
    )

    assert request.prompt == "hello"
    assert request.provider == "gemini"
    assert request.channel_type == 11


def test_parse_chat_request_rejects_missing_prompt() -> None:
    with pytest.raises(InteractionError, match="プロンプト"):
        parse_chat_request(
            {
                "application_id": "app",
                "token": "token",
                "channel": {"id": "channel", "type": 0},
                "data": {"name": "chat"},
            },
            "openai",
        )


def test_publisher_waits_for_pubsub_acknowledgement() -> None:
    class Future:
        timeout = None

        def result(self, timeout: float) -> str:
            self.timeout = timeout
            return "message-id"

    class Publisher:
        def __init__(self) -> None:
            self.future = Future()
            self.published = None

        def topic_path(self, project: str, topic: str) -> str:
            return f"projects/{project}/topics/{topic}"

        def publish(self, topic: str, data: bytes) -> Future:
            self.published = (topic, data)
            return self.future

    settings = Settings(
        project_id="project",
        pubsub_topic="topic",
        discord_public_key="00" * 32,
    )
    client = Publisher()
    request = ChatRequest("app", "token", "channel", 0, "hello", "openai")

    message_id = ChatPublisher(settings, client).publish(request)  # type: ignore[arg-type]

    assert message_id == "message-id"
    assert client.future.timeout == 2.0
    assert client.published is not None
    assert client.published[0] == "projects/project/topics/topic"
    assert b'"prompt":"hello"' in client.published[1]
