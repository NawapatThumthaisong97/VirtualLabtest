data "aws_caller_identity" "current" {}

locals {
  # ชื่อ bucket ต้องไม่ซ้ำทั้งโลก ต่อท้ายด้วย account id แบบ bucket อื่นของโปรเจกต์
  bucket_name = "vlab-web-storage-${data.aws_caller_identity.current.account_id}"
}

# ---------- bucket (private ทั้งหมด เข้าถึงผ่าน backend / presigned URL เท่านั้น) ----------
resource "aws_s3_bucket" "web" {
  bucket = local.bucket_name
}

resource "aws_s3_bucket_public_access_block" "web" {
  bucket                  = aws_s3_bucket.web.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

resource "aws_s3_bucket_ownership_controls" "web" {
  bucket = aws_s3_bucket.web.id
  rule {
    object_ownership = "BucketOwnerEnforced" # ปิด ACL ใช้ policy อย่างเดียว
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "web" {
  bucket = aws_s3_bucket.web.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm = "AES256"
    }
  }
}

# versioning: อัปเอกสารทับ / ลบ แล้วยังกู้ได้ (ดู lifecycle ด้านล่าง)
resource "aws_s3_bucket_versioning" "web" {
  bucket = aws_s3_bucket.web.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_lifecycle_configuration" "web" {
  bucket     = aws_s3_bucket.web.id
  depends_on = [aws_s3_bucket_versioning.web]

  rule {
    id     = "expire-old-versions"
    status = "Enabled"
    filter {}
    noncurrent_version_expiration {
      noncurrent_days = var.noncurrent_days
    }
    abort_incomplete_multipart_upload {
      days_after_initiation = 1
    }
  }
}

resource "aws_s3_bucket_cors_configuration" "web" {
  bucket = aws_s3_bucket.web.id
  cors_rule {
    allowed_methods = ["GET", "HEAD"]
    allowed_origins = var.web_origins
    allowed_headers = ["*"]
    max_age_seconds = 3600
  }
}

# ---------- สิทธิ์ของ backend (เฉพาะ bucket นี้ ไม่แตะ policy เดิมของ user) ----------
resource "aws_iam_user_policy" "backend_storage" {
  name = "vlab-web-storage"
  user = var.backend_iam_user
  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Sid      = "ListBucket"
        Effect   = "Allow"
        Action   = ["s3:ListBucket"]
        Resource = aws_s3_bucket.web.arn
      },
      {
        Sid      = "ReadWriteObjects"
        Effect   = "Allow"
        Action   = ["s3:GetObject", "s3:PutObject", "s3:DeleteObject"]
        Resource = "${aws_s3_bucket.web.arn}/*"
      },
    ]
  })
}
