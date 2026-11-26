output "api_base" {
  description = "OpenAI-compatible base URL for the gateway (callers need an identity token)."
  value       = "${google_cloud_run_v2_service.vllm.uri}/v1"
}
