variable "cloudflare_api_token" {
  description = "Cloudflare API Token for managing R2, Queues, and Workers"
  type        = string
  sensitive   = true
}

variable "cloudflare_account_id" {
  description = "Cloudflare Account ID"
  type        = string
}

variable "webhook_url" {
  description = "Webhook URL for receiving R2 events"
  type        = string
}

variable "webhook_secret" {
  description = "Secret token for webhook authentication"
  type        = string
  sensitive   = true
}

variable "bucket_name" {
  description = "Name of the R2 bucket"
  type        = string
  default     = "film-mini-project"
}

variable "app_domain" {
  description = "Production domain for CORS configuration"
  type        = string
  default     = ""
}
