# Create R2 Bucket
resource "cloudflare_r2_bucket" "test_bucket" {
  account_id = var.cloudflare_account_id
  name       = var.bucket_name
  location   = "apac"
}

# Configure the CORS Policy for Bucket
resource "cloudflare_r2_bucket_cors" "upload_bucket_cors" {
  account_id  = var.cloudflare_account_id
  bucket_name = cloudflare_r2_bucket.test_bucket.name

  rules = [{
    id = "AllowReactViteAndRegistryClient"
    allowed = {

      methods = ["PUT", "GET", "HEAD", "DELETE"]
      origins = concat(
        ["http://localhost:5173", "http://localhost:3000"],
        var.app_domain != "" ? ["https://${var.app_domain}"] : []
      )
      headers = ["*"]
    }

    expose_headers  = ["ETag"]
    max_age_seconds = 3600
  }]
}
