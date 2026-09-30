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
