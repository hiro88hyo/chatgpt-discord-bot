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

バックエンド:

- `GCP_PROJECT_ID`
- `DISCORD_BOT_TOKEN`
- `OPENAI_API_KEY`（OpenAI を使う場合）
- `GEMINI_API_KEY`（Gemini を使う場合）
- `MODEL_CONFIG_PARAMETER`（任意、既定値 `discord-bot-model-config`）
- `MODEL_CONFIG_TTL_SECONDS`（任意、既定値 `60`）
- `DEFAULT_AI_PROVIDER`（Parameter取得失敗時の既定値）
- `OPENAI_MODEL`（Parameter取得失敗時の既定値）
- `GEMINI_MODEL`（Parameter取得失敗時の既定値）
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

インフラとFunctionの設定は `infra/` のTerraformで管理します。通常のデプロイは
`main` へのマージを契機にGitHub Actionsが実行し、Workload Identity Federationで
Google Cloudへ鍵レス認証します。

初回だけ、管理者が以下を行います。

1. `infra/state` でstate bucketを作成
2. `infra/bootstrap` でIAM、WIF、Pub/Sub、Secret、Parameterを作成
3. Secret Managerへ秘密値の初期バージョンを追加
4. GitHubの `production` EnvironmentとRepository Variablesを設定
5. workflowを手動実行、または `main` へマージ

詳しい手順、既存Functionのimport方法、必要なGitHub変数は
[`infra/README.md`](infra/README.md) を参照してください。

## モデルの変更

モデル設定はGoogle Cloud Parameter Managerから最大60秒間隔で更新されるため、
Functionの再デプロイは不要です。GitHub Actionsの `Update model configuration` を
`main` ブランチから手動実行し、既定プロバイダーと両モデルIDを入力してください。

設定取得に失敗した場合は、直近に取得できた設定を使います。起動後に一度も取得
できていない場合だけ、環境変数の既定値へフォールバックします。

## セキュリティ上の注意

- Discord の署名検証前に interaction を処理しません。
- Bot token と API key をログへ出しません。
- Discord の mention 展開を無効にして、モデル出力による意図しない通知を防ぎます。
- リポジトリ作成時にソースへ直書きされていた Discord Bot token は失効・再発行してください。
