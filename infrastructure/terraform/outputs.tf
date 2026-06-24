###############################################################################
# outputs.tf — Key values to use in subsequent Day-0 steps
#
# ⚠️  SENSITIVE outputs (IAM access keys) are marked sensitive = true.
#    To view them run:
#      terraform output -json | jq .
#    Then immediately pipe into the secret creation script.
###############################################################################

# ── VPC ───────────────────────────────────────────────────────────────────────

output "vpc_id" {
  description = "VPC ID. Needed for SkyPilot sky_config.yaml vpc_id field."
  value       = aws_vpc.ailab.id
}

output "vpc_cidr" {
  description = "VPC CIDR block. Used by Tailscale gateway --advertise-routes."
  value       = aws_vpc.ailab.cidr_block
}

# ── Subnets ───────────────────────────────────────────────────────────────────

output "public_subnet_id" {
  description = "Public Subnet ID (t4g.nano gateway lives here)."
  value       = aws_subnet.public.id
}

output "private_subnet_id" {
  description = "Private Subnet ID. Set this in SkyPilot sky_config.yaml as the worker subnet."
  value       = aws_subnet.private.id
}

# ── Security Groups ───────────────────────────────────────────────────────────

output "sg_spot_workers_id" {
  description = "Security Group ID for EC2 Spot workers. Set in SkyPilot sky_config.yaml."
  value       = aws_security_group.spot_workers.id
}

# ── S3 ────────────────────────────────────────────────────────────────────────

output "ml_bucket_name" {
  description = "S3 bucket name for ML datasets and model weights."
  value       = aws_s3_bucket.ml_artifacts.id
}

output "ml_bucket_arn" {
  description = "S3 bucket ARN."
  value       = aws_s3_bucket.ml_artifacts.arn
}

# ── IAM Credentials (SENSITIVE) ──────────────────────────────────────────────
# These are used to create the Kubernetes Secret in Step 1c.
# Run: terraform output -json | jq '{key: .iam_access_key_id.value, secret: .iam_secret_access_key.value}'

output "iam_access_key_id" {
  description = "AWS_ACCESS_KEY_ID for the ailab-skypilot IAM user."
  value       = aws_iam_access_key.skypilot.id
  sensitive   = true
}

output "iam_secret_access_key" {
  description = "AWS_SECRET_ACCESS_KEY for the ailab-skypilot IAM user. Use in: create-k8s-secrets.sh"
  value       = aws_iam_access_key.skypilot.secret
  sensitive   = true
}

# ── ASG ───────────────────────────────────────────────────────────────────────

output "tailscale_gateway_asg_name" {
  description = "Auto Scaling Group name for the Tailscale gateway."
  value       = aws_autoscaling_group.tailscale_gateway.name
}
