from __future__ import annotations

import base64
import json
import logging
import traceback
from types import SimpleNamespace

import pytest
import requests
from backend_app import ai as ai_module
from backend_app import handler as handler_module
from backend_app.ai import AiService, GeneratedAnswer
from backend_app.config import DEFAULT_SYSTEM_PROMPT, ConfigurationError, Settings
from backend_app.discord import (
    ANSWER_LIMIT,
    DiscordClient,
    DiscordRequestError,
    build_response_payload,
    extract_conversation,
)
from backend_app.handler import ChatProcessingError
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
        openrouter_api_key="openrouter-key",
        project_id="project",
        fallback_default_provider="openai",
        fallback_openai_model="fallback-openai-model",
        fallback_gemini_model="fallback-gemini-model",
        fallback_openrouter_model="fallback-openrouter-model",
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
        openrouter_model="openrouter-model",
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
    assert settings.fallback_openrouter_model == "openrouter/auto"
    assert settings.model_config_ttl_seconds == 60
    assert settings.system_prompt == DEFAULT_SYSTEM_PROMPT
    assert settings.system_prompt == (
        "あなたは優秀なアシスタントです。"
        "ユーザーからの質問に対し700から800文字程度で簡潔に回答します。"
    )


def test_backend_settings_use_current_default_models() -> None:
    settings = Settings.from_env(
        {
            "DISCORD_BOT_TOKEN": "token",
            "GCP_PROJECT_ID": "project",
        }
    )

    assert settings.fallback_openai_model == "gpt-5.6-terra"
    assert settings.fallback_gemini_model == "gemini-3.8-flash"
    assert settings.fallback_openrouter_model == "openrouter/auto"


def test_backend_settings_accept_openrouter_configuration() -> None:
    settings = Settings.from_env(
        {
            "DISCORD_BOT_TOKEN": "token",
            "GCP_PROJECT_ID": "project",
            "DEFAULT_AI_PROVIDER": "openrouter",
            "OPENROUTER_API_KEY": "router-key",
            "OPENROUTER_MODEL": "anthropic/example-model",
        }
    )

    assert settings.fallback_default_provider == "openrouter"
    assert settings.openrouter_api_key == "router-key"
    assert settings.fallback_openrouter_model == "anthropic/example-model"


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


def test_model_config_uses_fallback_for_older_parameter_payload() -> None:
    config = ModelConfig.from_mapping(
        {
            "default_provider": "openai",
            "openai_model": "openai-model",
            "gemini_model": "gemini-model",
        },
        fallback_openrouter_model="fallback-router-model",
    )

    assert config.openrouter_model == "fallback-router-model"


def test_model_config_accepts_openrouter_and_rejects_empty_model() -> None:
    payload = {
        "default_provider": "openrouter",
        "openai_model": "openai-model",
        "gemini_model": "gemini-model",
        "openrouter_model": "anthropic/example-model",
    }

    config = ModelConfig.from_mapping(payload)
    assert config.openrouter_model == "anthropic/example-model"
    with pytest.raises(ValueError, match="openrouter_model"):
        ModelConfig.from_mapping({**payload, "openrouter_model": " "})


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


def test_decode_pubsub_event_accepts_openrouter() -> None:
    job = decode_pubsub_event(
        _event(
            {
                "application_id": "app",
                "interaction_token": "token",
                "channel_id": "channel",
                "channel_type": 0,
                "prompt": "hello",
                "provider": "openrouter",
            }
        )
    )

    assert job.provider == "openrouter"


def test_decode_pubsub_event_model_selects_openrouter() -> None:
    job = decode_pubsub_event(
        _event(
            {
                "application_id": "app",
                "interaction_token": "token",
                "channel_id": "channel",
                "channel_type": 0,
                "prompt": "hello",
                "model": "typesafe/jev-router",
            }
        )
    )

    assert job.provider == "openrouter"
    assert job.model == "typesafe/jev-router"


