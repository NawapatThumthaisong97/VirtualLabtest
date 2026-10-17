variable "region" {
  description = "AWS region for the experiment (Singapore)."
  type        = string
  default     = "ap-southeast-1"
}

# No default on purpose: pass it every time so we never fall back to the
# root/default profile or the SkyPilot IAM user.
variable "aws_profile" {
  description = "Pete's own AWS CLI profile. Never the SkyPilot IAM user."
  type        = string
}

# Public key only. The private key never leaves the laptop.
variable "ssh_public_key_path" {
  description = "Path to the SSH public key for the test instances."
  type        = string
  default     = "~/.ssh/id_ed25519.pub"
}
