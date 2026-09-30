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
