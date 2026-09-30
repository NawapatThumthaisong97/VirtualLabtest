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
