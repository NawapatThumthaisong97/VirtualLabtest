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

# Phase 4
output "private_subnet_ipv6_cidrs" {
  value = {
    private_a = aws_subnet.private_a.ipv6_cidr_block
    private_b = aws_subnet.private_b.ipv6_cidr_block
  }
}

# Phase 5
output "s3_prefix_list_id" {
  value = aws_vpc_endpoint.s3.prefix_list_id
}
