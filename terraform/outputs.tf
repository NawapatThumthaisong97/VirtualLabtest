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

# Phase 7
output "router_instance_id" {
  value = aws_instance.ts_router.id
}

output "router_public_ip" {
  value = aws_instance.ts_router.public_ip
}

# Phase 8
output "test_instances" {
  value = {
    for k, i in aws_instance.test : k => {
      az   = i.availability_zone
      ipv4 = i.private_ip
      ipv6 = i.ipv6_addresses
    }
  }
}

# Phase 9
output "ecr_repository_url" {
  description = "Normal endpoint (IPv4). Push from the laptop."
  value       = aws_ecr_repository.hello.repository_url
}

output "ecr_dualstack_host" {
  description = "Dual-stack registry host. Pull from the private instances."
  value       = "${aws_ecr_repository.hello.registry_id}.dkr-ecr.${var.region}.on.aws"
}
