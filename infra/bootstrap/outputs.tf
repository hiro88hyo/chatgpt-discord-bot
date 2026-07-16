output "workload_identity_provider" {
  value = google_iam_workload_identity_pool_provider.github.name
}

output "deploy_service_account" {
  value = google_service_account.deploy.email
}

output "secret_names" {
  value = {
    discord_public_key = google_secret_manager_secret.discord_public_key.secret_id
    discord_bot_token  = google_secret_manager_secret.discord_bot_token.secret_id
    openai_api_key     = google_secret_manager_secret.openai_api_key.secret_id
    gemini_api_key     = google_secret_manager_secret.gemini_api_key.secret_id
  }
}
