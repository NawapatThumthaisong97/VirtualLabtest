# Ubuntu 24.04 amd64 from Canonical. Phase 8 test instances reuse this.
data "aws_ami" "ubuntu" {
  most_recent = true
  owners      = ["099720109477"]

  filter {
    name   = "name"
    values = ["ubuntu/images/hvm-ssd-gp3/ubuntu-noble-24.04-amd64-server-*"]
  }

  filter {
    name   = "architecture"
    values = ["x86_64"]
  }
}

# --- IAM for SSM (break-glass access, no SSH port) ---------------------------

data "aws_iam_policy_document" "ec2_assume" {
  statement {
    actions = ["sts:AssumeRole"]

    principals {
      type        = "Service"
      identifiers = ["ec2.amazonaws.com"]
    }
  }
}

resource "aws_iam_role" "ts_router" {
  name               = "vlab-ts-router"
  assume_role_policy = data.aws_iam_policy_document.ec2_assume.json
}

resource "aws_iam_role_policy_attachment" "ts_router_ssm" {
  role       = aws_iam_role.ts_router.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "ts_router" {
  name = "vlab-ts-router"
  role = aws_iam_role.ts_router.name
}

# --- Subnet router instance --------------------------------------------------

# Tailscale is installed by hand through Session Manager, so no user_data and
# no auth key here.
resource "aws_instance" "ts_router" {
  ami                    = data.aws_ami.ubuntu.id
  instance_type          = "t3.micro"
  subnet_id              = aws_subnet.public_a.id
  vpc_security_group_ids = [aws_security_group.ts_router.id]
  iam_instance_profile   = aws_iam_instance_profile.ts_router.name

  metadata_options {
    http_endpoint = "enabled"
    http_tokens   = "required"
  }

  # A newer Ubuntu AMI must not replace the router (and wipe Tailscale).
  lifecycle {
    ignore_changes = [ami]
  }

  tags = {
    Name             = "vlab-ts-router"
    "vlab:protected" = "true"
  }
}
