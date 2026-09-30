resource "aws_key_pair" "pete" {
  key_name   = "vlab-ecr-pull-pete"
  public_key = file(pathexpand(var.ssh_public_key_path))
}

locals {
  test_instances = {
    a = aws_subnet.private_a.id
    b = aws_subnet.private_b.id
  }
}

# One instance per private subnet/AZ. No public IP: SSH comes through the
# Tailscale router, and the only ways out are IPv6 (EIGW) and S3 (endpoint).
resource "aws_instance" "test" {
  for_each = local.test_instances

  ami                         = data.aws_ami.ubuntu.id
  instance_type               = "t3.micro"
  subnet_id                   = each.value
  vpc_security_group_ids      = [aws_security_group.lab_instances.id]
  key_name                    = aws_key_pair.pete.key_name
  associate_public_ip_address = false

  metadata_options {
    http_endpoint               = "enabled"
    http_tokens                 = "required"
    http_put_response_hop_limit = 1
  }

  lifecycle {
    ignore_changes = [ami]
  }

  tags = {
    Name = "vlab-test-${each.key}"
  }
}
