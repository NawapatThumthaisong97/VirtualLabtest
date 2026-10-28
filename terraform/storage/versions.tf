# Bucket เก็บไฟล์ของเว็บ (รูปปกวิชา / เอกสาร lab / เอกสารวิชา) — แยก state จาก terraform/ ชุดหลัก
# (ชุดหลักไม่มี state ในเครื่อง apply แล้วจะสร้าง ECR / VPC ซ้ำ ห้ามรวมกัน)
terraform {
  required_version = ">= 1.5"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
  }
}

provider "aws" {
  region  = var.region
  profile = var.aws_profile

  default_tags {
    tags = {
      Project   = "virtual-lab"
      Component = "web-storage"
      ManagedBy = "terraform/storage"
    }
  }
}
