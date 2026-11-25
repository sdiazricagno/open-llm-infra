output "api_base" {
  description = "OpenAI-compatible base URL to put in the gateway's VLLM_<MODEL>_API_BASE variable."
  value       = "http://${aws_lb.this.dns_name}/v1"
}

output "autoscaling_group" {
  description = "Auto Scaling group name; set desired capacity to 0 to stop paying for GPUs."
  value       = aws_autoscaling_group.vllm.name
}
