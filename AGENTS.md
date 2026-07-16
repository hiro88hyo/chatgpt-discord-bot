# Repository guide

- Runtime: Python 3.11 on Google Cloud Functions Gen 2.
- Keep `src/frontend/main.py` and `src/backend/main.py` as thin deployment entry points.
- Do not log Discord interaction tokens, bot tokens, API keys, prompts, or model responses.
- Keep secrets in environment variables or Secret Manager; never commit `.env` files.
- Run `pytest`, `ruff check .`, and `ruff format --check .` before committing.
- Run `terraform fmt -check -recursive infra` and validate both Terraform roots after infrastructure changes.
- Keep frontend and backend requirements self-contained because each directory is deployed separately.
