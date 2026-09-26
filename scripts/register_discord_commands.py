"""Register the bot's global Discord slash commands."""

from __future__ import annotations

import os

import requests

OPENROUTER_MODEL_CHOICES = (
    ("Gemini 3.8 Flash", "google/gemini-3.8-flash"),
    ("Claude Opus 5.5", "anthropic/claude-opus-5.5"),
    ("GPT-6 Astra", "openai/gpt-6-astra"),
    ("DeepSeek V4.1 Flash", "deepseek/deepseek-v4.1-flash"),
    ("Claude Fable 5.1", "anthropic/claude-fable-5.1"),
)


def main() -> None:
    application_id = os.environ["DISCORD_APPLICATION_ID"]
    token = os.environ["DISCORD_BOT_TOKEN"]
    response = requests.put(
        f"https://discord.com/api/v10/applications/{application_id}/commands",
        headers={"Authorization": f"Bot {token}"},
        json=[
            {
                "name": "chat",
                "type": 1,
                "description": "AIに話しかける",
                "options": [
                    {
                        "name": "prompt",
                        "description": "プロンプト",
                        "type": 3,
                        "required": True,
                        "max_length": 2_000,
                    },
                    {
                        "name": "provider",
                        "description": "LLM Engine",
                        "type": 3,
                        "required": False,
                        "choices": [
                            {"name": "OpenAI", "value": "openai"},
                            {"name": "Gemini", "value": "gemini"},
                            {"name": "OpenRouter", "value": "openrouter"},
                        ],
                    },
                    {
                        "name": "model",
                        "description": "OpenRouterのモデル。選ぶとOpenRouterを使用",
                        "type": 3,
                        "required": False,
                        "choices": [
                            {"name": name, "value": model_id}
                            for name, model_id in OPENROUTER_MODEL_CHOICES
                        ],
                    },
                ],
            }
        ],
        timeout=30,
    )
    response.raise_for_status()
    print("Discord commands registered successfully.")


if __name__ == "__main__":
    main()
