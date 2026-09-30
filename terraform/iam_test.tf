# Phase 11: let the test instances get their own ECR token instead of us
# copying one in. Pull only, and only from vlab/hello.

resource "aws_iam_role" "lab_ecr_pull" {
  name               = "vlab-lab-ecr-pull"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

data "aws_iam_policy_document" "lab_ecr_pull" {
  # GetAuthorizationToken does not support resource-level permissions.
  statement {
    actions   = ["ecr:GetAuthorizationToken"]
    resources = ["*"]
  }

  statement {
    actions = [
      "ecr:BatchCheckLayerAvailability",
      "ecr:BatchGetImage",
      "ecr:GetDownloadUrlForLayer",
    ]
    resources = [aws_ecr_repository.hello.arn]
  }
}

resource "aws_iam_role_policy" "lab_ecr_pull" {
  name   = "ecr-pull-vlab-hello"
  role   = aws_iam_role.lab_ecr_pull.id
  policy = data.aws_iam_policy_document.lab_ecr_pull.json
}

resource "aws_iam_instance_profile" "lab_ecr_pull" {
  name = "vlab-lab-ecr-pull"
  role = aws_iam_role.lab_ecr_pull.name
}
