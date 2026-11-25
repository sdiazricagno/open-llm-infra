{{- define "open-llm.k8sName" -}}
{{- regexReplaceAll "[^a-z0-9-]+" (lower .) "-" | trunc 40 | trimSuffix "-" -}}
{{- end -}}

{{- define "open-llm.envSlug" -}}
{{- regexReplaceAll "[^A-Z0-9]+" (upper .) "_" | trimAll "_" -}}
{{- end -}}

{{- define "open-llm.labels" -}}
app.kubernetes.io/part-of: open-llm-infra
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end -}}
