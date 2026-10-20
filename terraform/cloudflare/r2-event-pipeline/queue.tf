# Create Cloudflare queue
resource "cloudflare_queue" "r2_event_queue" {
  account_id   = var.cloudflare_account_id
  queue_name   = "virtual-lab-event-queue-tf"
}

# Configure R2 Event Notification to Queue
resource "cloudflare_r2_bucket_event_notification" "bucket_trigger" {
  account_id  = var.cloudflare_account_id
  bucket_name = cloudflare_r2_bucket.test_bucket.name
  queue_id    = cloudflare_queue.r2_event_queue.id

  rules = [{
    actions = ["PutObject", "CompleteMultipartUpload"]
  }]
}
