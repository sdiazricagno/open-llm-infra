resource "google_cloud_run_v2_service" "vllm" {
  project             = var.project_id
  name                = var.name
  location            = var.region
  ingress             = "INGRESS_TRAFFIC_ALL"
  deletion_protection = var.deletion_protection

  template {
    max_instance_request_concurrency = var.concurrency
    timeout                          = "600s"
    gpu_zonal_redundancy_disabled    = true

    scaling {
      min_instance_count = var.min_instances
      max_instance_count = var.max_instances
    }

    node_selector {
      accelerator = "nvidia-l4"
    }

    containers {
      image = var.vllm_image
      args = [
        "--model", var.model,
        "--served-model-name", var.model,
        "--max-model-len", tostring(var.max_model_len),
        "--port", "8000",
      ]

      ports {
        container_port = 8000
      }

      resources {
        limits = {
          cpu              = "4"
          memory           = "16Gi"
          "nvidia.com/gpu" = "1"
        }
        cpu_idle          = false
        startup_cpu_boost = true
      }

      dynamic "env" {
        for_each = var.hf_token_secret == "" ? [] : [var.hf_token_secret]
        content {
          name = "HF_TOKEN"
          value_source {
            secret_key_ref {
              secret  = env.value
              version = "latest"
            }
          }
        }
      }

      startup_probe {
        initial_delay_seconds = 30
        period_seconds        = 10
        failure_threshold     = 60
        timeout_seconds       = 5
        http_get {
          path = "/health"
          port = 8000
        }
      }
    }
  }
}

resource "google_cloud_run_v2_service_iam_member" "invoker" {
  for_each = toset(var.invoker_members)
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_service.vllm.name
  role     = "roles/run.invoker"
  member   = each.value
}
