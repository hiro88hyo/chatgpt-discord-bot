# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Overview

This is a Discord bot that integrates with ChatGPT/OpenAI and Google Gemini APIs. It uses Google Cloud Functions for serverless deployment with a frontend/backend architecture connected via Pub/Sub.

## Commands

### Deployment Commands

Frontend deployment (HTTP trigger):
```bash
gcloud functions deploy discord-interaction --gen2 --runtime=python311 --region=asia-northeast1 --source=./src/frontend --entry-point=main --trigger-http --allow-unauthenticated
```

Backend deployment (Pub/Sub trigger):
```bash
gcloud functions deploy openai-api-hook --gen2 --runtime=python311 --region=asia-northeast1 --source=./src/backend --entry-point=subscribe --trigger-topic=openai_api_hook
```

Alternative deployment (without Gen2):
```bash
# Frontend
gcloud functions deploy discord-interaction --runtime=python39 --region=asia-northeast1 --source=./src/frontend --entry-point=main --trigger-http --allow-unauthenticated

# Backend
gcloud functions deploy openai-api-hook --runtime=python39 --region=asia-northeast1 --source=./src/backend --entry-point=subscribe --trigger-topic=openai_api_hook
```

### IAM Configuration

Set IAM policy for frontend function:
```bash
gcloud functions add-iam-policy-binding discord-interaction --region=asia-northeast1 --member="allUsers" --role="roles/cloudfunctions.invoker"
```

Create service identity for backend function (if needed):
```bash
gcloud beta functions add-invoker-policy-binding openai-api-hook --region=asia-northeast1 --member="serviceAccount:discord-chatgpt-366714@appspot.gserviceaccount.com"
```

## Architecture

The bot follows a serverless microservices pattern:
```
Discord User → Discord API → Frontend Function → Pub/Sub → Backend Function → AI API → Discord Response
```

### Frontend (`src/frontend/main.py`)
- Validates Discord webhook signatures using Ed25519
- Handles `/chat` and `/summary` slash commands
- Publishes messages to Pub/Sub topic `openai_api_hook`
- Returns deferred responses to Discord

### Backend (`src/backend/main.py`)
- Triggered by Pub/Sub messages
- Fetches conversation history from Discord
- Calls OpenAI GPT or Google Gemini APIs
- Posts responses back to Discord via webhooks
- Handles message threading and 4000 character limit

## Environment Variables

### Frontend (.env)
- `DISCORD_PUBLIC_KEY` - For signature verification
- `DISCORD_BOT_TOKEN` - Bot authentication token
- `DISCORD_APPLICATION_ID` - Application identifier

### Backend (.env)
- `OPENAI_API_KEY` - OpenAI API key
- `DISCORD_BOT_TOKEN` - Bot authentication token
- `PROJECT_ID` - Google Cloud project ID

## Project Structure

```
src/
├── frontend/
│   ├── main.py              # Discord webhook handler
│   ├── bot_register_command.py  # Command registration utility
│   └── requirements.txt
├── backend/
│   ├── main.py              # AI processing service
│   └── requirements.txt
└── get_messages.py          # Message retrieval utility
```

## Development Notes

- Python 3.11 runtime
- Uses Flask framework for HTTP handling
- Google Cloud Libraries for Pub/Sub and Logging
- PyNaCl for Discord signature verification
- Supports multiple AI engines (GPT-4o, GPT-3.5-turbo, Gemini)
- Message context maintained through Discord thread history
- Japanese language support included