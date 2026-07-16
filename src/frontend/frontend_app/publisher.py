"""Pub/Sub publisher for accepted chat interactions."""

from __future__ import annotations

import json

from google.cloud import pubsub_v1

from frontend_app.config import Settings
from frontend_app.discord import ChatRequest


class ChatPublisher:
    def __init__(
        self,
        settings: Settings,
        client: pubsub_v1.PublisherClient | None = None,
    ) -> None:
        self._settings = settings
        self._client = client or pubsub_v1.PublisherClient()

    def publish(self, request: ChatRequest) -> str:
        topic_path = self._client.topic_path(
            self._settings.project_id, self._settings.pubsub_topic
        )
        data = json.dumps(
            request.to_dict(), ensure_ascii=False, separators=(",", ":")
        ).encode("utf-8")
        future = self._client.publish(topic_path, data)
        return future.result(timeout=self._settings.publish_timeout_seconds)
