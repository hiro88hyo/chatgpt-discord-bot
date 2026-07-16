variable "project_id" {
  description = "Google Cloud project ID."
  type        = string
}

variable "region" {
  description = "Location of the Terraform state bucket."
  type        = string
  default     = "asia-northeast1"
}
