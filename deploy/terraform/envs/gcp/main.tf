terraform {
  required_version = ">= 1.6"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = ">= 6.20"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

variable "project_id" {
  description = "GCP project."
  type        = string
}

variable "region" {
  description = "Region with Cloud Run L4 GPUs."
  type        = string
  default     = "us-central1"
}

variable "gateway_service_account" {
  description = "Service account email the gateway uses to call Cloud Run."
  type        = string
}

module "qwen_1_5b" {
  source          = "../../modules/gcp-cloudrun-vllm"
  project_id      = var.project_id
  region          = var.region
  name            = "vllm-qwen2-5-1-5b"
  model           = "Qwen/Qwen2.5-1.5B-Instruct"
  min_instances   = 0
  max_instances   = 2
  invoker_members = ["serviceAccount:${var.gateway_service_account}"]
}

output "VLLM_QWEN2_5_1_5B_API_BASE" {
  description = "Set on the gateway."
  value       = module.qwen_1_5b.api_base
}
