from __future__ import annotations

from backend_app.models import OPENROUTER_MODEL_IDS as BACKEND_MODEL_IDS
from frontend_app.discord import OPENROUTER_MODEL_IDS as FRONTEND_MODEL_IDS

from scripts import register_discord_commands


def test_register_chat_model_choices_match_runtime_validation(monkeypatch) -> None:
    captured = {}

    class Response:
        def raise_for_status(self) -> None:
            return None

    def put(url, **kwargs) -> Response:
        captured["url"] = url
        captured["options"] = kwargs["json"][0]["options"]
        return Response()

    monkeypatch.setenv("DISCORD_APPLICATION_ID", "app")
    monkeypatch.setenv("DISCORD_BOT_TOKEN", "token")
    monkeypatch.setattr(register_discord_commands.requests, "put", put)

    register_discord_commands.main()

    assert captured["url"].endswith("/applications/app/commands")
    options = {option["name"]: option for option in captured["options"]}
    model_ids = {choice["value"] for choice in options["model"]["choices"]}
    assert model_ids == FRONTEND_MODEL_IDS == BACKEND_MODEL_IDS
    assert len(model_ids) <= 25
    assert options["model"]["required"] is False
