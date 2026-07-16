variable "project_id" {
  description = "Google Cloud project ID."
  type        = string
}

variable "region" {
  description = "Region for both Cloud Run functions."
  type        = string
  default     = "asia-northeast1"
}

variable "frontend_function_name" {
  description = "HTTP function that accepts Discord interactions."
  type        = string
  default     = "chatgpt-api-discord"
}

variable "backend_function_name" {
  description = "Pub/Sub function that calls the AI provider."
  type        = string
  default     = "chatgpt-api-discord-backend"
}

variable "pubsub_topic_name" {
  description = "Topic connecting the frontend and backend."
  type        = string
  default     = "discord-chat-requests"
}

variable "default_ai_provider" {
  description = "Default provider when the Discord option is omitted."
  type        = string
  default     = "openai"

  validation {
    condition     = contains(["openai", "gemini"], var.default_ai_provider)
    error_message = "default_ai_provider must be openai or gemini."
  }
}

variable "openai_model" {
  description = "OpenAI model ID passed to the Responses API."
  type        = string
  default     = "gpt-4o-mini"
}

variable "gemini_model" {
  description = "Gemini model ID."
  type        = string
  default     = "gemini-2.5-flash"
}

variable "history_message_limit" {
  description = "Maximum Discord messages fetched for thread context."
  type        = number
  default     = 20

  validation {
    condition     = var.history_message_limit > 0 && var.history_message_limit <= 100
    error_message = "history_message_limit must be between 1 and 100."
  }
}
