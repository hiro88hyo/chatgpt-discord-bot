"""Discord REST API client and conversation extraction."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import requests

from backend_app.models import ChatJob, ConversationMessage

DISCORD_API_BASE = "https://discord.com/api/v10"
QUESTION_LIMIT = 1_000
ANSWER_LIMIT = 4_500
TRUNCATION_MARKER = "\n\n…（長文のため省略しました）"


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - len(TRUNCATION_MARKER)].rstrip() + TRUNCATION_MARKER


def build_response_payload(prompt: str, answer: str) -> dict[str, Any]:
    return {
        "content": "",
        "embeds": [
            {
                "title": "質問",
                "description": truncate(prompt, QUESTION_LIMIT),
                "color": 0x55C500,
            },
            {
                "title": "回答",
                "description": truncate(answer, ANSWER_LIMIT),
                "color": 0x55C500,
                "footer": {"text": "chat-gpt-discord-bot"},
            },
        ],
        "allowed_mentions": {"parse": []},
    }


def extract_conversation(
    messages: list[Mapping[str, Any]],
) -> list[ConversationMessage]:
    conversation: list[ConversationMessage] = []
    for message in reversed(messages):
        embeds = message.get("embeds")
        if not isinstance(embeds, list):
            continue
        question = next(
            (
                embed.get("description")
                for embed in embeds
                if isinstance(embed, Mapping) and embed.get("title") == "質問"
            ),
            None,
        )
        answer = next(
            (
                embed.get("description")
                for embed in embeds
                if isinstance(embed, Mapping)
                and embed.get("title") == "回答"
                and isinstance(embed.get("footer"), Mapping)
                and embed["footer"].get("text") == "chat-gpt-discord-bot"
            ),
            None,
        )
        if isinstance(question, str) and isinstance(answer, str):
            conversation.extend(
                [
                    ConversationMessage(role="user", content=question),
                    ConversationMessage(role="assistant", content=answer),
                ]
            )
    return conversation


class DiscordClient:
    def __init__(
        self,
        bot_token: str,
        timeout_seconds: float,
        session: requests.Session | None = None,
    ) -> None:
        self._timeout = timeout_seconds
        self._session = session or requests.Session()
        self._authorization = {"Authorization": f"Bot {bot_token}"}

    def fetch_conversation(
        self, channel_id: str, message_limit: int
    ) -> list[ConversationMessage]:
        response = self._session.get(
            f"{DISCORD_API_BASE}/channels/{channel_id}/messages",
            params={"limit": min(message_limit, 100)},
            headers=self._authorization,
            timeout=self._timeout,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            raise RuntimeError("Discord message history response is not a list")
        return extract_conversation(payload)

    def complete_interaction(self, job: ChatJob, answer: str) -> None:
        response = self._session.patch(
            self._interaction_url(job),
            json=build_response_payload(job.prompt, answer),
            timeout=self._timeout,
        )
        response.raise_for_status()

    def fail_interaction(self, job: ChatJob) -> None:
        response = self._session.patch(
            self._interaction_url(job),
            json={
                "content": (
                    "回答の生成中にエラーが発生しました。"
                    "しばらくしてから再試行してください。"
                ),
                "allowed_mentions": {"parse": []},
            },
            timeout=self._timeout,
        )
        response.raise_for_status()

    @staticmethod
    def _interaction_url(job: ChatJob) -> str:
        return (
            f"{DISCORD_API_BASE}/webhooks/{job.application_id}/"
            f"{job.interaction_token}/messages/@original"
        )
