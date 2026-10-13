# IAM role of lab instances (vlab-lab-ecr-pull): ECR pull + autostop

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

# Phase 17: let SkyPilot autostop (down: true) terminate the lab instance.
#
# Skylet on the instance calls EC2 with the instance's own role, which only had
# ECR pull, so autostop failed with UnauthorizedOperation and the instance kept
# running (found when launching from the web portal with lifespan 3 min).
#
# Terminate/stop only instances SkyPilot tagged. Lab containers cannot reach these
# credentials: SkyPilot launches with metadata hop limit 1, and docker's bridge
# network adds a hop.
data "aws_iam_policy_document" "lab_autostop" {
  # Describe* does not support resource-level permissions.
  # terminate_instances also looks up the VPC by name and its security groups
  # (sky/provision/aws/instance.py) before terminating.
  statement {
    actions = [
      "ec2:DescribeInstances",
      "ec2:DescribeVpcs",
      "ec2:DescribeSecurityGroups",
    ]
    resources = ["*"]
  }

  statement {
    actions = [
      "ec2:TerminateInstances",
      "ec2:StopInstances",
    ]
    resources = ["arn:aws:ec2:${var.region}:${data.aws_caller_identity.current.account_id}:instance/*"]

    condition {
      test     = "StringLike"
      variable = "aws:ResourceTag/skypilot-cluster-name"
      values   = ["*"]
    }
  }
}

resource "aws_iam_role_policy" "lab_autostop" {
  name   = "skypilot-autostop"
  role   = aws_iam_role.lab_ecr_pull.id
  policy = data.aws_iam_policy_document.lab_autostop.json
}
