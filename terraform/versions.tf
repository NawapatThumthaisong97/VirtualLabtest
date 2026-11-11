terraform {
  required_version = ">= 1.10" # use_lockfile ใน backend.tf

  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}