@pytest.mark.parametrize(
    ("provider", "model"),
    [
        (None, "unlisted/model"),
        (None, "openrouter/auto"),
        ("gemini", "anthropic/claude-fable-5.1"),
    ],
)
def test_decode_pubsub_event_rejects_invalid_model(
    provider: str | None, model: str
) -> None:
    with pytest.raises(ValueError):
        decode_pubsub_event(
            _event(
                {
                    "application_id": "app",
                    "interaction_token": "token",
                    "channel_id": "channel",
                    "channel_type": 0,
                    "prompt": "hello",
                    "provider": provider,
                    "model": model,
                }
            )
        )


def test_payload_obeys_answer_limit_and_disables_mentions() -> None:
    payload = build_response_payload(
        "question", "@everyone " + "a" * ANSWER_LIMIT, "gemini-model"
    )

    assert payload["content"] == "question"
    assert len(payload["embeds"]) == 1
    assert payload["embeds"][0]["title"] == "回答"
    assert payload["embeds"][0]["author"] == {"name": "gemini-model"}
    assert len(payload["embeds"][0]["description"]) <= ANSWER_LIMIT
    assert payload["allowed_mentions"] == {"parse": []}
    assert payload["embeds"][0]["description"].endswith("…（長文のため省略しました）")
    assert (
        len(build_response_payload("q", "a", "m" * 300)["embeds"][0]["author"]["name"])
        == 256
    )


