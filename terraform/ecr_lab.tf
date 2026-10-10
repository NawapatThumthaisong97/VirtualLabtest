# Phase 13: lab image for SkyPilot docker mode (moved from the on-prem registry).
resource "aws_ecr_repository" "music_lab_ide" {
  name = "vlab/music-lab-ide"

  image_scanning_configuration {
    scan_on_push = true
  }
}

resource "aws_ecr_lifecycle_policy" "music_lab_ide" {
  repository = aws_ecr_repository.music_lab_ide.name

  policy = jsonencode({
    rules = [{
      rulePriority = 1
      description  = "Keep last 10 images"
      selection = {
        tagStatus   = "any"
        countType   = "imageCountMoreThan"
        countNumber = 10
      }
      action = {
        type = "expire"
      }
    }]
  })
}
