###############################################################################
# s3_endpoint.tf — VPC S3 Gateway Endpoint
#
# CONSTRAINT 7: S3 traffic from Private Subnet workers must NOT leave through
# the NAT Gateway. It must stay on the AWS backbone via the VPC Gateway Endpoint.
# This is free, eliminates NAT GW data-processing charges, and keeps dataset
# and model transfers within AWS.
###############################################################################

# ── S3 VPC Gateway Endpoint ───────────────────────────────────────────────────

resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.virtuallab.id
  service_name      = "com.amazonaws.${var.aws_region}.s3"
  vpc_endpoint_type = "Gateway"

  # Associate with both route tables so both Public + Private subnets can use it
  route_table_ids = [
    aws_route_table.public.id,
    aws_route_table.private.id,
  ]

  tags = { Name = "virtuallab-s3-vpc-endpoint" }
}

# ── S3 Bucket for ML Artifacts ────────────────────────────────────────────────

resource "aws_s3_bucket" "ml_artifacts" {
  bucket = var.ml_bucket_name

  # Prevent accidental deletion in production — change to false to allow destroy
  force_destroy = true

  tags = { Name = var.ml_bucket_name }
}

resource "aws_s3_bucket_versioning" "ml_artifacts" {
  bucket = aws_s3_bucket.ml_artifacts.id

  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "ml_artifacts" {
  bucket = aws_s3_bucket.ml_artifacts.id

  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# Block all public access to the bucket — data is accessed via VPC Endpoint only
resource "aws_s3_bucket_public_access_block" "ml_artifacts" {
  bucket = aws_s3_bucket.ml_artifacts.id

  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}
