# Network: VPC, gateways, subnets, route tables, S3 gateway endpoint

resource "aws_vpc" "main" {
  cidr_block                       = "10.10.0.0/16"
  assign_generated_ipv6_cidr_block = true
  enable_dns_support               = true
  enable_dns_hostnames             = true

  tags = {
    Name = "vlab-ecr-pull"
  }
}

# IPv4 in/out for the public subnet (Tailscale router).
resource "aws_internet_gateway" "igw" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "vlab-ecr-pull-igw"
  }
}

# IPv6 out only for the private subnets. Nothing from the internet can start a
# connection in.
resource "aws_egress_only_internet_gateway" "eigw" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "vlab-ecr-pull-eigw"
  }
}

# Tailscale subnet router lives here. IPv4 only, no IPv6.
resource "aws_subnet" "public_a" {
  vpc_id                  = aws_vpc.main.id
  cidr_block              = "10.10.1.0/24"
  availability_zone       = "ap-southeast-1a"
  map_public_ip_on_launch = true

  tags = {
    Name = "vlab-ecr-pull-public-a"
  }
}

# Local routes (10.10.0.0/16 and the VPC IPv6 /56) are added by AWS.
resource "aws_route_table" "public" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "rt-public"
  }
}

resource "aws_route" "public_ipv4_default" {
  route_table_id         = aws_route_table.public.id
  destination_cidr_block = "0.0.0.0/0"
  gateway_id             = aws_internet_gateway.igw.id
}

resource "aws_route_table_association" "public_a" {
  subnet_id      = aws_subnet.public_a.id
  route_table_id = aws_route_table.public.id
}

# Lab instances live here, in two AZs. No public IPv4 and no NAT on purpose:
# the only way out is IPv6 through the EIGW (plus the S3 endpoint in Phase 5).
resource "aws_subnet" "private_a" {
  vpc_id                          = aws_vpc.main.id
  cidr_block                      = "10.10.2.0/24"
  ipv6_cidr_block                 = cidrsubnet(aws_vpc.main.ipv6_cidr_block, 8, 2)
  availability_zone               = "ap-southeast-1a"
  assign_ipv6_address_on_creation = true
  map_public_ip_on_launch         = false

  tags = {
    Name = "vlab-ecr-pull-private-a"
  }
}

resource "aws_subnet" "private_b" {
  vpc_id                          = aws_vpc.main.id
  cidr_block                      = "10.10.3.0/24"
  ipv6_cidr_block                 = cidrsubnet(aws_vpc.main.ipv6_cidr_block, 8, 3)
  availability_zone               = "ap-southeast-1b"
  assign_ipv6_address_on_creation = true
  map_public_ip_on_launch         = false

  tags = {
    Name = "vlab-ecr-pull-private-b"
  }
}

# No 0.0.0.0/0 route on purpose. The S3 prefix list route is added by the
# endpoint association in Phase 5, not here.
resource "aws_route_table" "private" {
  vpc_id = aws_vpc.main.id

  tags = {
    Name = "rt-private"
  }
}

resource "aws_route" "private_ipv6_default" {
  route_table_id              = aws_route_table.private.id
  destination_ipv6_cidr_block = "::/0"
  egress_only_gateway_id      = aws_egress_only_internet_gateway.eigw.id
}

resource "aws_route_table_association" "private_a" {
  subnet_id      = aws_subnet.private_a.id
  route_table_id = aws_route_table.private.id
}

resource "aws_route_table_association" "private_b" {
  subnet_id      = aws_subnet.private_b.id
  route_table_id = aws_route_table.private.id
}

# Private instances reach S3 (ECR image layers) over IPv4 through this
# endpoint instead of a NAT. Associating it with rt-private makes AWS add the
# pl-xxx -> vpce-xxx route for us.
resource "aws_vpc_endpoint" "s3" {
  vpc_id            = aws_vpc.main.id
  service_name      = "com.amazonaws.${var.region}.s3"
  vpc_endpoint_type = "Gateway"
  route_table_ids   = [aws_route_table.private.id]

  tags = {
    Name = "vlab-ecr-pull-s3"
  }
}
