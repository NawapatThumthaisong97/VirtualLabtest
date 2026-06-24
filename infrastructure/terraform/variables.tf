###############################################################################
# variables.tf — Input variables for the AI Learner Lab PoC stack
###############################################################################

variable "aws_region" {
  description = "AWS region where all resources are deployed."
  type        = string
  default     = "ap-southeast-1"
}

variable "environment" {
  description = "Short environment name used in tags and resource names."
  type        = string
  default     = "poc"
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC."
  type        = string
  default     = "10.0.0.0/16"
}

variable "public_subnet_cidr" {
  description = "CIDR for the Public Subnet (hosts NAT GW + t4g.nano gateway)."
  type        = string
  default     = "10.0.1.0/24"
}

variable "private_subnet_cidr" {
  description = "CIDR for the Private Subnet (hosts EC2 Spot ML workers, no Public IP)."
  type        = string
  default     = "10.0.2.0/24"
}

variable "availability_zone" {
  description = "AZ to deploy subnets in. Use a single AZ for PoC simplicity."
  type        = string
  default     = "ap-southeast-1a"
}

# ── t4g.nano Tailscale Gateway ────────────────────────────────────────────────

variable "tailscale_auth_key" {
  description = <<-EOT
    Tailscale reusable auth key for the VPN gateway instance.
    Generate at: https://login.tailscale.com/admin/settings/keys
    Mark as REUSABLE so the ASG can re-register after self-healing.
    NEVER commit this value — pass via TF_VAR_tailscale_auth_key env var or
    a secrets manager.
  EOT
  type        = string
  sensitive   = true
}

variable "gateway_key_pair_name" {
  description = <<-EOT
    Name of an existing AWS EC2 Key Pair for SSH access to the t4g.nano gateway
    (for debugging only). Leave empty to disable SSH.
  EOT
  type        = string
  default     = ""
}

# ── IAM / S3 ─────────────────────────────────────────────────────────────────

variable "ml_bucket_name" {
  description = "Name of the S3 bucket used for ML dataset input and model weight output."
  type        = string
  default     = "ailab-ml-artifacts"
}

variable "iam_user_name" {
  description = "IAM user created for SkyPilot / FastAPI to provision EC2 Spot workers and access S3."
  type        = string
  default     = "ailab-skypilot"
}
