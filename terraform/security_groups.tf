# Rules match the tables in EXPERIMENT_TESTING 1:1. One rule per resource, and
# no inline ingress/egress blocks, so Terraform drops AWS's default allow-all
# egress and nothing else sneaks in.
#
# AWS does not allow group names starting with "sg-", so the table names live
# in the Name tag instead.

# --- sg-ts-router ------------------------------------------------------------

resource "aws_security_group" "ts_router" {
  name        = "vlab-ts-router"
  description = "Tailscale subnet router"
  vpc_id      = aws_vpc.main.id

  tags = {
    Name             = "sg-ts-router"
    "vlab:protected" = "true"
  }
}

resource "aws_vpc_security_group_ingress_rule" "ts_router_tailscale_direct" {
  security_group_id = aws_security_group.ts_router.id
  description       = "Tailscale direct connection"
  ip_protocol       = "udp"
  from_port         = 41641
  to_port           = 41641
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_vpc_security_group_egress_rule" "ts_router_https" {
  security_group_id = aws_security_group.ts_router.id
  description       = "Tailscale, DERP, SSM, apt https"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_vpc_security_group_egress_rule" "ts_router_http" {
  security_group_id = aws_security_group.ts_router.id
  description       = "apt"
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_vpc_security_group_egress_rule" "ts_router_udp_all" {
  security_group_id = aws_security_group.ts_router.id
  description       = "WireGuard, STUN"
  ip_protocol       = "udp"
  from_port         = 0
  to_port           = 65535
  cidr_ipv4         = "0.0.0.0/0"
}

resource "aws_vpc_security_group_egress_rule" "ts_router_ssh_to_lab" {
  security_group_id            = aws_security_group.ts_router.id
  description                  = "SSH to private lab instances"
  ip_protocol                  = "tcp"
  from_port                    = 22
  to_port                      = 22
  referenced_security_group_id = aws_security_group.lab_instances.id
}

# --- sg-lab-instances --------------------------------------------------------

resource "aws_security_group" "lab_instances" {
  name        = "vlab-lab-instances"
  description = "Private lab instances"
  vpc_id      = aws_vpc.main.id

  tags = {
    Name = "sg-lab-instances"
  }
}

resource "aws_vpc_security_group_ingress_rule" "lab_ssh_from_router" {
  security_group_id            = aws_security_group.lab_instances.id
  description                  = "SSH through router"
  ip_protocol                  = "tcp"
  from_port                    = 22
  to_port                      = 22
  referenced_security_group_id = aws_security_group.ts_router.id
}

resource "aws_vpc_security_group_ingress_rule" "lab_self_in" {
  security_group_id            = aws_security_group.lab_instances.id
  description                  = "Nodes can communicate"
  ip_protocol                  = "-1"
  referenced_security_group_id = aws_security_group.lab_instances.id
}

resource "aws_vpc_security_group_egress_rule" "lab_https_ipv6" {
  security_group_id = aws_security_group.lab_instances.id
  description       = "ECR dual-stack, https"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  cidr_ipv6         = "::/0"
}

resource "aws_vpc_security_group_egress_rule" "lab_http_ipv6" {
  security_group_id = aws_security_group.lab_instances.id
  description       = "apt"
  ip_protocol       = "tcp"
  from_port         = 80
  to_port           = 80
  cidr_ipv6         = "::/0"
}

resource "aws_vpc_security_group_egress_rule" "lab_https_s3" {
  security_group_id = aws_security_group.lab_instances.id
  description       = "ECR layers on S3 (IPv4 via gateway endpoint)"
  ip_protocol       = "tcp"
  from_port         = 443
  to_port           = 443
  prefix_list_id    = aws_vpc_endpoint.s3.prefix_list_id
}

resource "aws_vpc_security_group_egress_rule" "lab_self_out" {
  security_group_id            = aws_security_group.lab_instances.id
  description                  = "Nodes can communicate"
  ip_protocol                  = "-1"
  referenced_security_group_id = aws_security_group.lab_instances.id
}
