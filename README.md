# ChatGPT Discord Bot

Discord の `/chat` コマンドを OpenAI または Gemini へ渡し、回答を Discord に返す
Google Cloud Functions 向けのボットです。

## 構成

```text
Discord
  └─ HTTP interaction
      └─ frontend Cloud Function（署名検証・受付）
          └─ Pub/Sub
              └─ backend Cloud Function（履歴取得・AI 呼び出し・回答更新）
```

フロントエンドは Discord の3秒制限内に deferred response を返します。バックエンドは
生成完了後にその応答を `PATCH` し、スレッドでは過去のボット回答を会話履歴として利用します。

## 必要なもの

- Python 3.11
- Google Cloud CLI
- Discord Application / Bot
- OpenAI API キーまたは Gemini API キー
- Pub/Sub topic（以下では `discord-chat-requests`）

## 環境変数

`.env.example` を参考に、秘密情報は Git に入れず Cloud Functions の Secret Manager 連携などで設定してください。

フロントエンド:

- `GCP_PROJECT_ID`
- `PUBSUB_TOPIC_CHAT`
- `DISCORD_PUBLIC_KEY`
- `DEFAULT_AI_PROVIDER`（任意、`openai` または `gemini`）

バックエンド:

- `DISCORD_BOT_TOKEN`
- `OPENAI_API_KEY`（OpenAI を使う場合）
- `GEMINI_API_KEY`（Gemini を使う場合）
- `OPENAI_MODEL`（任意、既定値 `gpt-4o-mini`）
- `GEMINI_MODEL`（任意、既定値 `gemini-2.5-flash`）
- `SYSTEM_PROMPT`（任意）
- `HISTORY_MESSAGE_LIMIT`（任意、既定値 `20`）

## ローカル開発

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
pytest
ruff check .
ruff format --check .
```

フロントエンドを起動する場合:

```bash
functions-framework --source src/frontend/main.py --target main --port 8080
```

## Discord コマンド登録

`DISCORD_APPLICATION_ID` と `DISCORD_BOT_TOKEN` を環境変数に設定して実行します。

```bash
python scripts/register_discord_commands.py
```

このスクリプトは `PUT` でグローバルコマンド一覧を同期します。反映には時間がかかる場合があります。

## Google Cloud へのデプロイ

```bash
gcloud pubsub topics create discord-chat-requests

gcloud functions deploy discord-interaction \
  --gen2 \
  --runtime=python311 \
  --region=asia-northeast1 \
  --source=src/frontend \
  --entry-point=main \
  --trigger-http \
  --allow-unauthenticated \
  --set-env-vars="GCP_PROJECT_ID=${PROJECT_ID},PUBSUB_TOPIC_CHAT=discord-chat-requests,DEFAULT_AI_PROVIDER=openai" \
  --set-secrets="DISCORD_PUBLIC_KEY=discord-public-key:latest"

gcloud functions deploy discord-chat-worker \
  --gen2 \
  --runtime=python311 \
  --region=asia-northeast1 \
  --source=src/backend \
  --entry-point=main \
  --trigger-topic=discord-chat-requests \
  --set-env-vars="OPENAI_MODEL=gpt-4o-mini,GEMINI_MODEL=gemini-2.5-flash" \
  --set-secrets="DISCORD_BOT_TOKEN=discord-bot-token:latest,OPENAI_API_KEY=openai-api-key:latest,GEMINI_API_KEY=gemini-api-key:latest"
```

デプロイ前に、各 Function のサービスアカウントへ必要最小限の Pub/Sub と
Secret Manager 権限を付与してください。

## セキュリティ上の注意

- Discord の署名検証前に interaction を処理しません。
- Bot token と API key をログへ出しません。
- Discord の mention 展開を無効にして、モデル出力による意図しない通知を防ぎます。
- リポジトリ作成時にソースへ直書きされていた Discord Bot token は失効・再発行してください。
