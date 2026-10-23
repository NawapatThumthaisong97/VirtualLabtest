# Create Worker Script
resource "cloudflare_workers_script" "queue_consumer" {
  account_id  = var.cloudflare_account_id
  script_name = "virtual-lab-webhook-dispatcher"
  content     = file("${path.module}/../../../cloudflare-worker/index.js")

  main_module = "index.js"

  bindings = [
    {
      name = "WEBHOOK_URL"
      text = var.webhook_url
      type = "plain_text"
    },
    {
      name = "WEBHOOK_SECRET"
      text = var.webhook_secret
      type = "secret_text"
    }
  ]
}

# Create Queue Consumer and Connect Worker to Queue
resource "cloudflare_queue_consumer" "r2_queue_consumer" {
  account_id  = var.cloudflare_account_id
  queue_id    = cloudflare_queue.r2_event_queue.id
  script_name = cloudflare_workers_script.queue_consumer.script_name
  type        = "worker"

  settings = {
    batch_size       = 10
    max_concurrency  = 2
    max_retries      = 3
    max_wait_time_ms = 5000
    retry_delay      = 3
  }
}
