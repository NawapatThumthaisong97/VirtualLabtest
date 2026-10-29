# ใส่ใน ansible/group_vars/all.yml → webservice_storage_s3_bucket
output "bucket_name" {
  value = aws_s3_bucket.web.bucket
}

output "bucket_region" {
  value = var.region
}
