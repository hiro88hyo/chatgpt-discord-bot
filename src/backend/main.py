"""Google Cloud Functions entry point for queued chat requests."""

from __future__ import annotations

import logging

import functions_framework
from backend_app.ai import AiService
from backend_app.config import Settings
from backend_app.discord import DiscordClient
from backend_app.model_config import ModelConfig, ModelConfigProvider
from backend_app.models import decode_pubsub_event

logger = logging.getLogger(__name__)
_model_config_provider: ModelConfigProvider | None = None


def _get_model_config(settings: Settings) -> ModelConfig:
    global _model_config_provider
    if _model_config_provider is None:
        _model_config_provider = ModelConfigProvider(settings)
    return _model_config_provider.get()


@functions_framework.cloud_event
def main(cloud_event) -> None:
    """Generate an AI answer and complete a deferred Discord interaction."""
    job = decode_pubsub_event(cloud_event)
    settings = Settings.from_env()
    discord = DiscordClient(settings.discord_bot_token, settings.http_timeout_seconds)

    try:
        model_config = _get_model_config(settings)
        history = []
        if job.is_thread:
            history = discord.fetch_conversation(
                job.channel_id, settings.history_message_limit
            )
        answer = AiService(settings, model_config).generate(
            provider=job.provider or model_config.default_provider,
            history=history,
            prompt=job.prompt,
        )
        discord.complete_interaction(job, answer)
    except Exception:
        logger.exception(
            "Chat processing failed (application_id=%s, channel_id=%s)",
            job.application_id,
            job.channel_id,
        )
        try:
            discord.fail_interaction(job)
        except Exception:
            logger.exception("Failed to notify Discord about the processing error")
        raise