def test_extract_conversation_ignores_unrelated_embeds() -> None:
    messages = [
        {"embeds": [{"title": "unrelated", "description": "ignore"}]},
        {
            "type": 20,
            "flags": 0,
            "content": "newest question",
            "embeds": [
                {
                    "title": "回答",
                    "description": "newest answer",
                    "author": {"name": "gemini-model"},
                }
            ],
        },
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
        "newest question",
        "newest answer",
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
    client.complete_interaction(job, "answer", "openai-model")

    assert session.get_args[1]["headers"] == {"Authorization": "Bot secret"}
    assert "headers" not in session.patch_args[1]
    assert session.patch_args[0].endswith(
        "/webhooks/app/interaction-token/messages/@original"
    )
    assert session.patch_args[1]["json"]["embeds"][0]["author"] == {
        "name": "openai-model"
    }


@pytest.mark.parametrize("operation", ["complete", "fail"])
@pytest.mark.parametrize("failure_mode", ["http", "connection"])
def test_discord_interaction_errors_hide_sensitive_data(
    operation: str, failure_mode: str
) -> None:
    class Session:
        def patch(self, url: str, **kwargs) -> requests.Response:
            if failure_mode == "connection":
                raise requests.ConnectionError(f"{url} {kwargs['json']}")
            response = requests.Response()
            response.status_code = 500
            response.url = url
            return response

    job = ChatJob(
        "app", "private-interaction-token", "channel", 0, "private prompt", "openai"
    )
    answer = "private answer"
    client = DiscordClient("bot-token", 30, Session())  # type: ignore[arg-type]

    with pytest.raises(DiscordRequestError) as caught:
        if operation == "complete":
            client.complete_interaction(job, answer, "openai-model")
        else:
            client.fail_interaction(job)

    formatted = "".join(traceback.format_exception(caught.value))
    assert "private-interaction-token" not in formatted
    assert "private prompt" not in formatted
    assert "private answer" not in formatted
    assert "Discord interaction request failed" in formatted
    if failure_mode == "http":
        assert "HTTP 500" in formatted


def test_handler_logs_and_raises_only_safe_error_details(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    class Discord:
        failure_notifications = 0

        def complete_interaction(self, job: ChatJob, answer: str, _model: str) -> None:
            raise RuntimeError(f"{job.interaction_token} {job.prompt} {answer}")

        def fail_interaction(self, job: ChatJob) -> None:
            self.failure_notifications += 1
            raise RuntimeError(f"{job.interaction_token} {job.prompt}")

    discord = Discord()
    monkeypatch.setattr(handler_module, "Settings", SimpleNamespace(from_env=_settings))
    monkeypatch.setattr(handler_module, "DiscordClient", lambda *_args: discord)
    monkeypatch.setattr(
        handler_module, "_get_model_config", lambda _settings: _model_config()
    )
    monkeypatch.setattr(
        handler_module,
        "AiService",
        lambda *_args: SimpleNamespace(
            generate=lambda **_kwargs: GeneratedAnswer("private answer")
        ),
    )

    with (
        caplog.at_level(logging.ERROR, logger=handler_module.__name__),
        pytest.raises(ChatProcessingError) as caught,
    ):
        handler_module.handle_chat(
            _event(
                {
                    "application_id": "app",
                    "interaction_token": "private-interaction-token",
                    "channel_id": "channel",
                    "channel_type": 0,
                    "prompt": "private prompt",
                    "provider": "openai",
                }
            )
        )

    visible = caplog.text + "".join(traceback.format_exception(caught.value))
    assert "private-interaction-token" not in visible
    assert "private prompt" not in visible
    assert "private answer" not in visible
    assert "RuntimeError" in caplog.text
    assert discord.failure_notifications == 1


def test_handler_uses_openrouter_default_and_model_label(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {}

    class Discord:
        def complete_interaction(
            self, _job: ChatJob, answer: str, model_name: str
        ) -> None:
            captured["answer"] = answer
            captured["model_name"] = model_name

    def generate(**kwargs) -> GeneratedAnswer:
        captured["provider"] = kwargs["provider"]
        return GeneratedAnswer("answer")

    config = ModelConfig(
        default_provider="openrouter",
        openai_model="openai-model",
        gemini_model="gemini-model",
        openrouter_model="openrouter-model",
    )
    monkeypatch.setattr(handler_module, "Settings", SimpleNamespace(from_env=_settings))
    monkeypatch.setattr(handler_module, "DiscordClient", lambda *_args: Discord())
    monkeypatch.setattr(handler_module, "_get_model_config", lambda _settings: config)
    monkeypatch.setattr(
        handler_module, "AiService", lambda *_args: SimpleNamespace(generate=generate)
    )

    handler_module.handle_chat(
        _event(
            {
                "application_id": "app",
                "interaction_token": "token",
                "channel_id": "channel",
                "channel_type": 0,
                "prompt": "question",
            }
        )
    )

    assert captured == {
        "provider": "openrouter",
        "answer": "answer",
        "model_name": "openrouter-model",
    }


@pytest.mark.parametrize(
    ("selected_model", "actual_model", "expected_label"),
    [
        ("deepseek/deepseek-v4.1-flash", None, "deepseek/deepseek-v4.1-flash"),
        (
            "typesafe/jev-router",
            "deepseek/deepseek-v4.1-flash",
            "typesafe/jev-router → deepseek/deepseek-v4.1-flash",
        ),
    ],
)
def test_handler_uses_selected_openrouter_model(
    monkeypatch: pytest.MonkeyPatch,
    selected_model: str,
    actual_model: str | None,
    expected_label: str,
) -> None:
    captured = {}

    class Discord:
        def complete_interaction(
            self, _job: ChatJob, _answer: str, model_name: str
        ) -> None:
            captured["label"] = model_name

    def generate(**kwargs) -> GeneratedAnswer:
        captured["provider"] = kwargs["provider"]
        captured["model"] = kwargs["model"]
        return GeneratedAnswer("answer", actual_model)

    monkeypatch.setattr(handler_module, "Settings", SimpleNamespace(from_env=_settings))
    monkeypatch.setattr(handler_module, "DiscordClient", lambda *_args: Discord())
    monkeypatch.setattr(
        handler_module, "_get_model_config", lambda _settings: _model_config()
    )
    monkeypatch.setattr(
        handler_module, "AiService", lambda *_args: SimpleNamespace(generate=generate)
    )

    handler_module.handle_chat(
        _event(
            {
                "application_id": "app",
                "interaction_token": "token",
                "channel_id": "channel",
                "channel_type": 0,
                "prompt": "question",
                "model": selected_model,
            }
        )
    )

    assert captured == {
        "provider": "openrouter",
        "model": selected_model,
        "label": expected_label,
    }


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

    assert answer == GeneratedAnswer("generated answer")
    assert captured["model"] == "openai-model"
    assert captured["instructions"] == "system prompt"
    assert captured["input"][-1] == {
        "role": "user",
        "content": "current question",
    }
    assert "reasoning" not in captured


def test_gpt_5_6_preserves_non_reasoning_response_behavior(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured = {}

    class Responses:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(output_text="generated answer")

    class Client:
        responses = Responses()

    monkeypatch.setattr(ai_module, "OpenAI", lambda **_kwargs: Client())
    model_config = ModelConfig(
        default_provider="openai",
        openai_model="gpt-5.6-terra",
        gemini_model="gemini-model",
    )

    AiService(_settings(), model_config).generate(
        provider="openai",
        history=[],
        prompt="current question",
    )

    assert captured["model"] == "gpt-5.6-terra"
    assert captured["reasoning"] == {"effort": "none"}


def test_gemini_provider_includes_history(monkeypatch: pytest.MonkeyPatch) -> None:
    captured = {}

    class Models:
        def generate_content(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(text=" generated answer ")

    class Client:
        models = Models()

    monkeypatch.setattr(ai_module.genai, "Client", lambda **_kwargs: Client())

    model_config = ModelConfig(
        default_provider="gemini",
        openai_model="openai-model",
        gemini_model="gemini-3.8-flash",
    )

    answer = AiService(_settings(), model_config).generate(
        provider="gemini",
        history=[ConversationMessage("assistant", "earlier answer")],
        prompt="current question",
    )

    assert answer == GeneratedAnswer("generated answer")
    assert captured["model"] == "gemini-3.8-flash"
    assert "アシスタント: earlier answer" in captured["contents"]
    assert "ユーザー: current question" in captured["contents"]


def test_openrouter_provider_uses_chat_completions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client_options = {}
    request = {}

    class Completions:
        def create(self, **kwargs):
            request.update(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content=" answer "))]
            )

    class Client:
        chat = SimpleNamespace(completions=Completions())

    def client_factory(**kwargs):
        client_options.update(kwargs)
        return Client()

    monkeypatch.setattr(ai_module, "OpenAI", client_factory)

    answer = AiService(_settings(), _model_config()).generate(
        provider="openrouter",
        history=[
            ConversationMessage("user", "earlier question"),
            ConversationMessage("assistant", "earlier answer"),
        ],
        prompt="current question",
    )

    assert answer == GeneratedAnswer("answer")
    assert client_options == {
        "api_key": "openrouter-key",
        "base_url": "https://openrouter.ai/api/v1",
        "timeout": 30.0,
    }
    assert request == {
        "model": "openrouter-model",
        "messages": [
            {"role": "system", "content": "system prompt"},
            {"role": "user", "content": "earlier question"},
            {"role": "assistant", "content": "earlier answer"},
            {"role": "user", "content": "current question"},
        ],
    }


def test_openrouter_provider_passes_selected_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request = {}

    class Completions:
        def create(self, **kwargs):
            request.update(kwargs)
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="answer"))],
                model="deepseek/deepseek-v4.1-flash",
            )

    class Client:
        chat = SimpleNamespace(completions=Completions())

    monkeypatch.setattr(ai_module, "OpenAI", lambda **_kwargs: Client())

    answer = AiService(_settings(), _model_config()).generate(
        provider="openrouter",
        history=[],
        prompt="question",
        model="typesafe/jev-router",
    )

    assert request["model"] == "typesafe/jev-router"
    assert answer == GeneratedAnswer("answer", "deepseek/deepseek-v4.1-flash")


def test_openrouter_provider_requires_key() -> None:
    settings = Settings.from_env({"DISCORD_BOT_TOKEN": "token", "GCP_PROJECT_ID": "p"})

    with pytest.raises(ConfigurationError, match="OPENROUTER_API_KEY"):
        AiService(settings, _model_config()).generate(
            provider="openrouter", history=[], prompt="question"
        )


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
    assert first.openrouter_model == "fallback-openrouter-model"
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
    assert config.openrouter_model == "fallback-openrouter-model"
