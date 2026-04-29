{{/*
Chart name (truncated to 63 chars for k8s name limit).
*/}}
{{- define "arp-survey.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/*
Fully qualified app name.
*/}}
{{- define "arp-survey.fullname" -}}
{{- if .Values.fullnameOverride -}}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- $name := default .Chart.Name .Values.nameOverride -}}
{{- if contains $name .Release.Name -}}
{{- .Release.Name | trunc 63 | trimSuffix "-" -}}
{{- else -}}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" -}}
{{- end -}}
{{- end -}}
{{- end -}}

{{/*
Common labels.
*/}}
{{- define "arp-survey.labels" -}}
app.kubernetes.io/name: {{ include "arp-survey.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version | replace "+" "_" }}
app: {{ include "arp-survey.name" . }}
{{- end -}}

{{/*
Selector labels (must remain stable across upgrades).
*/}}
{{- define "arp-survey.selectorLabels" -}}
app: {{ include "arp-survey.name" . }}
{{- end -}}

{{/*
Shared environment variables for app and migration containers.
*/}}
{{- define "arp-survey.env" -}}
- name: PYTHONPATH
  value: {{ .Values.env.PYTHONPATH | quote }}
- name: DATABASE_URL
  valueFrom:
    secretKeyRef:
      name: {{ .Values.secret.name }}
      key: database-url
- name: SECRET_KEY
  valueFrom:
    secretKeyRef:
      name: {{ .Values.secret.name }}
      key: flask-secret-key
{{- end -}}
