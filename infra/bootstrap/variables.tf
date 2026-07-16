variable "project_id" {
  description = "Google Cloud project ID."
  type        = string
}

variable "github_repository" {
  description = "GitHub repository in owner/name format allowed to deploy."
  type        = string

  validation {
    condition     = can(regex("^[^/]+/[^/]+$", var.github_repository))
    error_message = "github_repository must use the owner/name format."
  }
}

variable "region" {
  description = "Google Cloud region."
  type        = string
  default     = "asia-northeast1"
}

variable "pubsub_topic_name" {
  description = "Topic connecting the frontend and backend."
  type        = string
  default     = "discord-chat-requests"
}
