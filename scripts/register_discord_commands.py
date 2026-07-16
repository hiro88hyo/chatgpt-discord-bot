"""Register the bot's global Discord slash commands."""

from __future__ import annotations

import os

import requests


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
                "description": "AI アシスタントに質問します",
                "options": [
                    {
                        "name": "prompt",
                        "description": "質問内容",
                        "type": 3,
                        "required": True,
                        "max_length": 2_000,
                    },
                    {
                        "name": "provider",
                        "description": "使用する AI",
                        "type": 3,
                        "required": False,
                        "choices": [
                            {"name": "OpenAI", "value": "openai"},
                            {"name": "Gemini", "value": "gemini"},
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
