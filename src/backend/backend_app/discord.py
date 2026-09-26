"""Discord REST API client and conversation extraction."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import requests

from backend_app.models import ChatJob, ConversationMessage

DISCORD_API_BASE = "https://discord.com/api/v10"
QUESTION_LIMIT = 2_000
ANSWER_LIMIT = 4_000
TRUNCATION_MARKER = "\n\n…（長文のため省略しました）"


class DiscordRequestError(RuntimeError):
    """A Discord request error that does not expose the interaction URL."""


def truncate(text: str, limit: int) -> str:
    if len(text) <= limit:
        return text
    return text[: limit - len(TRUNCATION_MARKER)].rstrip() + TRUNCATION_MARKER


def build_response_payload(prompt: str, answer: str, model_name: str) -> dict[str, Any]:
    return {
        "content": truncate(prompt, QUESTION_LIMIT),
        "embeds": [
            {
                "title": "回答",
                "description": truncate(answer, ANSWER_LIMIT),
                "color": 0x55C500,
                "author": {"name": model_name},
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

        # Continue to read messages emitted by the post-refactor two-embed UI.
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
            continue

        # The initial UI puts the prompt in message content and the answer in a
        # single embed. Discord marks application-command responses as type 20.
        content = message.get("content")
        initial_answer = next(
            (
                embed.get("description")
                for embed in embeds
                if isinstance(embed, Mapping)
                and embed.get("title") == "回答"
                and isinstance(embed.get("author"), Mapping)
                and isinstance(embed["author"].get("name"), str)
            ),
            None,
        )
        flags = message.get("flags", 0)
        is_ephemeral = isinstance(flags, int) and bool(flags & (1 << 6))
        if (
            message.get("type") == 20
            and not is_ephemeral
            and isinstance(content, str)
            and content
            and isinstance(initial_answer, str)
        ):
            conversation.extend(
                [
                    ConversationMessage(role="user", content=content),
                    ConversationMessage(role="assistant", content=initial_answer),
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

    def complete_interaction(self, job: ChatJob, answer: str, model_name: str) -> None:
        self._patch_interaction(
            job, build_response_payload(job.prompt, answer, model_name)
        )

    def fail_interaction(self, job: ChatJob) -> None:
        self._patch_interaction(
            job,
            {
                "content": (
                    "回答の生成中にエラーが発生しました。"
                    "しばらくしてから再試行してください。"
                ),
                "allowed_mentions": {"parse": []},
            },
        )

    def _patch_interaction(self, job: ChatJob, payload: dict[str, Any]) -> None:
        try:
            response = self._session.patch(
                self._interaction_url(job),
                json=payload,
                timeout=self._timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            status = exc.response.status_code if exc.response is not None else None
            detail = f" (HTTP {status})" if isinstance(status, int) else ""
            raise DiscordRequestError(
                f"Discord interaction request failed{detail}"
            ) from None

    @staticmethod
    def _interaction_url(job: ChatJob) -> str:
        return (
            f"{DISCORD_API_BASE}/webhooks/{job.application_id}/"
            f"{job.interaction_token}/messages/@original"
        )
