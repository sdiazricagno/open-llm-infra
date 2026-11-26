variable "name" {
  description = "Prefix for every resource."
  type        = string
}

variable "vpc_id" {
  description = "VPC to deploy into."
  type        = string
}

variable "subnet_ids" {
  description = "At least two subnets in different AZs for the load balancer and instances."
  type        = list(string)
}

variable "allowed_cidrs" {
  description = "CIDRs allowed to reach the load balancer. Keep this to your gateway or VPN range."
  type        = list(string)
}

variable "instance_type" {
  description = "GPU instance type, e.g. g4dn.xlarge (T4), g6.xlarge (L4), g5.xlarge (A10G)."
  type        = string
  default     = "g6.xlarge"
}

variable "use_spot" {
  description = "Run on spot capacity; cheaper but interruptible."
  type        = bool
  default     = true
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

variable "hf_token_ssm_parameter" {
  description = "Optional SSM SecureString holding a Hugging Face token for gated models."
  type        = string
  default     = ""
}

variable "min_size" {
  description = "Minimum instances; 0 lets the group sleep when idle."
  type        = number
  default     = 0
}

variable "max_size" {
  description = "Maximum instances."
  type        = number
  default     = 2
}

variable "desired_capacity" {
  description = "Initial instances."
  type        = number
  default     = 1
}

variable "target_requests_per_instance" {
  description = "ALB requests per target that triggers scale-out."
  type        = number
  default     = 60
}

variable "root_volume_gb" {
  description = "Root volume size for the image and model cache."
  type        = number
  default     = 100
}

variable "tags" {
  description = "Tags applied to every resource."
  type        = map(string)
  default     = {}
}
