"""Process queued chat requests without exposing sensitive exception details."""

from __future__ import annotations

import logging

from backend_app.ai import AiService
from backend_app.config import Settings
from backend_app.discord import DiscordClient
from backend_app.model_config import ModelConfig, ModelConfigProvider
from backend_app.models import ChatJob, decode_pubsub_event

logger = logging.getLogger(__name__)
_model_config_provider: ModelConfigProvider | None = None


class ChatProcessingError(RuntimeError):
    """A safe error for the Cloud Functions runtime to log and retry."""


def _get_model_config(settings: Settings) -> ModelConfig:
    global _model_config_provider
    if _model_config_provider is None:
        _model_config_provider = ModelConfigProvider(settings)
    return _model_config_provider.get()


def handle_chat(cloud_event) -> None:
    """Generate an answer and complete a deferred Discord interaction."""
    job: ChatJob | None = None
    discord: DiscordClient | None = None

    try:
        job = decode_pubsub_event(cloud_event)
        settings = Settings.from_env()
        discord = DiscordClient(
            settings.discord_bot_token, settings.http_timeout_seconds
        )
        model_config = _get_model_config(settings)
        history = []
        if job.is_thread:
            history = discord.fetch_conversation(
                job.channel_id, settings.history_message_limit
            )
        provider = job.provider or model_config.default_provider
        answer = AiService(settings, model_config).generate(
            provider=provider,
            history=history,
            prompt=job.prompt,
        )
        model_name = {
            "openai": model_config.openai_model,
            "gemini": model_config.gemini_model,
            "openrouter": model_config.openrouter_model,
        }[provider]
        discord.complete_interaction(job, answer, model_name)
    except Exception as exc:
        logger.error("Chat processing failed (error_type=%s)", type(exc).__name__)
        if job is not None and discord is not None:
            try:
                discord.fail_interaction(job)
            except Exception as notification_error:
                logger.error(
                    "Failed to notify Discord about the processing error "
                    "(error_type=%s)",
                    type(notification_error).__name__,
                )
        raise ChatProcessingError("Chat processing failed") from None
