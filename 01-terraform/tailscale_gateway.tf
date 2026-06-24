###############################################################################
# tailscale_gateway.tf — Always-On t4g.nano Tailscale Subnet Router
#
# CONSTRAINTS ENFORCED:
#   #5 — No Tailscale on Spot workers; this gateway advertises the full VPC CIDR
#   #6 — ASG Min=1, Max=1 (On-Demand) for self-healing, no Spot here
#
# The gateway runs `tailscaled` + `tailscale up --advertise-routes=<VPC_CIDR>`.
# SkyPilot on On-Prem (100.x.x.x) reaches any private worker (10.0.2.x) via:
#   On-Prem → Tailscale VPN → this t4g.nano → worker private IP
###############################################################################

# ── Latest Amazon Linux 2023 ARM64 AMI ───────────────────────────────────────

data "aws_ami" "amazon_linux_2023_arm64" {
  most_recent = true
  owners      = ["amazon"]

  filter {
    name   = "name"
    values = ["al2023-ami-*-arm64"]
  }

  filter {
    name   = "virtualization-type"
    values = ["hvm"]
  }
}

# ── IAM Role for t4g.nano (SSM access, no SSH required in prod) ───────────────

resource "aws_iam_role" "tailscale_gateway" {
  name = "virtuallab-tailscale-gateway-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect    = "Allow"
      Principal = { Service = "ec2.amazonaws.com" }
      Action    = "sts:AssumeRole"
    }]
  })
}

resource "aws_iam_role_policy_attachment" "tailscale_gateway_ssm" {
  role       = aws_iam_role.tailscale_gateway.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonSSMManagedInstanceCore"
}

resource "aws_iam_instance_profile" "tailscale_gateway" {
  name = "virtuallab-tailscale-gateway-profile"
  role = aws_iam_role.tailscale_gateway.name
}

# ── Launch Template ───────────────────────────────────────────────────────────

resource "aws_launch_template" "tailscale_gateway" {
  name_prefix   = "virtuallab-tailscale-gw-"
  image_id      = data.aws_ami.amazon_linux_2023_arm64.id
  instance_type = "t4g.nano"

  # Optional: attach key pair for SSH debugging (leave empty to disable)
  dynamic "key_name_spec" {
    for_each = var.gateway_key_pair_name != "" ? [1] : []
    content {}
  }

  key_name = var.gateway_key_pair_name != "" ? var.gateway_key_pair_name : null

  iam_instance_profile {
    name = aws_iam_instance_profile.tailscale_gateway.name
  }

  network_interfaces {
    associate_public_ip_address = true   # Needs public IP to reach Tailscale DERP
    security_groups             = [aws_security_group.tailscale_gateway.id]
    subnet_id                   = aws_subnet.public.id
    delete_on_termination       = true
  }

  # User Data: installs Tailscale, advertises VPC CIDR, enables IP forwarding
  # bootstrap-gateway.sh is the canonical reference — this inline version mirrors it.
  user_data = base64encode(templatefile("${path.module}/userdata/bootstrap-gateway.sh.tftpl", {
    tailscale_auth_key = var.tailscale_auth_key
    vpc_cidr           = var.vpc_cidr
  }))

  tag_specifications {
    resource_type = "instance"
    tags = {
      Name        = "virtuallab-tailscale-gateway"
      Role        = "tailscale-subnet-router"
      Project     = "virtuallab"
      Environment = var.environment
    }
  }

  lifecycle {
    create_before_destroy = true
  }
}

# ── Auto Scaling Group: Min=1, Max=1 (On-Demand, self-healing) ───────────────
# CONSTRAINT 6: Always-on, never Spot. ASG ensures automatic replacement on failure.

resource "aws_autoscaling_group" "tailscale_gateway" {
  name                = "virtuallab-asg-tailscale-gateway"
  min_size            = 1
  max_size            = 1
  desired_capacity    = 1
  vpc_zone_identifier = [aws_subnet.public.id]

  launch_template {
    id      = aws_launch_template.tailscale_gateway.id
    version = "$Latest"
  }

  # Health check: EC2 replaces instance if it becomes unhealthy
  health_check_type         = "EC2"
  health_check_grace_period = 120

  tag {
    key                 = "Name"
    value               = "virtuallab-tailscale-gateway"
    propagate_at_launch = true
  }

  tag {
    key                 = "Project"
    value               = "virtuallab"
    propagate_at_launch = true
  }

  lifecycle {
    create_before_destroy = true
  }
}
