"""Dynamic AI model configuration backed by Google Parameter Manager."""

from __future__ import annotations

import json
import logging
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from google.cloud import parametermanager_v1

from backend_app.config import Settings

logger = logging.getLogger(__name__)
SUPPORTED_PROVIDERS = {"openai", "gemini"}


def _required_string(payload: Mapping[str, Any], name: str) -> str:
    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Model configuration field '{name}' must be a string")
    if len(value) > 200:
        raise ValueError(f"Model configuration field '{name}' is too long")
    return value.strip()


@dataclass(frozen=True, slots=True)
class ModelConfig:
    default_provider: str
    openai_model: str
    gemini_model: str

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> ModelConfig:
        provider = _required_string(payload, "default_provider").lower()
        if provider not in SUPPORTED_PROVIDERS:
            raise ValueError("default_provider must be openai or gemini")
        return cls(
            default_provider=provider,
            openai_model=_required_string(payload, "openai_model"),
            gemini_model=_required_string(payload, "gemini_model"),
        )

    @classmethod
    def from_settings(cls, settings: Settings) -> ModelConfig:
        return cls.from_mapping(
            {
                "default_provider": settings.fallback_default_provider,
                "openai_model": settings.fallback_openai_model,
                "gemini_model": settings.fallback_gemini_model,
            }
        )


class ModelConfigProvider:
    def __init__(
        self,
        settings: Settings,
        client: parametermanager_v1.ParameterManagerClient | None = None,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._settings = settings
        self._client = client or parametermanager_v1.ParameterManagerClient()
        self._clock = clock
        self._cached: ModelConfig | None = None
        self._expires_at = 0.0

    def get(self) -> ModelConfig:
        now = self._clock()
        if self._cached is not None and now < self._expires_at:
            return self._cached

        try:
            config = self._fetch()
        except Exception:
            config = self._cached or ModelConfig.from_settings(self._settings)
            logger.warning(
                "Unable to refresh model configuration; using last known value",
                exc_info=True,
            )

        self._cached = config
        self._expires_at = now + self._settings.model_config_ttl_seconds
        return config

    def _fetch(self) -> ModelConfig:
        name = self._client.parameter_version_path(
            self._settings.project_id,
            "global",
            self._settings.model_config_parameter,
            "latest",
        )
        response = self._client.render_parameter_version(
            request={"name": name},
            timeout=self._settings.http_timeout_seconds,
        )
        raw_payload = bytes(response.rendered_payload.data).decode("utf-8")
        payload = json.loads(raw_payload)
        if not isinstance(payload, Mapping):
            raise ValueError("Model configuration must be a JSON object")
        return ModelConfig.from_mapping(payload)
