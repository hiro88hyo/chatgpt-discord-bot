resource "google_storage_bucket" "terraform_state" {
  project                     = var.project_id
  name                        = "${var.project_id}-discord-bot-tfstate"
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = true
  }

  lifecycle {
    prevent_destroy = true
  }
}
