"""Google Cloud Functions entry point for Discord interactions."""

from __future__ import annotations

import logging

import functions_framework
from flask import Request, jsonify
from frontend_app.config import ConfigurationError, Settings
from frontend_app.discord import (
    APPLICATION_COMMAND,
    PING,
    InteractionError,
    parse_chat_request,
    verify_request_signature,
)
from frontend_app.publisher import ChatPublisher

logger = logging.getLogger(__name__)


def _message(content: str, *, ephemeral: bool = True) -> tuple[dict, int]:
    flags = 64 if ephemeral else 0
    return {"type": 4, "data": {"content": content, "flags": flags}}, 200


@functions_framework.http
def main(request: Request):
    """Validate a Discord interaction and enqueue chat work."""
    if request.method == "GET":
        return jsonify({"status": "ok"}), 200

    try:
        settings = Settings.from_env()
    except ConfigurationError:
        logger.exception("Frontend configuration is invalid")
        return jsonify({"error": "service is not configured"}), 500

    raw_body = request.get_data(cache=True)
    if not verify_request_signature(
        request.headers, raw_body, settings.discord_public_key
    ):
        return jsonify({"error": "invalid request signature"}), 401

    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        return _message("リクエストの形式が正しくありません。")

    interaction_type = body.get("type")
    if interaction_type == PING:
        return jsonify({"type": PING}), 200
    if interaction_type != APPLICATION_COMMAND:
        return _message("この操作には対応していません。")

    try:
        chat_request = parse_chat_request(body)
        ChatPublisher(settings).publish(chat_request)
    except InteractionError as exc:
        return _message(str(exc))
    except Exception:
        logger.exception("Failed to enqueue Discord interaction")
        return _message(
            "現在リクエストを受け付けられません。少し待ってから再試行してください。"
        )

    # Discord requires an acknowledgement within three seconds. The backend edits
    # this deferred response after the model finishes generating an answer.
    return jsonify({"type": 5}), 200
