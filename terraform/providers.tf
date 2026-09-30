provider "aws" {
  region  = var.region
  profile = var.aws_profile

  default_tags {
    tags = {
      Project    = "virtual-lab"
      ManagedBy  = "terraform"
      Experiment = "ecr-pull"
    }
  }
}
