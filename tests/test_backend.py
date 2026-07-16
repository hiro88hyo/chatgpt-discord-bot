from __future__ import annotations

import base64
import json
from types import SimpleNamespace

import pytest
from backend_app import ai as ai_module
from backend_app.ai import AiService
from backend_app.config import ConfigurationError, Settings
from backend_app.discord import (
    ANSWER_LIMIT,
    DiscordClient,
    build_response_payload,
    extract_conversation,
)
from backend_app.model_config import ModelConfig, ModelConfigProvider
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
        project_id="project",
        fallback_default_provider="openai",
        fallback_openai_model="fallback-openai-model",
        fallback_gemini_model="fallback-gemini-model",
        model_config_parameter="discord-bot-model-config",
        model_config_ttl_seconds=60,
        system_prompt="system prompt",
        history_message_limit=20,
    )


def _model_config() -> ModelConfig:
    return ModelConfig(
        default_provider="openai",
        openai_model="openai-model",
        gemini_model="gemini-model",
    )


def test_backend_settings_load_model_fallbacks() -> None:
    settings = Settings.from_env(
        {
            "DISCORD_BOT_TOKEN": "token",
            "GCP_PROJECT_ID": "project",
            "DEFAULT_AI_PROVIDER": "gemini",
            "OPENAI_MODEL": "openai-fallback",
        }
    )

    assert settings.fallback_default_provider == "gemini"
    assert settings.fallback_openai_model == "openai-fallback"
    assert settings.model_config_ttl_seconds == 60


def test_backend_settings_reject_empty_fallback_model() -> None:
    with pytest.raises(ConfigurationError, match="OPENAI_MODEL"):
        Settings.from_env(
            {
                "DISCORD_BOT_TOKEN": "token",
                "GCP_PROJECT_ID": "project",
                "OPENAI_MODEL": " ",
            }
        )


def test_model_config_rejects_invalid_provider() -> None:
    with pytest.raises(ValueError, match="default_provider"):
        ModelConfig.from_mapping(
            {
                "default_provider": "unknown",
                "openai_model": "openai-model",
                "gemini_model": "gemini-model",
            }
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


def test_decode_pubsub_event_allows_backend_default_provider() -> None:
    job = decode_pubsub_event(
        _event(
            {
                "application_id": "app",
                "interaction_token": "token",
                "channel_id": "channel",
                "channel_type": 0,
                "prompt": "hello",
            }
        )
    )

    assert job.provider is None


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

    answer = AiService(_settings(), _model_config()).generate(
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

    answer = AiService(_settings(), _model_config()).generate(
        provider="gemini",
        history=[ConversationMessage("assistant", "earlier answer")],
        prompt="current question",
    )

    assert answer == "generated answer"
    assert captured["model"] == "gemini-model"
    assert "アシスタント: earlier answer" in captured["contents"]
    assert "ユーザー: current question" in captured["contents"]


def test_model_config_provider_caches_latest_version() -> None:
    class Clock:
        now = 100.0

        def __call__(self) -> float:
            return self.now

    class Client:
        calls = 0

        def parameter_version_path(self, *parts: str) -> str:
            return "/".join(parts)

        def render_parameter_version(self, *, request: dict, **_kwargs):
            assert request["name"].endswith("/latest")
            self.calls += 1
            payload = {
                "default_provider": "gemini",
                "openai_model": "dynamic-openai",
                "gemini_model": "dynamic-gemini",
            }
            return SimpleNamespace(
                rendered_payload=SimpleNamespace(data=json.dumps(payload).encode())
            )

    clock = Clock()
    client = Client()
    provider = ModelConfigProvider(
        _settings(),
        client,
        clock,  # type: ignore[arg-type]
    )

    first = provider.get()
    second = provider.get()
    clock.now += 61
    third = provider.get()

    assert first == second == third
    assert first.default_provider == "gemini"
    assert client.calls == 2


def test_model_config_provider_uses_stale_value_on_refresh_error() -> None:
    class Clock:
        now = 100.0

        def __call__(self) -> float:
            return self.now

    class Client:
        calls = 0

        def parameter_version_path(self, *parts: str) -> str:
            return "/".join(parts)

        def render_parameter_version(self, *, request: dict, **_kwargs):
            self.calls += 1
            if self.calls > 1:
                raise RuntimeError("Parameter Manager unavailable")
            payload = {
                "default_provider": "gemini",
                "openai_model": "dynamic-openai",
                "gemini_model": "dynamic-gemini",
            }
            return SimpleNamespace(
                rendered_payload=SimpleNamespace(data=json.dumps(payload).encode())
            )

    clock = Clock()
    provider = ModelConfigProvider(
        _settings(),
        Client(),
        clock,  # type: ignore[arg-type]
    )
    current = provider.get()
    clock.now += 61

    assert provider.get() == current


def test_model_config_provider_falls_back_on_first_error() -> None:
    class Client:
        def parameter_version_path(self, *parts: str) -> str:
            return "/".join(parts)

        def render_parameter_version(self, *, request: dict, **_kwargs):
            raise RuntimeError("No parameter version")

    provider = ModelConfigProvider(_settings(), Client())  # type: ignore[arg-type]

    config = provider.get()

    assert config.default_provider == "openai"
    assert config.openai_model == "fallback-openai-model"
