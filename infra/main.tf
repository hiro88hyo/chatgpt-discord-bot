locals {
  source_bucket_name = "${var.project_id}-discord-bot-source"

  frontend_service_account_email = "discord-bot-frontend@${var.project_id}.iam.gserviceaccount.com"
  backend_service_account_email  = "discord-bot-backend@${var.project_id}.iam.gserviceaccount.com"
  build_service_account_email    = "discord-bot-build@${var.project_id}.iam.gserviceaccount.com"
  build_service_account_name     = "projects/${var.project_id}/serviceAccounts/${local.build_service_account_email}"
}

data "archive_file" "frontend" {
  type             = "zip"
  source_dir       = "${path.module}/../src/frontend"
  output_path      = "${path.module}/.frontend-source.zip"
  output_file_mode = "0666"
  excludes         = [".env", ".env.*", "**/__pycache__/**", "**/*.pyc"]
}

data "archive_file" "backend" {
  type             = "zip"
  source_dir       = "${path.module}/../src/backend"
  output_path      = "${path.module}/.backend-source.zip"
  output_file_mode = "0666"
  excludes         = [".env", ".env.*", "**/__pycache__/**", "**/*.pyc"]
}

resource "google_storage_bucket_object" "frontend_source" {
  name   = "frontend-${data.archive_file.frontend.output_sha256}.zip"
  bucket = local.source_bucket_name
  source = data.archive_file.frontend.output_path
}

resource "google_storage_bucket_object" "backend_source" {
  name   = "backend-${data.archive_file.backend.output_sha256}.zip"
  bucket = local.source_bucket_name
  source = data.archive_file.backend.output_path
}

resource "google_cloudfunctions2_function" "frontend" {
  project     = var.project_id
  name        = var.frontend_function_name
  location    = var.region
  description = "Validates Discord interactions and publishes chat requests."

  build_config {
    runtime         = "python311"
    entry_point     = "main"
    service_account = local.build_service_account_name

    source {
      storage_source {
        bucket = google_storage_bucket_object.frontend_source.bucket
        object = google_storage_bucket_object.frontend_source.name
      }
    }
  }

  service_config {
    available_cpu                    = "1"
    available_memory                 = "256M"
    timeout_seconds                  = 10
    min_instance_count               = 0
    max_instance_count               = 3
    max_instance_request_concurrency = 20
    ingress_settings                 = "ALLOW_ALL"
    all_traffic_on_latest_revision   = true
    service_account_email            = local.frontend_service_account_email

    environment_variables = {
      GCP_PROJECT_ID    = var.project_id
      PUBSUB_TOPIC_CHAT = var.pubsub_topic_name
    }

    secret_environment_variables {
      key        = "DISCORD_PUBLIC_KEY"
      project_id = var.project_id
      secret     = "discord-public-key"
      version    = "latest"
    }
  }

  depends_on = [google_cloudfunctions2_function.backend]
}

resource "google_cloudfunctions2_function" "backend" {
  project     = var.project_id
  name        = var.backend_function_name
  location    = var.region
  description = "Generates AI answers for queued Discord chat requests."

  build_config {
    runtime         = "python311"
    entry_point     = "main"
    service_account = local.build_service_account_name

    source {
      storage_source {
        bucket = google_storage_bucket_object.backend_source.bucket
        object = google_storage_bucket_object.backend_source.name
      }
    }
  }

  service_config {
    available_memory               = "512M"
    timeout_seconds                = 300
    min_instance_count             = 0
    max_instance_count             = 3
    ingress_settings               = "ALLOW_INTERNAL_ONLY"
    all_traffic_on_latest_revision = true
    service_account_email          = local.backend_service_account_email

    environment_variables = {
      GCP_PROJECT_ID           = var.project_id
      DEFAULT_AI_PROVIDER      = var.default_ai_provider
      OPENAI_MODEL             = var.openai_model
      GEMINI_MODEL             = var.gemini_model
      MODEL_CONFIG_PARAMETER   = "discord-bot-model-config"
      MODEL_CONFIG_TTL_SECONDS = "60"
      HISTORY_MESSAGE_LIMIT    = tostring(var.history_message_limit)
    }

    secret_environment_variables {
      key        = "DISCORD_BOT_TOKEN"
      project_id = var.project_id
      secret     = "discord-bot-token"
      version    = "latest"
    }

    secret_environment_variables {
      key        = "OPENAI_API_KEY"
      project_id = var.project_id
      secret     = "openai-api-key"
      version    = "latest"
    }

    secret_environment_variables {
      key        = "GEMINI_API_KEY"
      project_id = var.project_id
      secret     = "gemini-api-key"
      version    = "latest"
    }
  }

  event_trigger {
    trigger_region        = var.region
    event_type            = "google.cloud.pubsub.topic.v1.messagePublished"
    pubsub_topic          = "projects/${var.project_id}/topics/${var.pubsub_topic_name}"
    retry_policy          = "RETRY_POLICY_RETRY"
    service_account_email = local.backend_service_account_email
  }
}

resource "google_cloud_run_service_iam_member" "frontend_public_invoker" {
  project  = var.project_id
  location = google_cloudfunctions2_function.frontend.location
  service  = google_cloudfunctions2_function.frontend.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_service_iam_member" "backend_event_invoker" {
  project  = var.project_id
  location = google_cloudfunctions2_function.backend.location
  service  = google_cloudfunctions2_function.backend.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${local.backend_service_account_email}"
}
