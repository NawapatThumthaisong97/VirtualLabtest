###############################################################################
# vpc.tf — VPC, Subnets (Public / Private), IGW, NAT Gateway, Route Tables
#
# Architecture (from ARCHITECTURE.md):
#   PUBLIC SUBNET  (10.0.1.0/24) → NAT GW + Internet GW + t4g.nano
#   PRIVATE SUBNET (10.0.2.0/24) → EC2 Spot Workers (no public IP)
#                                   outbound via NAT GW
###############################################################################

# ── VPC ───────────────────────────────────────────────────────────────────────

resource "aws_vpc" "virtuallab" {
  cidr_block           = var.vpc_cidr
  enable_dns_support   = true
  enable_dns_hostnames = true

  tags = { Name = "virtuallab-vpc" }
}

# ── Internet Gateway (attached to VPC, used by Public Subnet) ─────────────────

resource "aws_internet_gateway" "virtuallab" {
  vpc_id = aws_vpc.virtuallab.id

  tags = { Name = "virtuallab-igw" }
}

# ── Public Subnet ─────────────────────────────────────────────────────────────

resource "aws_subnet" "public" {
  vpc_id                  = aws_vpc.virtuallab.id
  cidr_block              = var.public_subnet_cidr
  availability_zone       = var.availability_zone
  map_public_ip_on_launch = true   # t4g.nano needs a public IP for Tailscale

  tags = { Name = "virtuallab-subnet-public" }
}

# ── Private Subnet ────────────────────────────────────────────────────────────
# CONSTRAINT 4: map_public_ip_on_launch = false — no worker ever gets a public IP

resource "aws_subnet" "private" {
  vpc_id                  = aws_vpc.virtuallab.id
  cidr_block              = var.private_subnet_cidr
  availability_zone       = var.availability_zone
  map_public_ip_on_launch = false   # ENFORCES Constraint #4

  tags = { Name = "virtuallab-subnet-private" }
}

# ── Elastic IP for NAT Gateway ────────────────────────────────────────────────

resource "aws_eip" "nat" {
  domain = "vpc"

  tags = { Name = "virtuallab-nat-eip" }

  depends_on = [aws_internet_gateway.virtuallab]
}

# ── NAT Gateway (sits in Public Subnet, gives Private Subnet outbound internet) ─

resource "aws_nat_gateway" "virtuallab" {
  allocation_id = aws_eip.nat.id
  subnet_id     = aws_subnet.public.id

  tags = { Name = "virtuallab-nat-gw" }

  depends_on = [aws_internet_gateway.virtuallab]
}

# ── Route Table: Public Subnet → Internet Gateway ─────────────────────────────

resource "aws_route_table" "public" {
  vpc_id = aws_vpc.virtuallab.id

  route {
    cidr_block = "0.0.0.0/0"
    gateway_id = aws_internet_gateway.virtuallab.id
  }

  tags = { Name = "virtuallab-rt-public" }
}

resource "aws_route_table_association" "public" {
  subnet_id      = aws_subnet.public.id
  route_table_id = aws_route_table.public.id
}

# ── Route Table: Private Subnet → NAT Gateway ─────────────────────────────────
# CONSTRAINT 7: Private workers reach Docker Hub / internet via NAT, not VPN

resource "aws_route_table" "private" {
  vpc_id = aws_vpc.virtuallab.id

  route {
    cidr_block     = "0.0.0.0/0"
    nat_gateway_id = aws_nat_gateway.virtuallab.id
  }

  tags = { Name = "virtuallab-rt-private" }
}

resource "aws_route_table_association" "private" {
  subnet_id      = aws_subnet.private.id
  route_table_id = aws_route_table.private.id
}

# ── Security Group: t4g.nano Tailscale Gateway ────────────────────────────────
# Allows:
#   - Tailscale WireGuard (UDP 41641) from any — required for mesh VPN
#   - SSH from VPC only (for emergency debugging only)
#   - All outbound

resource "aws_security_group" "tailscale_gateway" {
  name        = "virtuallab-sg-tailscale-gateway"
  description = "SG for the always-on Tailscale Subnet Router (t4g.nano)"
  vpc_id      = aws_vpc.virtuallab.id

  ingress {
    description = "Tailscale WireGuard"
    from_port   = 41641
    to_port     = 41641
    protocol    = "udp"
    cidr_blocks = ["0.0.0.0/0"]
  }

  ingress {
    description = "SSH from within VPC only (debug)"
    from_port   = 22
    to_port     = 22
    protocol    = "tcp"
    cidr_blocks = [var.vpc_cidr]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "virtuallab-sg-tailscale-gateway" }
}

# ── Security Group: EC2 Spot ML Workers ───────────────────────────────────────
# Allows:
#   - SSH from t4g.nano gateway SG only (SkyPilot needs SSH to dispatch jobs)
#   - All outbound (Docker Hub via NAT GW, S3 via VPC Endpoint)
# CONSTRAINT 1: NO inbound from 0.0.0.0/0

resource "aws_security_group" "spot_workers" {
  name        = "virtuallab-sg-spot-workers"
  description = "SG for ephemeral EC2 Spot ML workers. No public inbound."
  vpc_id      = aws_vpc.virtuallab.id

  ingress {
    description     = "SSH from Tailscale Gateway only"
    from_port       = 22
    to_port         = 22
    protocol        = "tcp"
    security_groups = [aws_security_group.tailscale_gateway.id]
  }

  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }

  tags = { Name = "virtuallab-sg-spot-workers" }
}
