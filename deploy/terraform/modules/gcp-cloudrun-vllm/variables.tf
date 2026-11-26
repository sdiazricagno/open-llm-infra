variable "project_id" {
  description = "GCP project."
  type        = string
}

variable "region" {
  description = "Region with Cloud Run L4 GPUs, e.g. us-central1 or europe-west1."
  type        = string
  default     = "us-central1"
}

variable "name" {
  description = "Cloud Run service name."
  type        = string
  default     = "vllm"
}

variable "model" {
  description = "Hugging Face repo served by vLLM."
  type        = string
  default     = "Qwen/Qwen2.5-1.5B-Instruct"
}

variable "max_model_len" {
  description = "Maximum context length vLLM allocates KV cache for."
  type        = number
  default     = 8192
}

variable "vllm_image" {
  description = "vLLM OpenAI-compatible server image."
  type        = string
  default     = "vllm/vllm-openai:latest"
}

variable "max_instances" {
  description = "Upper bound on GPU instances; subject to project GPU quota."
  type        = number
  default     = 2
}

variable "min_instances" {
  description = "Warm instances; 0 scales to zero and stops GPU billing when idle."
  type        = number
  default     = 0
}

variable "concurrency" {
  description = "Concurrent requests per instance before Cloud Run adds another."
  type        = number
  default     = 16
}

variable "hf_token_secret" {
  description = "Optional Secret Manager secret id holding a Hugging Face token for gated models."
  type        = string
  default     = ""
}

variable "invoker_members" {
  description = "Principals allowed to call the service, e.g. the gateway's service account."
  type        = list(string)
  default     = []
}

variable "deletion_protection" {
  description = "Protect the service from terraform destroy."
  type        = bool
  default     = false
}
