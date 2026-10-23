{{/* Shared ingress for backend routes, with independent annotations and TLS. */}}
{{- define "dictaphone.backendIngress" -}}
{{- $root := .root -}}
{{- $ingress := .ingress -}}
{{- $fullName := include "dictaphone.fullname" $root -}}
{{- $annotations := deepCopy $ingress.annotations -}}
{{- if and $ingress.className (not (semverCompare ">=1.18-0" $root.Capabilities.KubeVersion.GitVersion)) -}}
  {{- if not (hasKey $annotations "kubernetes.io/ingress.class") -}}
    {{- $_ := set $annotations "kubernetes.io/ingress.class" $ingress.className -}}
  {{- end -}}
{{- end -}}
{{- if semverCompare ">=1.19-0" $root.Capabilities.KubeVersion.GitVersion -}}
apiVersion: networking.k8s.io/v1
{{- else if semverCompare ">=1.14-0" $root.Capabilities.KubeVersion.GitVersion -}}
apiVersion: networking.k8s.io/v1beta1
{{- else -}}
apiVersion: extensions/v1beta1
{{- end }}
kind: Ingress
metadata:
  name: {{ $fullName }}-{{ .suffix }}
  namespace: {{ $root.Release.Namespace | quote }}
  labels:
    {{- include "dictaphone.labels" $root | nindent 4 }}
  {{- with $annotations }}
  annotations:
    {{- toYaml . | nindent 4 }}
  {{- end }}
spec:
  {{- if and $ingress.className (semverCompare ">=1.18-0" $root.Capabilities.KubeVersion.GitVersion) }}
  ingressClassName: {{ $ingress.className | quote }}
  {{- end }}
  {{- if $ingress.tls.enabled }}
  tls:
    {{- if $ingress.host }}
    - secretName: {{ $ingress.tls.secretName | default (printf "%s-tls" $fullName) | quote }}
      hosts:
        - {{ $ingress.host | quote }}
    {{- end }}
    {{- range $ingress.tls.additional }}
    - hosts:
        {{- range .hosts }}
        - {{ . | quote }}
        {{- end }}
      secretName: {{ .secretName | quote }}
    {{- end }}
  {{- end }}
  rules:
    {{- $hosts := $ingress.hosts -}}
    {{- if $ingress.host -}}
      {{- $hosts = prepend $hosts $ingress.host -}}
    {{- end -}}
    {{- if not $hosts -}}
      {{- fail (printf "ingress%s requires at least one host in host or hosts" (title .suffix)) -}}
    {{- end -}}
    {{- range $hosts }}
    - host: {{ . | quote }}
      http:
        paths:
          {{- range $ingress.paths }}
          - path: {{ . | quote }}
            {{- if semverCompare ">=1.18-0" $root.Capabilities.KubeVersion.GitVersion }}
            pathType: Prefix
            {{- end }}
            backend:
              {{- if semverCompare ">=1.19-0" $root.Capabilities.KubeVersion.GitVersion }}
              service:
                name: {{ include "dictaphone.backend.fullname" $root }}
                port:
                  number: {{ $root.Values.backend.service.port }}
              {{- else }}
              serviceName: {{ include "dictaphone.backend.fullname" $root }}
              servicePort: {{ $root.Values.backend.service.port }}
              {{- end }}
          {{- end }}
    {{- end }}
{{- end -}}
