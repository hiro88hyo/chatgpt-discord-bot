# Deployment infrastructure

Terraform manages the two Cloud Run functions. The state bucket is isolated in `state/`, and
stable foundation resources are kept in `bootstrap/`. Both are intentionally applied by an
administrator. Normal code deployments use the root configuration through GitHub Actions.

## 1. Create the Terraform state bucket

Requirements:

- An existing Google Cloud project with billing enabled
- Terraform 1.8 or newer
- Local Application Default Credentials with permission to create a Cloud Storage bucket

Create the remote state bucket first. This small configuration keeps local state; back its
state file up securely after applying it.

```bash
gcloud auth application-default login

terraform -chdir=infra/state init
terraform -chdir=infra/state apply -var="project_id=YOUR_PROJECT_ID"
```

The bucket has object versioning, public-access prevention, and Terraform `prevent_destroy`
enabled.

## 2. Bootstrap Google Cloud

This step requires permission to enable APIs and create IAM, Pub/Sub, Secret Manager, and
Cloud Storage resources. It also needs the GitHub repository name in `owner/name` format.

```bash
terraform -chdir=infra/bootstrap init \
  -backend-config="bucket=YOUR_PROJECT_ID-discord-bot-tfstate" \
  -backend-config="prefix=production/bootstrap"

terraform -chdir=infra/bootstrap apply \
  -var="project_id=YOUR_PROJECT_ID" \
  -var="github_repository=OWNER/REPOSITORY"
```

WIF accepts tokens only from the configured repository's `main` branch. Application secrets
are never stored in Terraform state.

## 3. Add secret versions

Bootstrap creates Secret Manager resources, but never puts secret values in Terraform state.
Add the initial versions interactively:

```bash
gcloud secrets versions add discord-public-key --data-file=/secure/path/discord-public-key
gcloud secrets versions add discord-bot-token --data-file=/secure/path/discord-bot-token
gcloud secrets versions add openai-api-key --data-file=/secure/path/openai-api-key
gcloud secrets versions add gemini-api-key --data-file=/secure/path/gemini-api-key
```

All four secrets need at least one enabled version before the first deployment. Avoid putting
real values in shell history; using a password manager or redirected secure file is preferable.

Bootstrap also creates the `discord-bot-model-config` JSON parameter. Its versions are managed
outside Terraform so normal model changes never trigger a Function deployment and never alter
Terraform state.

## 4. Configure GitHub

Create a `production` GitHub Environment and enable required reviewers. Add these repository
or environment variables using the values printed by `terraform output` in `infra/bootstrap`:

| GitHub variable | Value |
| --- | --- |
| `GCP_PROJECT_ID` | Google Cloud project ID |
| `GCP_REGION` | `asia-northeast1` or the selected region |
| `GCP_WORKLOAD_IDENTITY_PROVIDER` | `workload_identity_provider` output |
| `GCP_DEPLOY_SERVICE_ACCOUNT` | `deploy_service_account` output |

No service-account JSON key or application secret is stored in GitHub.

## 5. Set the model configuration

Run the `Update model configuration` workflow from the `main` branch. Enter all three values;
each run creates an auditable Parameter Manager version. Warm backend instances refresh the
latest valid version within 60 seconds. To roll back, run the workflow again with the previous
values.

## 6. Deploy

Merges to `main` that change `src/` or `infra/` trigger `.github/workflows/deploy.yml`.
The workflow runs tests, creates a Terraform plan, waits for the production environment's
approval, and applies the plan. It can also be started manually with `workflow_dispatch`.
Manual deployments must run from the `main` branch because WIF rejects every other ref.

After the first deployment, get `frontend_uri` from the workflow's Terraform output and set it
as the Discord application's interaction endpoint.

## Importing existing functions

If functions with the configured names already exist, import them before the first apply:

```bash
terraform -chdir=infra init \
  -backend-config="bucket=YOUR_PROJECT_ID-discord-bot-tfstate" \
  -backend-config="prefix=production/functions"

terraform -chdir=infra import \
  -var="project_id=YOUR_PROJECT_ID" \
  google_cloudfunctions2_function.frontend \
  projects/YOUR_PROJECT_ID/locations/asia-northeast1/functions/discord-interaction

terraform -chdir=infra import \
  -var="project_id=YOUR_PROJECT_ID" \
  google_cloudfunctions2_function.backend \
  projects/YOUR_PROJECT_ID/locations/asia-northeast1/functions/discord-chat-worker
```

Run a plan after importing. Do not apply until every proposed replacement or deletion has been
reviewed.
