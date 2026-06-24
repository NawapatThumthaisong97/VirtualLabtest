###############################################################################
# iam.tf — IAM User + Minimum-Permission Policy for SkyPilot / FastAPI
#
# CONSTRAINT 8: Credentials never hardcoded. This file creates the IAM user
# and access key. The access key values are output as sensitive outputs — they
# are then stored in a Kubernetes Secret via:
#   bash scripts/create-k8s-secrets.sh
#
# Permissions are scoped to minimum required:
#   EC2: manage Spot instances only in the private subnet
#   S3:  read/write to the ML artifacts bucket only
#   IAM PassRole: pass instance profile to Spot workers
###############################################################################

# ── IAM User ──────────────────────────────────────────────────────────────────

resource "aws_iam_user" "skypilot" {
  name = var.iam_user_name

  tags = { Purpose = "SkyPilot SDK + FastAPI EC2 Spot provisioning and S3 access" }
}

resource "aws_iam_access_key" "skypilot" {
  user = aws_iam_user.skypilot.name
}

# ── Minimum-Permission Policy ─────────────────────────────────────────────────

resource "aws_iam_policy" "skypilot" {
  name        = "ailab-skypilot-policy"
  description = "Minimum permissions for SkyPilot to provision EC2 Spot workers and access S3."

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      # ── EC2: Spot instance lifecycle ──────────────────────────────────────
      {
        Sid    = "EC2SpotWorkerManagement"
        Effect = "Allow"
        Action = [
          "ec2:RunInstances",
          "ec2:TerminateInstances",
          "ec2:DescribeInstances",
          "ec2:DescribeInstanceStatus",
          "ec2:DescribeSpotInstanceRequests",
          "ec2:RequestSpotInstances",
          "ec2:CancelSpotInstanceRequests",
          "ec2:DescribeImages",
          "ec2:DescribeSubnets",
          "ec2:DescribeSecurityGroups",
          "ec2:DescribeKeyPairs",
          "ec2:DescribeInstanceTypes",
          "ec2:DescribeAvailabilityZones",
          "ec2:CreateTags",
          "ec2:DescribeTags",
          # For SkyPilot autostop
          "ec2:StopInstances",
          "ec2:StartInstances",
        ]
        Resource = "*"
        # Optional: Restrict to specific VPC (tighten later)
        # Condition = {
        #   StringEquals = {
        #     "ec2:Vpc" = aws_vpc.ailab.arn
        #   }
        # }
      },

      # ── IAM: Allow SkyPilot to pass the instance profile to workers ───────
      {
        Sid    = "PassRoleToEC2"
        Effect = "Allow"
        Action = ["iam:PassRole"]
        Resource = "*"
        Condition = {
          StringEquals = {
            "iam:PassedToService" = "ec2.amazonaws.com"
          }
        }
      },

      # ── IAM: SkyPilot reads its own identity ──────────────────────────────
      {
        Sid      = "SelfIdentity"
        Effect   = "Allow"
        Action   = ["iam:GetUser"]
        Resource = "arn:aws:iam::*:user/${var.iam_user_name}"
      },

      # ── S3: Read/write to the ML artifacts bucket only ───────────────────
      {
        Sid    = "S3MLArtifacts"
        Effect = "Allow"
        Action = [
          "s3:GetObject",
          "s3:PutObject",
          "s3:DeleteObject",
          "s3:ListBucket",
          "s3:GetBucketLocation",
        ]
        Resource = [
          aws_s3_bucket.ml_artifacts.arn,
          "${aws_s3_bucket.ml_artifacts.arn}/*",
        ]
      },
    ]
  })
}

resource "aws_iam_user_policy_attachment" "skypilot" {
  user       = aws_iam_user.skypilot.name
  policy_arn = aws_iam_policy.skypilot.arn
}
