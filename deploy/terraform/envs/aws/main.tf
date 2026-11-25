terraform {
  required_version = ">= 1.6"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = ">= 6.0"
    }
  }
}

provider "aws" {
  region = var.region
}

variable "region" {
  description = "AWS region."
  type        = string
  default     = "us-east-1"
}

variable "vpc_id" {
  description = "VPC id."
  type        = string
}

variable "subnet_ids" {
  description = "Two or more subnets in different AZs."
  type        = list(string)
}

variable "allowed_cidrs" {
  description = "Who may call the endpoint."
  type        = list(string)
}

module "qwen_1_5b" {
  source        = "../../modules/aws-gpu-vllm"
  name          = "qwen15b"
  vpc_id        = var.vpc_id
  subnet_ids    = var.subnet_ids
  allowed_cidrs = var.allowed_cidrs
  instance_type = "g4dn.xlarge"
  use_spot      = true
  model         = "Qwen/Qwen2.5-1.5B-Instruct"
}

module "qwen_7b" {
  source           = "../../modules/aws-gpu-vllm"
  name             = "qwen7b"
  vpc_id           = var.vpc_id
  subnet_ids       = var.subnet_ids
  allowed_cidrs    = var.allowed_cidrs
  instance_type    = "g6.xlarge"
  use_spot         = true
  model            = "Qwen/Qwen2.5-7B-Instruct-AWQ"
  desired_capacity = 0
}

output "VLLM_QWEN2_5_1_5B_API_BASE" {
  description = "Set on the gateway."
  value       = module.qwen_1_5b.api_base
}

output "VLLM_QWEN2_5_7B_API_BASE" {
  description = "Set on the gateway."
  value       = module.qwen_7b.api_base
}
