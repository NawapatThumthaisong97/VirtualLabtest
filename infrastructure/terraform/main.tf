###############################################################################
# main.tf — AI Learner Lab PoC
# Provider: AWS (ap-southeast-1)
# All resources tagged with Project = "virtuallab"
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
  #   bucket = "virtuallab-tfstate"
  #   key    = "poc/terraform.tfstate"
  #   region = "ap-southeast-1"
  # }
}

provider "aws" {
  region = var.aws_region

  default_tags {
    tags = {
      Project     = "virtuallab"
      Environment = var.environment
      ManagedBy   = "terraform"
    }
  }
}
