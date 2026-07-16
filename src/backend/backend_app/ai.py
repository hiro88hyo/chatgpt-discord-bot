"""AI provider adapters."""

from __future__ import annotations

from google import genai
from google.genai import types
from openai import OpenAI

from backend_app.config import ConfigurationError, Settings
from backend_app.model_config import ModelConfig
from backend_app.models import ConversationMessage


class AiService:
    def __init__(self, settings: Settings, model_config: ModelConfig) -> None:
        self._settings = settings
        self._model_config = model_config

    def generate(
        self,
        *,
        provider: str,
        history: list[ConversationMessage],
        prompt: str,
    ) -> str:
        if provider == "openai":
            return self._generate_openai(history, prompt)
        if provider == "gemini":
            return self._generate_gemini(history, prompt)
        raise ValueError(f"Unsupported AI provider: {provider}")

    def _generate_openai(self, history: list[ConversationMessage], prompt: str) -> str:
        if not self._settings.openai_api_key:
            raise ConfigurationError(
                "OPENAI_API_KEY is required for the OpenAI provider"
            )

        input_messages = [
            {"role": message.role, "content": message.content} for message in history
        ]
        input_messages.append({"role": "user", "content": prompt})
        response = OpenAI(
            api_key=self._settings.openai_api_key,
            timeout=self._settings.http_timeout_seconds,
        ).responses.create(
            model=self._model_config.openai_model,
            instructions=self._settings.system_prompt,
            input=input_messages,
        )
        if not response.output_text:
            raise RuntimeError("OpenAI returned an empty response")
        return response.output_text.strip()

    def _generate_gemini(self, history: list[ConversationMessage], prompt: str) -> str:
        if not self._settings.gemini_api_key:
            raise ConfigurationError(
                "GEMINI_API_KEY is required for the Gemini provider"
            )

        transcript = []
        for message in history:
            speaker = "ユーザー" if message.role == "user" else "アシスタント"
            transcript.append(f"{speaker}: {message.content}")
        transcript.append(f"ユーザー: {prompt}")
        client = genai.Client(api_key=self._settings.gemini_api_key)
        response = client.models.generate_content(
            model=self._model_config.gemini_model,
            contents="\n\n".join(transcript),
            config=types.GenerateContentConfig(
                system_instruction=self._settings.system_prompt
            ),
        )
        if not response.text:
            raise RuntimeError("Gemini returned an empty response")
        return response.text.strip()
