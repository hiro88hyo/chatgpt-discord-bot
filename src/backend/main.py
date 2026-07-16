"""Google Cloud Functions entry point for queued chat requests."""

from __future__ import annotations

import logging

import functions_framework
from backend_app.ai import AiService
from backend_app.config import Settings
from backend_app.discord import DiscordClient
from backend_app.models import decode_pubsub_event

logger = logging.getLogger(__name__)


@functions_framework.cloud_event
def main(cloud_event) -> None:
    """Generate an AI answer and complete a deferred Discord interaction."""
    job = decode_pubsub_event(cloud_event)
    settings = Settings.from_env()
    discord = DiscordClient(settings.discord_bot_token, settings.http_timeout_seconds)

    try:
        history = []
        if job.is_thread:
            history = discord.fetch_conversation(
                job.channel_id, settings.history_message_limit
            )
        answer = AiService(settings).generate(
            provider=job.provider,
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
