# ChatGPT Discord Bot

Discord の `/chat` コマンドを OpenAI、Gemini、OpenRouter のいずれかへ渡し、回答を Discord に返す
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
- 利用するプロバイダーの API キー（OpenAI、Gemini、OpenRouter）
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
- `OPENROUTER_API_KEY`（OpenRouter を使う場合）
- `MODEL_CONFIG_PARAMETER`（任意、既定値 `discord-bot-model-config`）
- `MODEL_CONFIG_TTL_SECONDS`（任意、既定値 `60`）
- `DEFAULT_AI_PROVIDER`（Parameter取得失敗時の既定値）
- `OPENAI_MODEL`（Parameter取得失敗時の既定値）
- `GEMINI_MODEL`（Parameter取得失敗時の既定値）
- `OPENROUTER_MODEL`（Parameter取得失敗時の既定値。初期値 `typesafe/jev-router`）
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
サーバー専用コマンドも使う場合は `DISCORD_GUILD_ID` を設定すると、
グローバルコマンドと同じ内容へ更新できます。

```bash
python scripts/register_discord_commands.py
```

このスクリプトは `PUT` でグローバルコマンド一覧を同期します。反映には時間がかかる場合があります。
`/chat` の `model` では Gemini 3.8 Flash、Claude Opus 5.5、GPT-6 Astra、
DeepSeek V4.1 Flash、Claude Fable 5.1、Jev Router から選べます。`model` を選ぶと
`provider` を省略しても OpenRouter を使います。`model` を省略した場合は、
従来どおりプロバイダーの既定モデルを使います。
`provider` に OpenAI または Gemini を選ぶ場合、`model` は指定できません。
候補を変更したときは、Function のデプロイ後にこのスクリプトを再実行してください。

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
`main` ブランチから手動実行し、既定プロバイダーと3つのモデルIDを入力してください。
既存のモデル設定に `openrouter_model` がない場合は、環境変数の
`OPENROUTER_MODEL` を使用します。
`provider` と `model` を省略した `/chat` は既定で OpenRouter の `typesafe/jev-router` を使います。
Jev Router はリクエストに応じて回答モデルを選びます。
固定したい場合は [OpenRouter のモデル一覧](https://openrouter.ai/models) にあるモデルIDを設定してください。
スラッシュコマンドの `model` を選んだリクエストでは、そのモデルIDが既定設定より優先されます。
OpenRouter が別のモデルへ振り分けた場合、回答には「指定モデル → 実際のモデル」を表示します。

設定取得に失敗した場合は、直近に取得できた設定を使います。起動後に一度も取得
できていない場合だけ、環境変数の既定値へフォールバックします。

## セキュリティ上の注意

- Discord の署名検証前に interaction を処理しません。
- Bot token と API key をログへ出しません。
- Discord の mention 展開を無効にして、モデル出力による意図しない通知を防ぎます。
- リポジトリ作成時にソースへ直書きされていた Discord Bot token は失効・再発行してください。
