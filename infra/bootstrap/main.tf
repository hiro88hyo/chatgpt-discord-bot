locals {
  required_services = toset([
    "artifactregistry.googleapis.com",
    "cloudbuild.googleapis.com",
    "cloudfunctions.googleapis.com",
    "cloudresourcemanager.googleapis.com",
    "eventarc.googleapis.com",
    "iam.googleapis.com",
    "iamcredentials.googleapis.com",
    "parametermanager.googleapis.com",
    "pubsub.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
    "serviceusage.googleapis.com",
    "sts.googleapis.com",
  ])

  deploy_project_roles = toset([
    "roles/cloudfunctions.developer",
    "roles/eventarc.developer",
    "roles/parametermanager.parameterVersionAdder",
    "roles/pubsub.viewer",
    "roles/run.admin",
    "roles/secretmanager.viewer",
    "roles/serviceusage.serviceUsageConsumer",
  ])

  build_project_roles = toset([
    "roles/artifactregistry.writer",
    "roles/logging.logWriter",
    "roles/storage.objectViewer",
  ])

  runtime_service_accounts = {
    frontend = google_service_account.frontend.name
    backend  = google_service_account.backend.name
    build    = google_service_account.build.name
  }
}

resource "google_project_service" "required" {
  for_each = local.required_services

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

resource "google_storage_bucket" "function_source" {
  project                     = var.project_id
  name                        = "${var.project_id}-discord-bot-source"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  depends_on = [google_project_service.required]
}

resource "google_pubsub_topic" "chat_requests" {
  project = var.project_id
  name    = var.pubsub_topic_name

  message_retention_duration = "86400s"

  depends_on = [google_project_service.required]
}

resource "google_secret_manager_secret" "discord_public_key" {
  project   = var.project_id
  secret_id = "discord-public-key"

  replication {
    auto {}
  }

  depends_on = [google_project_service.required]
}

resource "google_secret_manager_secret" "discord_bot_token" {
  project   = var.project_id
  secret_id = "discord-bot-token"

  replication {
    auto {}
  }

  depends_on = [google_project_service.required]
}

resource "google_secret_manager_secret" "openai_api_key" {
  project   = var.project_id
  secret_id = "openai-api-key"

  replication {
    auto {}
  }

  depends_on = [google_project_service.required]
}

resource "google_secret_manager_secret" "gemini_api_key" {
  project   = var.project_id
  secret_id = "gemini-api-key"

  replication {
    auto {}
  }

  depends_on = [google_project_service.required]
}

resource "google_parameter_manager_parameter" "model_config" {
  project         = var.project_id
  parameter_id    = "discord-bot-model-config"
  format          = "JSON"
  deletion_policy = "PREVENT"

  depends_on = [google_project_service.required]
}

resource "google_service_account" "frontend" {
  project      = var.project_id
  account_id   = "discord-bot-frontend"
  display_name = "Discord bot frontend runtime"

  depends_on = [google_project_service.required]
}

resource "google_service_account" "backend" {
  project      = var.project_id
  account_id   = "discord-bot-backend"
  display_name = "Discord bot backend runtime"

  depends_on = [google_project_service.required]
}

resource "google_service_account" "build" {
  project      = var.project_id
  account_id   = "discord-bot-build"
  display_name = "Discord bot Cloud Build"

  depends_on = [google_project_service.required]
}

resource "google_service_account" "deploy" {
  project      = var.project_id
  account_id   = "discord-bot-deploy"
  display_name = "Discord bot GitHub deployment"

  depends_on = [google_project_service.required]
}

resource "google_project_iam_member" "runtime_log_writer" {
  for_each = {
    frontend = google_service_account.frontend.email
    backend  = google_service_account.backend.email
  }

  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${each.value}"
}

resource "google_pubsub_topic_iam_member" "frontend_publisher" {
  project = var.project_id
  topic   = google_pubsub_topic.chat_requests.name
  role    = "roles/pubsub.publisher"
  member  = "serviceAccount:${google_service_account.frontend.email}"
}

resource "google_project_iam_member" "backend_event_receiver" {
  project = var.project_id
  role    = "roles/eventarc.eventReceiver"
  member  = "serviceAccount:${google_service_account.backend.email}"
}

resource "google_project_iam_member" "backend_parameter_accessor" {
  project = var.project_id
  role    = "roles/parametermanager.parameterAccessor"
  member  = "serviceAccount:${google_service_account.backend.email}"
}

resource "google_secret_manager_secret_iam_member" "frontend_public_key" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.discord_public_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.frontend.email}"
}

resource "google_secret_manager_secret_iam_member" "backend_secrets" {
  for_each = {
    discord_bot_token = google_secret_manager_secret.discord_bot_token.secret_id
    openai_api_key    = google_secret_manager_secret.openai_api_key.secret_id
    gemini_api_key    = google_secret_manager_secret.gemini_api_key.secret_id
  }

  project   = var.project_id
  secret_id = each.value
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.backend.email}"
}

resource "google_project_iam_member" "build_roles" {
  for_each = local.build_project_roles

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.build.email}"
}

resource "google_project_iam_member" "deploy_roles" {
  for_each = local.deploy_project_roles

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.deploy.email}"
}

resource "google_storage_bucket_iam_member" "deploy_source_writer" {
  bucket = google_storage_bucket.function_source.name
  role   = "roles/storage.objectAdmin"
  member = "serviceAccount:${google_service_account.deploy.email}"
}

resource "google_service_account_iam_member" "deploy_act_as" {
  for_each = local.runtime_service_accounts

  service_account_id = each.value
  role               = "roles/iam.serviceAccountUser"
  member             = "serviceAccount:${google_service_account.deploy.email}"
}

resource "google_iam_workload_identity_pool" "github" {
  project                   = var.project_id
  workload_identity_pool_id = "github-actions"
  display_name              = "GitHub Actions"

  depends_on = [google_project_service.required]
}

resource "google_iam_workload_identity_pool_provider" "github" {
  project                            = var.project_id
  workload_identity_pool_id          = google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = "github"
  display_name                       = "GitHub OIDC"

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
  }

  attribute_condition = "assertion.repository == '${var.github_repository}' && assertion.ref == 'refs/heads/main'"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account_iam_member" "github_deployer" {
  service_account_id = google_service_account.deploy.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${google_iam_workload_identity_pool.github.name}/attribute.repository/${var.github_repository}"
}
