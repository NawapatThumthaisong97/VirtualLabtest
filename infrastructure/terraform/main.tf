###############################################################################
# main.tf — AI Learner Lab PoC
# Provider: AWS (ap-southeast-1)
# All resources tagged with Project = "ailab"
###############################################################################

terraform {
  required_version = ">= 1.7"

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }

  # ── Optional: Remote state in S3 (uncomment after bucket exists) ────────────
  # backend "s3" {
  #   bucket = "ailab-tfstate"
  #   key    = "poc/terraform.tfstate"
  #   region = "ap-southeast-1"
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "ailab"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
