{{/*
SPDX-License-Identifier: BUSL-1.1
Copyright (c) 2025 Open Computer Use Contributors
*/}}

{{/* Chart name. */}}
{{- define "computer-use-server.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* Fully qualified app name. */}}
{{- define "computer-use-server.fullname" -}}
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

{{/* Chart label "name-version". */}}
{{- define "computer-use-server.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" -}}
{{- end -}}

{{/* Common labels. */}}
{{- define "computer-use-server.labels" -}}
helm.sh/chart: {{ include "computer-use-server.chart" . }}
{{ include "computer-use-server.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
app.kubernetes.io/part-of: open-computer-use
{{- end -}}

{{/* Selector labels (used by Service and Deployment). */}}
{{- define "computer-use-server.selectorLabels" -}}
app.kubernetes.io/name: {{ include "computer-use-server.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}

{{/* ServiceAccount name. */}}
{{- define "computer-use-server.serviceAccountName" -}}
{{- if .Values.serviceAccount.create -}}
{{- default (include "computer-use-server.fullname" .) .Values.serviceAccount.name -}}
{{- else -}}
{{- default "default" .Values.serviceAccount.name -}}
{{- end -}}
{{- end -}}

{{/* Orchestrator image reference. */}}
{{- define "computer-use-server.image" -}}
{{- $tag := default .Chart.AppVersion .Values.image.tag -}}
{{- printf "%s:%s" .Values.image.repository $tag -}}
{{- end -}}

{{/* Workspace image reference — passed to orchestrator as DOCKER_IMAGE env. */}}
{{- define "computer-use-server.workspaceImage" -}}
{{- $tag := default .Chart.AppVersion .Values.workspaceImage.tag -}}
{{- printf "%s:%s" .Values.workspaceImage.repository $tag -}}
{{- end -}}

{{/* Cleanup sidecar image reference. */}}
{{- define "computer-use-server.cleanupImage" -}}
{{- $tag := default .Chart.AppVersion .Values.cleanup.image.tag -}}
{{- printf "%s:%s" .Values.cleanup.image.repository $tag -}}
{{- end -}}

{{/* Secret name (chart-managed or external). */}}
{{- define "computer-use-server.secretName" -}}
{{- if .Values.secrets.existingSecret -}}
{{- .Values.secrets.existingSecret -}}
{{- else -}}
{{- include "computer-use-server.fullname" . -}}
{{- end -}}
{{- end -}}

{{/*
Whether the inner dind container must run privileged.
Resolution order:
  1. dind.privileged explicitly set (true/false) => use it verbatim.
     Kata needs `true`: dockerd requires CAP_NET_ADMIN/RAW for iptables NAT,
     and the caps stay confined to the microVM.
  2. otherwise (dind.privileged is null) => legacy auto-derivation:
       runtimeClassName empty => true  (stock runc, required for dockerd to start)
       runtimeClassName set   => false (sysbox-runc handles isolation)
A null default means Sysbox installs render identically to before this knob existed.
*/}}
{{- define "computer-use-server.dindPrivileged" -}}
{{- if not (kindIs "invalid" .Values.dind.privileged) -}}
{{- .Values.dind.privileged -}}
{{- else if eq (default "" .Values.orchestrator.runtimeClassName) "" -}}
true
{{- else -}}
false
{{- end -}}
{{- end -}}

{{/*
Whether /var/lib/docker is backed by a Block-mode PVC (Kata) rather than an
emptyDir (Sysbox / default). True when persistence.varLibDocker.persistentVolume
is enabled or an existingClaim is supplied.
*/}}
{{- define "computer-use-server.varLibDockerIsPVC" -}}
{{- $pv := .Values.persistence.varLibDocker.persistentVolume | default dict -}}
{{- if or $pv.enabled $pv.existingClaim -}}
true
{{- else -}}
false
{{- end -}}
{{- end -}}
