"""Environment-backed frontend configuration."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass


class ConfigurationError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


def _required(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "").strip()
    if not value:
        raise ConfigurationError(f"Missing required environment variable: {name}")
    return value


@dataclass(frozen=True, slots=True)
class Settings:
    project_id: str
    pubsub_topic: str
    discord_public_key: str
    publish_timeout_seconds: float = 2.0

    @classmethod
    def from_env(cls, env: Mapping[str, str] = os.environ) -> Settings:
        return cls(
            project_id=_required(env, "GCP_PROJECT_ID"),
            pubsub_topic=_required(env, "PUBSUB_TOPIC_CHAT"),
            discord_public_key=_required(env, "DISCORD_PUBLIC_KEY"),
        )
