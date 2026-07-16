output "frontend_uri" {
  description = "URL to register as the Discord interaction endpoint."
  value       = google_cloudfunctions2_function.frontend.service_config[0].uri
}

output "frontend_function_name" {
  value = google_cloudfunctions2_function.frontend.name
}

output "backend_function_name" {
  value = google_cloudfunctions2_function.backend.name
}
