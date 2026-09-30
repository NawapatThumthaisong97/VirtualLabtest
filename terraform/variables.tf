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
