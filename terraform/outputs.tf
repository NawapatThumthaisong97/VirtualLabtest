# Outputs grow with each phase.

# Phase 1
output "vpc_id" {
  value = aws_vpc.main.id
}

output "vpc_ipv6_cidr" {
  value = aws_vpc.main.ipv6_cidr_block
}

# Phase 3
output "public_a_subnet_id" {
  value = aws_subnet.public_a.id
}
