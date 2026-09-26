"""Google Cloud Functions entry point for queued chat requests."""

import functions_framework
from backend_app.handler import handle_chat


@functions_framework.cloud_event
def main(cloud_event) -> None:
    """Generate an AI answer and complete a deferred Discord interaction."""
    handle_chat(cloud_event)
