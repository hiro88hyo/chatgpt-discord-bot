from __future__ import annotations

import base64
import json
from types import SimpleNamespace

import pytest
from backend_app import ai as ai_module
from backend_app.ai import AiService
from backend_app.config import Settings
from backend_app.discord import (
    ANSWER_LIMIT,
    DiscordClient,
    build_response_payload,
    extract_conversation,
)
from backend_app.models import ChatJob, ConversationMessage, decode_pubsub_event


class CloudEvent:
    def __init__(self, data: dict) -> None:
        self.data = data


def _event(payload: dict) -> CloudEvent:
    encoded = base64.b64encode(json.dumps(payload).encode()).decode()
    return CloudEvent({"message": {"data": encoded}})


def _settings() -> Settings:
    return Settings(
        discord_bot_token="discord-token",
        openai_api_key="openai-key",
        gemini_api_key="gemini-key",
        openai_model="openai-model",
        gemini_model="gemini-model",
        system_prompt="system prompt",
        history_message_limit=20,
    )


def test_decode_pubsub_event() -> None:
    job = decode_pubsub_event(
        _event(
            {
                "application_id": "app",
                "interaction_token": "token",
                "channel_id": "channel",
                "channel_type": 12,
                "prompt": "hello",
                "provider": "openai",
            }
        )
    )

    assert job.prompt == "hello"
    assert job.is_thread


def test_decode_pubsub_event_rejects_unknown_provider() -> None:
    with pytest.raises(ValueError, match="Unsupported"):
        decode_pubsub_event(
            _event(
                {
                    "application_id": "app",
                    "interaction_token": "token",
                    "channel_id": "channel",
                    "channel_type": 0,
                    "prompt": "hello",
                    "provider": "unknown",
                }
            )
        )


def test_payload_obeys_answer_limit_and_disables_mentions() -> None:
    payload = build_response_payload("question", "@everyone " + "a" * ANSWER_LIMIT)

    assert len(payload["embeds"][1]["description"]) <= ANSWER_LIMIT
    assert payload["allowed_mentions"] == {"parse": []}
    assert payload["embeds"][1]["description"].endswith("…（長文のため省略しました）")


def test_extract_conversation_ignores_unrelated_embeds() -> None:
    messages = [
        {"embeds": [{"title": "unrelated", "description": "ignore"}]},
        {
            "embeds": [
                {"title": "質問", "description": "new question"},
                {
                    "title": "回答",
                    "description": "new answer",
                    "footer": {"text": "chat-gpt-discord-bot"},
                },
            ]
        },
        {
            "embeds": [
                {"title": "質問", "description": "old question"},
                {
                    "title": "回答",
                    "description": "old answer",
                    "footer": {"text": "chat-gpt-discord-bot"},
                },
            ]
        },
    ]

    conversation = extract_conversation(messages)

    assert [message.content for message in conversation] == [
        "old question",
        "old answer",
        "new question",
        "new answer",
    ]


def test_discord_client_only_authenticates_bot_api_requests() -> None:
    class Response:
        def raise_for_status(self) -> None:
            return None

        def json(self) -> list:
            return []

    class Session:
        get_args = None
        patch_args = None

        def get(self, url: str, **kwargs) -> Response:
            self.get_args = (url, kwargs)
            return Response()

        def patch(self, url: str, **kwargs) -> Response:
            self.patch_args = (url, kwargs)
            return Response()

    session = Session()
    client = DiscordClient("secret", 30, session)  # type: ignore[arg-type]
    job = ChatJob("app", "interaction-token", "channel", 0, "question", "openai")

    client.fetch_conversation("channel", 20)
    client.complete_interaction(job, "answer")

    assert session.get_args[1]["headers"] == {"Authorization": "Bot secret"}
    assert "headers" not in session.patch_args[1]
    assert session.patch_args[0].endswith(
        "/webhooks/app/interaction-token/messages/@original"
    )


def test_openai_provider_uses_responses_api(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    class Responses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(output_text=" generated answer ")

    class Client:
        responses = Responses()

    monkeypatch.setattr(ai_module, "OpenAI", lambda **_kwargs: Client())

    answer = AiService(_settings()).generate(
        provider="openai",
        history=[ConversationMessage("user", "earlier question")],
        prompt="current question",
    )

    assert answer == "generated answer"
    assert captured["model"] == "openai-model"
    assert captured["instructions"] == "system prompt"
    assert captured["input"][-1] == {
        "role": "user",
        "content": "current question",
    }


def test_gemini_provider_includes_history(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    class Models:
        def generate_content(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(text=" generated answer ")

    class Client:
        models = Models()

    monkeypatch.setattr(ai_module.genai, "Client", lambda **_kwargs: Client())

    answer = AiService(_settings()).generate(
        provider="gemini",
        history=[ConversationMessage("assistant", "earlier answer")],
        prompt="current question",
    )

    assert answer == "generated answer"
    assert captured["model"] == "gemini-model"
    assert "アシスタント: earlier answer" in captured["contents"]
    assert "ユーザー: current question" in captured["contents"]
