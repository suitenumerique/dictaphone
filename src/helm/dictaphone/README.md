# Dictaphone helm chart

## Workload security defaults

The backend (including migration, superuser and scheduled jobs), Celery and frontend
containers default to UID/GID 10000, non-root execution, a read-only root filesystem,
no privilege escalation, all Linux capabilities dropped and the runtime default
seccomp profile. Audio workers and the S3 gateway also use restrictive defaults.

The backend, Celery and frontend mount a writable `emptyDir` at `/tmp` for temporary
files (including Gunicorn worker files and the unprivileged Nginx PID and cache).
This volume is configured by each component’s `tmpVolume` setting and remains
mounted when `extraVolumes` or `extraVolumeMounts` are overridden. The name `tmp`
and mount path `/tmp` are reserved for this volume. Custom images and persistent volumes
must support the configured UID/GID and read-only root filesystem. Operator-supplied
sidecars and init containers must define their own container security contexts.

## API ingresses

The `ingress` resource serves the frontend. Enable `ingressPublic` to route
`/api/` and `/external-api/` to the backend, independently of frontend annotations.
Like `ingressAdmin`, both new ingresses are disabled by default.

**Upgrade:** API routes have moved out of `ingress`. Set
`ingressPublic.enabled: true` and copy the existing API host(s), ingress class,
TLS configuration, and any required API annotations from `ingress` to
`ingressPublic`. The default TLS secret remains `<release-fullname>-tls`.
The development environment already enables the public API ingress.

The public ingress disables gzip and clears the incoming and upstream
`Accept-Encoding` request header by default to mitigate BREACH (CVE-2013-3587).
Clearing the incoming header also prevents Brotli negotiation, including when
Brotli is enabled globally, without requiring its optional module to be loaded.
This uses the ingress-nginx `configuration-snippet` annotation: the controller
must allow snippet annotations and accept their risk level (see the
[ingress-nginx controller configuration](https://kubernetes.github.io/ingress-nginx/user-guide/nginx-configuration/configmap/#allow-snippet-annotations)).
If you replace this snippet, retain the compression directives. Other ingress
controllers require equivalent compression settings. Compression must also
remain disabled in any proxy/CDN serving API responses beyond this ingress.

Enable `ingressInternal` to apply a shared IP allowlist to media authentication,
AI webhook callbacks, and the audio worker routes. Use the **same host(s) and
ingress class as the public ingress** so these more specific paths take
precedence over `/api/`. A separate internal hostname alone does not restrict
these routes on the public host. When the internal ingress is disabled, these
routes remain accessible through the public API ingress.

```yaml
ingress:
  enabled: true
  className: nginx
  host: dictaphone.example.com

ingressPublic:
  enabled: true
  className: nginx
  host: dictaphone.example.com

ingressInternal:
  enabled: true
  className: nginx
  host: dictaphone.example.com
  annotations:
    nginx.ingress.kubernetes.io/whitelist-source-range: "192.0.2.0/24,198.51.100.10/32"
```

Replace the example CIDRs with the source addresses the ingress controller sees
for your media authentication subrequests, callback providers, and workers.
Without the allowlist annotation, enabling the internal ingress does not limit
source IPs. Its default paths are `/api/internal/`,
`/api/v1.0/files/media-auth`, and `/api/v1.0/ai-jobs/webhook`; update
`ingressInternal.paths` if you change the backend API version.

## Parameters

### General configuration

| Name                                                                              | Description                                            | Value                                                            |
| --------------------------------------------------------------------------------- | ------------------------------------------------------ | ---------------------------------------------------------------- |
| `images.backend.repository` | Backend image repository | `lasuite/dictaphone-backend` |
| `images.backend.tag` | Backend image tag | `latest` |
| `images.backend.pullPolicy` | Backend image pull policy | `IfNotPresent` |
| `images.frontend.repository` | Frontend image repository | `lasuite/dictaphone-frontend` |
| `images.frontend.tag` | Frontend image tag | `latest` |
| `images.frontend.pullPolicy` | Frontend image pull policy | `IfNotPresent` |
| `images.audioExtractor.repository` | Audio extractor image repository | `lasuite/dictaphone-audio-extractor` |
| `images.audioExtractor.tag` | Audio extractor image tag | `latest` |
| `images.audioExtractor.pullPolicy` | Audio extractor image pull policy | `IfNotPresent` |
| `images.credentials.username` | Username for container registry authentication | |
| `images.credentials.password` | Password for container registry authentication | |
| `images.credentials.registry` | Registry url for which the credentials are specified | |
| `images.credentials.name` | Name of the generated secret for imagePullSecrets | |
| `nameOverride`                                                                    | Override the chart name                                | `""`                                                             |
| `fullnameOverride`                                                                | Override the full application name                     | `""`                                                             |
| `ingress.enabled`                                                                 | whether to enable the Ingress or not                   | `false`                                                          |
| `ingress.className`                                                               | IngressClass to use for the Ingress                    | `nil`                                                            |
| `ingress.host`                                                                    | Host for the Ingress                                   | `dictaphone.example.com`                                         |
| `ingress.path`                                                                    | Path to use for the Ingress                            | `/`                                                              |
| `ingress.hosts`                                                                   | Additional host to configure for the Ingress           | `[]`                                                             |
| `ingress.tls.enabled`                                                             | Weather to enable TLS for the Ingress                  | `true`                                                           |
| `ingress.tls.secretName`                                                          | Secret name for TLS config                             | `nil`                                                            |
| `ingress.tls.additional[].secretName`                                             | Secret name for additional TLS config                  |                                                                  |
| `ingress.tls.additional[].hosts[]`                                                | Hosts for additional TLS config                        |                                                                  |
| `ingress.customBackends`                                                          | Add custom backends to ingress                         | `[]`                                                             |
| `ingressPublic.enabled` | Enable the public API ingress | `false` |
| `ingressPublic.className` | IngressClass to use | `nil` |
| `ingressPublic.host` | Primary hostname | `dictaphone.example.com` |
| `ingressPublic.hosts` | Additional hostnames | `[]` |
| `ingressPublic.paths` | Backend route prefixes | `[/api/, /external-api/]` |
| `ingressPublic.annotations` | Ingress annotations | `NGINX snippet disabling compression` |
| `ingressPublic.tls.enabled` | Enable TLS | `true` |
| `ingressPublic.tls.secretName` | TLS secret (defaults to the main ingress secret) | `nil` |
| `ingressPublic.tls.additional[].secretName` | Secret name for additional TLS config | `` |
| `ingressPublic.tls.additional[].hosts[]` | Hosts for additional TLS config | `` |
| `ingressInternal.enabled` | Enable the internal API ingress | `false` |
| `ingressInternal.className` | IngressClass to use | `nil` |
| `ingressInternal.host` | Primary hostname | `dictaphone.example.com` |
| `ingressInternal.hosts` | Additional hostnames | `[]` |
| `ingressInternal.paths` | Backend route prefixes | `[/api/internal/, /api/v1.0/files/media-auth, /api/v1.0/ai-jobs/webhook]` |
| `ingressInternal.annotations` | Ingress annotations | `{}` |
| `ingressInternal.tls.enabled` | Enable TLS | `true` |
| `ingressInternal.tls.secretName` | TLS secret (defaults to the main ingress secret) | `nil` |
| `ingressInternal.tls.additional[].secretName` | Secret name for additional TLS config | `` |
| `ingressInternal.tls.additional[].hosts[]` | Hosts for additional TLS config | `` |
| `ingressAdmin.enabled`                                                            | whether to enable the Ingress or not                   | `false`                                                          |
| `ingressAdmin.className`                                                          | IngressClass to use for the Ingress                    | `nil`                                                            |
| `ingressAdmin.host`                                                               | Host for the Ingress                                   | `dictaphone.example.com`                                         |
| `ingressAdmin.path`                                                               | Path to use for the Ingress                            | `/admin`                                                         |
| `ingressAdmin.hosts`                                                              | Additional host to configure for the Ingress           | `[]`                                                             |
| `ingressAdmin.tls.enabled`                                                        | Weather to enable TLS for the Ingress                  | `true`                                                           |
| `ingressAdmin.tls.secretName`                                                     | Secret name for TLS config                             | `nil`                                                            |
| `ingressAdmin.tls.additional[].secretName`                                        | Secret name for additional TLS config                  |                                                                  |
| `ingressAdmin.tls.additional[].hosts[]`                                           | Hosts for additional TLS config                        |                                                                  |
| `ingressMediaFiles`                                                              | List of media files ingresses to create                 |                                                                  |
| `ingressMediaFiles[].name`                                                       | Unique name for the ingress and its provider entry      | `default`                                                        |
| `ingressMediaFiles[].serviceName`                                                | Service entry to route to (defaults to name)            | `default`                                                        |
| `ingressMediaFiles[].enabled`                                                    | Whether to enable this Ingress                           | `false`                                                          |
| `ingressMediaFiles[].className`                                                  | IngressClass to use for this Ingress                    | `nil`                                                            |
| `ingressMediaFiles[].host`                                                       | Host for this Ingress                                   | `dictaphone.example.com`                                         |
| `ingressMediaFiles[].path`                                                       | Path to use for this Ingress                            | `/media/(.*)`                                                    |
| `ingressMediaFiles[].hosts`                                                      | Additional hosts to configure for the Ingress           | `[]`                                                             |
| `ingressMediaFiles[].tls.enabled`                                                | Whether to enable TLS for the Ingress                  | `true`                                                           |
| `ingressMediaFiles[].tls.secretName`                                             | Secret name for TLS config                             | `nil`                                                            |
| `ingressMediaFiles[].tls.additional[].secretName`                                | Secret name for additional TLS config                  |                                                                  |
| `ingressMediaFiles[].tls.additional[].hosts[]`                                  | Hosts for additional TLS config                        |                                                                  |
| `ingressMediaFiles[].annotations.nginx.ingress.kubernetes.io/use-regex`          | Enable use of regex for ingress paths                  | `true`                                                           |
| `ingressMediaFiles[].annotations.nginx.ingress.kubernetes.io/auth-url`           | Authentication URL for the ingress                     | `https://dictaphone.example.com/api/v1.0/files/media-auth/`      |
| `ingressMediaFiles[].annotations.nginx.ingress.kubernetes.io/auth-response-headers` | Headers to pass from auth response                  | `Authorization, X-Amz-Date, X-Amz-Content-SHA256`                |
| `ingressMediaFiles[].annotations.nginx.ingress.kubernetes.io/upstream-vhost`     | Upstream host for proxying                             | `rustfs.dictaphone.svc.cluster.local:9000`                        |
| `ingressMediaFiles[].annotations.nginx.ingress.kubernetes.io/configuration-snippet` | Custom nginx configuration snippet                  | `add_header Content-Security-Policy "default-src 'none'" always; |

add_header Content-Disposition "attachment";
`|
| `serviceMediaFiles`                                                              | List of ExternalName services for media files providers |                                                                  |
| `serviceMediaFiles[].name`                                                       | Unique name for this provider service                  | `default`                                                        |
| `serviceMediaFiles[].host`                                                       | External hostname for this provider                    | `rustfs.dictaphone.svc.cluster.local`                             |
| `serviceMediaFiles[].port`                                                       | Port for this provider                                 | `9000`                                                           |
| `serviceMediaFiles[].annotations`                                                | Annotations to add to this Service                     | `{}`                                                             |

### backend

| Name                                                  | Description                                                       | Value                                                                                                                                                                                                                                                                               |
| ----------------------------------------------------- | ----------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `backend.dpAnnotations`                               | Annotations to add to the backend Deployment                      | `{}`                                                                                                                                                                                                                                                                                |
| `backend.command`                                     | Override the backend container command                            | `[]`                                                                                                                                                                                                                                                                                |
| `backend.args`                                        | Override the backend container args                               | `[]`                                                                                                                                                                                                                                                                                |
| `backend.replicas`                                    | Amount of backend replicas                                        | `3`                                                                                                                                                                                                                                                                                 |
| `backend.shareProcessNamespace`                       | Enable share process namespace between containers                 | `false`                                                                                                                                                                                                                                                                             |
| `backend.sidecars`                                    | Add sidecars containers to backend deployment                     | `[]`                                                                                                                                                                                                                                                                                |
| `backend.migrateJobAnnotations`                       | Annotations for the migrate job                                   | `{}`                                                                                                                                                                                                                                                                                |
| `backend.jobs.ttlSecondsAfterFinished`                | Period to wait before remove jobs                                 | `30`                                                                                                                                                                                                                                                                                |
| `backend.jobs.backoffLimit`                           | Numbers of jobs retries                                           | `2`                                                                                                                                                                                                                                                                                 |
| `backend.securityContext` | Configure backend container security context | `{runAsNonRoot: true, runAsUser: 10000, runAsGroup: 10000, readOnlyRootFilesystem: true, allowPrivilegeEscalation: false, capabilities: {drop: [ALL]}, seccompProfile: {type: RuntimeDefault}}` |
| `backend.envVars`                                     | Configure backend container environment variables                 | `undefined`                                                                                                                                                                                                                                                                         |
| `backend.envVars.BY_VALUE`                            | Example environment variable by setting value directly            |                                                                                                                                                                                                                                                                                     |
| `backend.envVars.FROM_CONFIGMAP.configMapKeyRef.name` | Name of a ConfigMap when configuring env vars from a ConfigMap    |                                                                                                                                                                                                                                                                                     |
| `backend.envVars.FROM_CONFIGMAP.configMapKeyRef.key`  | Key within a ConfigMap when configuring env vars from a ConfigMap |                                                                                                                                                                                                                                                                                     |
| `backend.envVars.FROM_SECRET.secretKeyRef.name`       | Name of a Secret when configuring env vars from a Secret          |                                                                                                                                                                                                                                                                                     |
| `backend.envVars.FROM_SECRET.secretKeyRef.key`        | Key within a Secret when configuring env vars from a Secret       |                                                                                                                                                                                                                                                                                     |
| `backend.podAnnotations`                              | Annotations to add to the backend Pod                             | `{}`                                                                                                                                                                                                                                                                                |
| `backend.service.type`                                | backend Service type                                              | `ClusterIP`                                                                                                                                                                                                                                                                         |
| `backend.service.port`                                | backend Service listening port                                    | `80`                                                                                                                                                                                                                                                                                |
| `backend.service.targetPort`                          | backend container listening port                                  | `8000`                                                                                                                                                                                                                                                                              |
| `backend.service.annotations`                         | Annotations to add to the backend Service                         | `{}`                                                                                                                                                                                                                                                                                |
| `backend.migrate.command`                             | backend migrate command                                           | `["/bin/sh","-c","while ! python manage.py check --database default > /dev/null 2>&1\ndo\n  echo \"Database not ready\"\n  sleep 2\ndone\necho \"Database is ready\"\n\npython manage.py migrate --no-input\n"]`                                                                    |
| `backend.migrate.restartPolicy`                       | backend migrate job restart policy                                | `Never`                                                                                                                                                                                                                                                                             |
| `backend.createsuperuser.command`                     | backend migrate command                                           | `["/bin/sh","-c","while ! python manage.py check --database default > /dev/null 2>&1\ndo\n  echo \"Database not ready\"\n  sleep 2\ndone\necho \"Database is ready\"\n\npython manage.py createsuperuser --email $DJANGO_SUPERUSER_EMAIL --password $DJANGO_SUPERUSER_PASSWORD\n"]` |
| `backend.createsuperuser.restartPolicy`               | backend migrate job restart policy                                | `Never`                                                                                                                                                                                                                                                                             |

### Jobs

| Name                                           | Description                                                                        | Value                                                     |
| ---------------------------------------------- | ---------------------------------------------------------------------------------- | --------------------------------------------------------- |
| `backend.cronjobs[0].name` | Name of the CronJob | `delete-original-files-data` |
| `backend.cronjobs[0].schedule` | Schedule in cron format | `1 0 * * *` |
| `backend.cronjobs[0].command` | The bash command to execute in the CronJob | `["/bin/sh","-c","python manage.py delete_original_files_data"]` |
| `backend.cronjobs[1].name` | Name of the CronJob | `auto-hard-delete-files` |
| `backend.cronjobs[1].schedule` | Schedule in cron format | `15 0 * * *` |
| `backend.cronjobs[1].command` | The bash command to execute in the CronJob | `["/bin/sh","-c","python manage.py auto_hard_delete_files"]` |
| `backend.cronjobs[2].name` | Name of the CronJob | `clean-pending-files` |
| `backend.cronjobs[2].schedule` | Schedule in cron format | `30 0 * * *` |
| `backend.cronjobs[2].command` | The bash command to execute in the CronJob | `["/bin/sh","-c","python manage.py clean_pending_files"]` |
| `backend.cronjobs[3].name` | Name of the CronJob | `purge-deleted-files` |
| `backend.cronjobs[3].schedule` | Schedule in cron format | `45 0 * * *` |
| `backend.cronjobs[3].command` | The bash command to execute in the CronJob | `["/bin/sh","-c","python manage.py purge_deleted_files"]` |
| `backend.cronjobs[4].name` | Name of the CronJob | `purge-transcription-usage` |
| `backend.cronjobs[4].schedule` | Schedule in cron format | `0 1 * * *` |
| `backend.cronjobs[4].command` | The bash command to execute in the CronJob | `["/bin/sh","-c","python manage.py purge_transcription_usage"]` |
| `backend.probes.liveness.path`                 | Configure path for backend HTTP liveness probe                                     | `/__heartbeat__`                                          |
| `backend.probes.liveness.targetPort`           | Configure port for backend HTTP liveness probe                                     | `nil`                                                     |
| `backend.probes.liveness.initialDelaySeconds`  | Configure initial delay for backend liveness probe                                 | `5`                                                       |
| `backend.probes.liveness.timeoutSeconds`       | Configure timeout for backend liveness probe                                       | `nil`                                                     |
| `backend.probes.liveness.period`               | Configure period for backend liveness probe                                        | `nil`                                                     |
| `backend.probes.liveness.periodSeconds`        | Configure period for backend liveness probe                                        | `30`                                                      |
| `backend.probes.startup.path`                  | Configure path for backend HTTP startup probe                                      | `nil`                                                     |
| `backend.probes.startup.targetPort`            | Configure port for backend HTTP startup probe                                      | `nil`                                                     |
| `backend.probes.startup.initialDelaySeconds`   | Configure initial delay for backend startup probe                                  | `nil`                                                     |
| `backend.probes.startup.timeoutSeconds`        | Configure timeout for backend startup probe                                        | `nil`                                                     |
| `backend.probes.startup.period`                | Configure period for backend startup probe                                         | `nil`                                                     |
| `backend.probes.readiness.path`                | Configure path for backend HTTP readiness probe                                    | `/__lbheartbeat__`                                        |
| `backend.probes.readiness.targetPort`          | Configure port for backend HTTP readiness probe                                    | `nil`                                                     |
| `backend.probes.readiness.initialDelaySeconds` | Configure initial delay for backend readiness probe                                | `5`                                                       |
| `backend.probes.readiness.timeoutSeconds`      | Configure timeout for backend readiness probe                                      | `nil`                                                     |
| `backend.probes.readiness.period`              | Configure period for backend readiness probe                                       | `nil`                                                     |
| `backend.probes.readiness.periodSeconds`       | Configure period for backend readiness probe                                       | `30`                                                      |
| `backend.resources`                            | Resource requirements for the backend container                                    | `{}`                                                      |
| `backend.nodeSelector`                         | Node selector for the backend Pod                                                  | `{}`                                                      |
| `backend.tolerations`                          | Tolerations for the backend Pod                                                    | `[]`                                                      |
| `backend.affinity`                             | Affinity for the backend Pod                                                       | `{}`                                                      |
| `backend.persistence`                          | Additional volumes to create and mount on the backend. Used for debugging purposes | `{}`                                                      |
| `backend.persistence.volume-name.size`         | Size of the additional volume                                                      |                                                           |
| `backend.persistence.volume-name.type`         | Type of the additional volume, persistentVolumeClaim or emptyDir                   |                                                           |
| `backend.persistence.volume-name.mountPath`    | Path where the volume should be mounted to                                         |                                                           |
| `backend.tmpVolume` | Volume backing writable `/tmp`; defaults to `emptyDir` when unset, independent of additional volumes | `{}` |
| `backend.extraVolumeMounts` | Additional volumes to mount on the backend. | `[]` |
| `backend.extraVolumes` | Additional volumes to mount on the backend. | `[]` |
| `backend.pdb.enabled`                          | Enable pdb on backend                                                              | `true`                                                    |

### celeryBackend

| Name                                                        | Description                                                                              | Value                                                                                          |
| ----------------------------------------------------------- | ---------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------- |
| `celeryBackend.dpAnnotations`                               | Annotations to add to the celeryBackend Deployment                                       | `{}`                                                                                           |
| `celeryBackend.command`                                     | Override the celeryBackend container command                                             | `["celery","-A","dictaphone.celery_app","worker","--loglevel=info","-Q","dictaphone-backend"]` |
| `celeryBackend.args`                                        | Override the celeryBackend container args                                                | `[]`                                                                                           |
| `celeryBackend.replicas`                                    | Amount of celeryBackend replicas                                                         | `1`                                                                                            |
| `celeryBackend.shareProcessNamespace`                       | Enable share process namespace between containers                                        | `false`                                                                                        |
| `celeryBackend.sidecars`                                    | Add sidecars containers to celeryBackend deployment                                      | `[]`                                                                                           |
| `celeryBackend.migrateJobAnnotations`                       | Annotations for the migrate job                                                          | `{}`                                                                                           |
| `celeryBackend.securityContext` | Configure celeryBackend container security context | `{runAsNonRoot: true, runAsUser: 10000, runAsGroup: 10000, readOnlyRootFilesystem: true, allowPrivilegeEscalation: false, capabilities: {drop: [ALL]}, seccompProfile: {type: RuntimeDefault}}` |
| `celeryBackend.envVars`                                     | Configure celeryBackend container environment variables                                  | `undefined`                                                                                    |
| `celeryBackend.envVars.BY_VALUE`                            | Example environment variable by setting value directly                                   |                                                                                                |
| `celeryBackend.envVars.FROM_CONFIGMAP.configMapKeyRef.name` | Name of a ConfigMap when configuring env vars from a ConfigMap                           |                                                                                                |
| `celeryBackend.envVars.FROM_CONFIGMAP.configMapKeyRef.key`  | Key within a ConfigMap when configuring env vars from a ConfigMap                        |                                                                                                |
| `celeryBackend.envVars.FROM_SECRET.secretKeyRef.name`       | Name of a Secret when configuring env vars from a Secret                                 |                                                                                                |
| `celeryBackend.envVars.FROM_SECRET.secretKeyRef.key`        | Key within a Secret when configuring env vars from a Secret                              |                                                                                                |
| `celeryBackend.podAnnotations`                              | Annotations to add to the celeryBackend Pod                                              | `{}`                                                                                           |
| `celeryBackend.service.type`                                | celeryBackend Service type                                                               | `ClusterIP`                                                                                    |
| `celeryBackend.service.port`                                | celeryBackend Service listening port                                                     | `80`                                                                                           |
| `celeryBackend.service.targetPort`                          | celeryBackend container listening port                                                   | `8000`                                                                                         |
| `celeryBackend.service.annotations`                         | Annotations to add to the celeryBackend Service                                          | `{}`                                                                                           |
| `celeryBackend.probes`                                      | Configure celeryBackend probes                                                           | `{}`                                                                                           |
| `celeryBackend.probes.liveness.path`                        | Configure path for celeryBackend HTTP liveness probe                                     | `nil`                                                                                          |
| `celeryBackend.probes.liveness.targetPort`                  | Configure port for celeryBackend HTTP liveness probe                                     | `nil`                                                                                          |
| `celeryBackend.probes.liveness.initialDelaySeconds`         | Configure initial delay for celeryBackend liveness probe                                 | `nil`                                                                                          |
| `celeryBackend.probes.liveness.initialDelaySeconds`         | Configure timeout for celeryBackend liveness probe                                       | `nil`                                                                                          |
| `celeryBackend.probes.startup.path`                         | Configure path for celeryBackend HTTP startup probe                                      | `nil`                                                                                          |
| `celeryBackend.probes.startup.targetPort`                   | Configure port for celeryBackend HTTP startup probe                                      | `nil`                                                                                          |
| `celeryBackend.probes.startup.initialDelaySeconds`          | Configure initial delay for celeryBackend startup probe                                  | `nil`                                                                                          |
| `celeryBackend.probes.startup.initialDelaySeconds`          | Configure timeout for celeryBackend startup probe                                        | `nil`                                                                                          |
| `celeryBackend.probes.readiness.path`                       | Configure path for celeryBackend HTTP readiness probe                                    | `nil`                                                                                          |
| `celeryBackend.probes.readiness.targetPort`                 | Configure port for celeryBackend HTTP readiness probe                                    | `nil`                                                                                          |
| `celeryBackend.probes.readiness.initialDelaySeconds`        | Configure initial delay for celeryBackend readiness probe                                | `nil`                                                                                          |
| `celeryBackend.probes.readiness.initialDelaySeconds`        | Configure timeout for celeryBackend readiness probe                                      | `nil`                                                                                          |
| `celeryBackend.resources`                                   | Resource requirements for the celeryBackend container                                    | `{}`                                                                                           |
| `celeryBackend.nodeSelector`                                | Node selector for the celeryBackend Pod                                                  | `{}`                                                                                           |
| `celeryBackend.tolerations`                                 | Tolerations for the celeryBackend Pod                                                    | `[]`                                                                                           |
| `celeryBackend.affinity`                                    | Affinity for the celeryBackend Pod                                                       | `{}`                                                                                           |
| `celeryBackend.persistence`                                 | Additional volumes to create and mount on the celeryBackend. Used for debugging purposes | `{}`                                                                                           |
| `celeryBackend.persistence.volume-name.size`                | Size of the additional volume                                                            |                                                                                                |
| `celeryBackend.persistence.volume-name.type`                | Type of the additional volume, persistentVolumeClaim or emptyDir                         |                                                                                                |
| `celeryBackend.persistence.volume-name.mountPath`           | Path where the volume should be mounted to                                               |                                                                                                |
| `celeryBackend.tmpVolume` | Volume backing writable `/tmp`; defaults to `emptyDir` when unset, independent of additional volumes | `{}` |
| `celeryBackend.extraVolumeMounts` | Additional volumes to mount on the celeryBackend. | `[]` |
| `celeryBackend.extraVolumes` | Additional volumes to mount on the celeryBackend. | `[]` |
| `celeryBackend.pdb.enabled`                                 | Enable pdb on celeryBackend                                                              | `false`                                                                                        |

### audioExtractor

The worker's `AUDIO_EXTRACTOR_JOB_TIMEOUT_SECONDS` is copied from
`backend.envVars.AUDIO_JOB_TIMEOUT_SECONDS`, defaulting to `300`.
Settings under `audioExtractor` apply to both transcoding and validation workers.
As with the gateway, `podSecurityContext` configures the Pod and `securityContext`
configures the worker container. Probes accept native Kubernetes definitions;
set an individual probe to `null` to disable it.

| Name                        | Description                                                    | Value                                                                                       |
| --------------------------- | -------------------------------------------------------------- | ------------------------------------------------------------------------------------------- |
| `audioExtractor.dpAnnotations` | Annotations to add to the audio worker Deployment       | `{}`                                                                                        |
| `audioExtractor.command`          | Command used by the audio extraction worker, enforcing its job deadline | `["sh","/app/run-worker.sh"]` |
| `audioExtractor.args`          | Additional audio worker arguments                        | `[]`                                                                                        |
| `audioExtractor.transcodingReplicas` | Amount of transcoding worker replicas             | `1` |
| `audioExtractor.validationReplicas`  | Amount of validation worker replicas              | `1` |
| `audioExtractor.shareProcessNamespace` | Enable share process namespace between containers | `false` |
| `audioExtractor.sidecars`      | Add sidecars containers to audio worker deployment       | `[]`                                                                                        |
| `audioExtractor.initContainers` | Init containers in audio worker Pods | `[]` |
| `audioExtractor.automountServiceAccountToken` | Mount a service-account token | `false` |
| `audioExtractor.serviceAccountName` | Existing service account for audio worker Pods | `""` |
| `audioExtractor.podSecurityContext` | Pod security context | Non-root UID/GID/fsGroup 10000, RuntimeDefault seccomp |
| `audioExtractor.strategy` | Deployment rollout strategy | RollingUpdate, maxUnavailable 0, maxSurge 1 |
| `audioExtractor.probes` | Startup, liveness, and readiness probes | `/startupz`, `/livez`, `/readyz` on port `health` |
| `audioExtractor.terminationGracePeriodSeconds` | Time for cancellation and cleanup | `45` |
| `audioExtractor.securityContext` | Configure audio worker container security context     | `{allowPrivilegeEscalation: false, readOnlyRootFilesystem: true, runAsNonRoot: true, runAsUser: 10000, runAsGroup: 10000, capabilities: {drop: [ALL]}}`                                                                                       |
| `audioExtractor.envVars`       | Environment variables shared by both audio workers      | `AUDIO_EXTRACTOR_API_URL not set by the chart; include /api/internal/${API_VERSION} in its value` |
| `audioExtractor.transcodingEnvVars` | Environment variables for the transcoding worker, including its dedicated `AUDIO_EXTRACTOR_TOKEN` | `{}` |
| `audioExtractor.validationEnvVars` | Environment variables for the validation worker, including its dedicated `AUDIO_EXTRACTOR_TOKEN` | `{}` |
| `audioExtractor.podAnnotations` | Annotations to add to the audio worker Pod             | `{}`                                                                                        |
| `audioExtractor.resources`      | Resource requirements for the audio worker container    | `{}` |
| `audioExtractor.nodeSelector`   | Node selector for the audio worker Pod                  | `{}`                                                                                        |
| `audioExtractor.tolerations`    | Tolerations for the audio worker Pod                    | `[]`                                                                                        |
| `audioExtractor.affinity`       | Affinity for the audio worker Pod                       | `{}`                                                                                        |
| `audioExtractor.persistence`   | Additional volumes to create and mount on the audio worker. Used for debugging purposes | `{}` |
| `audioExtractor.persistence.volume-name.size` | Size of the additional volume | |
| `audioExtractor.persistence.volume-name.type` | Type of the additional volume, persistentVolumeClaim or emptyDir | |
| `audioExtractor.persistence.volume-name.mountPath` | Path where the volume should be mounted to | |
| `audioExtractor.workVolume` | Kubernetes volume source mounted at `/work` | `{emptyDir: {sizeLimit: 4Gi}}` |
| `audioExtractor.extraVolumeMounts` | Additional native Kubernetes volume mounts | `[]` |
| `audioExtractor.extraVolumes` | Additional Kubernetes volumes; also accepts `existingClaim` for PVCs | `[]` |
| `audioExtractor.pdb.enabled`    | Enable pdb on the audio worker | `false` |
| `audioExtractor.pdb.maxUnavailable` | Maximum unavailable Pods per worker Deployment | `1` |

### frontend

| Name                                                   | Description                                                                         | Value                         |
| ------------------------------------------------------ | ----------------------------------------------------------------------------------- | ----------------------------- |
| `frontend.dpAnnotations`                               | Annotations to add to the frontend Deployment                                       | `{}`                          |
| `frontend.command`                                     | Override the frontend container command                                             | `[]`                          |
| `frontend.args`                                        | Override the frontend container args                                                | `[]`                          |
| `frontend.replicas`                                    | Amount of frontend replicas                                                         | `3`                           |
| `frontend.shareProcessNamespace`                       | Enable share process namefrontend between containers                                | `false`                       |
| `frontend.sidecars`                                    | Add sidecars containers to frontend deployment                                      | `[]`                          |
| `frontend.securityContext` | Configure frontend container security context | `{runAsNonRoot: true, runAsUser: 10000, runAsGroup: 10000, readOnlyRootFilesystem: true, allowPrivilegeEscalation: false, capabilities: {drop: [ALL]}, seccompProfile: {type: RuntimeDefault}}` |
| `frontend.envVars`                                     | Configure frontend container environment variables                                  | `undefined`                   |
| `frontend.envVars.BY_VALUE`                            | Example environment variable by setting value directly                              |                               |
| `frontend.envVars.FROM_CONFIGMAP.configMapKeyRef.name` | Name of a ConfigMap when configuring env vars from a ConfigMap                      |                               |
| `frontend.envVars.FROM_CONFIGMAP.configMapKeyRef.key`  | Key within a ConfigMap when configuring env vars from a ConfigMap                   |                               |
| `frontend.envVars.FROM_SECRET.secretKeyRef.name`       | Name of a Secret when configuring env vars from a Secret                            |                               |
| `frontend.envVars.FROM_SECRET.secretKeyRef.key`        | Key within a Secret when configuring env vars from a Secret                         |                               |
| `frontend.podAnnotations`                              | Annotations to add to the frontend Pod                                              | `{}`                          |
| `frontend.service.type`                                | frontend Service type                                                               | `ClusterIP`                   |
| `frontend.service.port`                                | frontend Service listening port                                                     | `80`                          |
| `frontend.service.targetPort`                          | frontend container listening port                                                   | `8080`                        |
| `frontend.service.annotations`                         | Annotations to add to the frontend Service                                          | `{}`                          |
| `frontend.probes`                                      | Configure probe for frontend                                                        | `{}`                          |
| `frontend.probes.liveness.path`                        | Configure path for frontend HTTP liveness probe                                     |                               |
| `frontend.probes.liveness.targetPort`                  | Configure port for frontend HTTP liveness probe                                     |                               |
| `frontend.probes.liveness.initialDelaySeconds`         | Configure initial delay for frontend liveness probe                                 |                               |
| `frontend.probes.liveness.initialDelaySeconds`         | Configure timeout for frontend liveness probe                                       |                               |
| `frontend.probes.startup.path`                         | Configure path for frontend HTTP startup probe                                      |                               |
| `frontend.probes.startup.targetPort`                   | Configure port for frontend HTTP startup probe                                      |                               |
| `frontend.probes.startup.initialDelaySeconds`          | Configure initial delay for frontend startup probe                                  |                               |
| `frontend.probes.startup.initialDelaySeconds`          | Configure timeout for frontend startup probe                                        |                               |
| `frontend.probes.readiness.path`                       | Configure path for frontend HTTP readiness probe                                    |                               |
| `frontend.probes.readiness.targetPort`                 | Configure port for frontend HTTP readiness probe                                    |                               |
| `frontend.probes.readiness.initialDelaySeconds`        | Configure initial delay for frontend readiness probe                                |                               |
| `frontend.probes.readiness.initialDelaySeconds`        | Configure timeout for frontend readiness probe                                      |                               |
| `frontend.resources`                                   | Resource requirements for the frontend container                                    | `{}`                          |
| `frontend.nodeSelector`                                | Node selector for the frontend Pod                                                  | `{}`                          |
| `frontend.tolerations`                                 | Tolerations for the frontend Pod                                                    | `[]`                          |
| `frontend.affinity`                                    | Affinity for the frontend Pod                                                       | `{}`                          |
| `frontend.persistence`                                 | Additional volumes to create and mount on the frontend. Used for debugging purposes | `{}`                          |
| `frontend.persistence.volume-name.size`                | Size of the additional volume                                                       |                               |
| `frontend.persistence.volume-name.type`                | Type of the additional volume, persistentVolumeClaim or emptyDir                    |                               |
| `frontend.persistence.volume-name.mountPath`           | Path where the volume should be mounted to                                          |                               |
| `frontend.tmpVolume` | Volume backing writable `/tmp`; defaults to `emptyDir` when unset, independent of additional volumes | `{}` |
| `frontend.extraVolumeMounts` | Additional volumes to mount on the frontend. | `[]` |
| `frontend.extraVolumes` | Additional volumes to mount on the frontend. | `[]` |
| `frontend.pdb.enabled`                                 | Enable pdb on frontend                                                              | `true`                        |

### posthog

| Name                                   | Description                                                 | Value                     |
| -------------------------------------- | ----------------------------------------------------------- | ------------------------- |
| `posthog.ingress.enabled`              | Enable or disable the ingress resource creation             | `false`                   |
| `posthog.ingress.className`            | Kubernetes ingress class name to use (e.g., nginx, traefik) | `nil`                     |
| `posthog.ingress.host`                 | Primary hostname for the ingress resource                   | `dictaphone.example.com`  |
| `posthog.ingress.path`                 | URL path prefix for the ingress routes (e.g., /)            | `/`                       |
| `posthog.ingress.hosts`                | Additional hostnames array to be included in the ingress    | `[]`                      |
| `posthog.ingress.tls.enabled`          | Enable or disable TLS/HTTPS for the ingress                 | `true`                    |
| `posthog.ingress.tls.secretName`       | Secret name for TLS config                                  | `nil`                     |
| `posthog.ingress.tls.additional`       | Additional TLS configurations for extra hosts/certificates  | `[]`                      |
| `posthog.ingress.customBackends`       | Custom backend service configurations for the ingress       | `[]`                      |
| `posthog.ingress.annotations`          | Additional Kubernetes annotations to apply to the ingress   | `{}`                      |
| `posthog.ingressAssets.enabled`        | Enable or disable the ingress resource creation             | `false`                   |
| `posthog.ingressAssets.className`      | Kubernetes ingress class name to use (e.g., nginx, traefik) | `nil`                     |
| `posthog.ingressAssets.host`           | Primary hostname for the ingress resource                   | `dictaphone.example.com`  |
| `posthog.ingressAssets.path`           | URL path prefix for the ingress routes (e.g., /)            | `/static`                 |
| `posthog.ingressAssets.hosts`          | Additional hostnames array to be included in the ingress    | `[]`                      |
| `posthog.ingressAssets.tls.enabled`    | Enable or disable TLS/HTTPS for the ingress                 | `true`                    |
| `posthog.ingressAssets.tls.secretName` | Secret name for TLS config                                  | `nil`                     |
| `posthog.ingressAssets.tls.additional` | Additional TLS configurations for extra hosts/certificates  | `[]`                      |
| `posthog.ingressAssets.customBackends` | Custom backend service configurations for the ingress       | `[]`                      |
| `posthog.ingressAssets.annotations`    | Additional Kubernetes annotations to apply to the ingress   | `{}`                      |
| `posthog.service.type`                 | Service type (e.g. ExternalName, ClusterIP, LoadBalancer)   | `ExternalName`            |
| `posthog.service.externalName`         | External service hostname when type is ExternalName         | `eu.i.posthog.com`        |
| `posthog.service.port`                 | Port number for the service                                 | `443`                     |
| `posthog.service.annotations`          | Additional annotations to apply to the service              | `{}`                      |
| `posthog.assetsService.type`           | Service type (e.g. ExternalName, ClusterIP, LoadBalancer)   | `ExternalName`            |
| `posthog.assetsService.externalName`   | External service hostname when type is ExternalName         | `eu-assets.i.posthog.com` |
| `posthog.assetsService.port`           | Port number for the service                                 | `443`                     |
| `posthog.assetsService.annotations`    | Additional annotations to apply to the service              | `{}`                      |

### Extra Manifests

| Name                          | Description                                                 | Value |
| ----------------------------- | ----------------------------------------------------------- | ----- |
| `extraManifests`              | Extra Kubernetes manifests to deploy                        | `[]`  |
| `extraManifests[].apiVersion` | API version of the resource                                 |       |
| `extraManifests[].kind`       | Kind of the resource (Deployment, Service, ConfigMap, etc.) |       |
| `extraManifests[].metadata`   | Resource metadata                                           |       |
| `extraManifests[].spec`       | Resource specification                                      |       |

### s3Gateway

The S3 proxy is enabled by default and runs the existing audio extractor image.
Provide a nonempty `s3Gateway.rules` YAML array with
`endpoint`, `addressing_style` (`path` or `virtual`), and explicit bucket GET/PUT
prefixes. Both audio worker Deployments then receive its internal proxy URL.

Probes accept native Kubernetes definitions; set an individual probe to `null`
to disable it. Worker connections follow `service.port`, while the gateway
listener follows `service.targetPort`.

| Name | Description | Value |
| ---- | ----------- | ----- |
| `s3Gateway.enabled` | Deploy the gateway and route both audio workers through it | `true` |
| `s3Gateway.replicas` | Number of gateway replicas | `2` |
| `s3Gateway.rules` | Required nonempty array of storage provider rules when enabled | `[]` |
| `s3Gateway.rules[].endpoint` | Storage origin without a path; HTTPS and no explicit port by default | |
| `s3Gateway.rules[].addressing_style` | Bucket addressing style: `path` or `virtual` | |
| `s3Gateway.rules[].buckets` | Map of bucket names to GET/PUT prefix lists; prefixes must end in `/` | |
| `s3Gateway.dpAnnotations` | Annotations for the gateway Deployment | `{}` |
| `s3Gateway.podAnnotations` | Annotations for gateway Pods | `{}` |
| `s3Gateway.strategy` | Deployment update strategy; empty uses Kubernetes defaults | `{}` |
| `s3Gateway.automountServiceAccountToken` | Mount a service-account token in gateway Pods | `false` |
| `s3Gateway.serviceAccountName` | Existing service account for gateway Pods; empty uses the namespace default | `""` |
| `s3Gateway.podSecurityContext` | Pod security context | `{runAsNonRoot: true, runAsUser: 10000, runAsGroup: 10000, seccompProfile: {type: RuntimeDefault}}` |
| `s3Gateway.securityContext` | Gateway container security context | `{allowPrivilegeEscalation: false, readOnlyRootFilesystem: true, capabilities: {drop: [ALL]}}` |
| `s3Gateway.command` | Override the gateway container command | `["python","-m","audio_extractor.s3_gateway"]` |
| `s3Gateway.args` | Arguments for the gateway container | `[]` |
| `s3Gateway.shareProcessNamespace` | Share the process namespace between containers | `false` |
| `s3Gateway.sidecars` | Additional containers in gateway Pods | `[]` |
| `s3Gateway.initContainers` | Init containers in gateway Pods | `[]` |
| `s3Gateway.extraVolumes` | Additional native Kubernetes volume definitions | `[]` |
| `s3Gateway.extraVolumeMounts` | Additional native Kubernetes volume mounts for the gateway container | `[]` |
| `s3Gateway.service.type` | Gateway Service type | `ClusterIP` |
| `s3Gateway.service.port` | Gateway Service port used by workers | `8080` |
| `s3Gateway.service.targetPort` | Gateway container listening port; also sets `S3_GATEWAY_PORT` | `8080` |
| `s3Gateway.service.annotations` | Annotations for the gateway Service | `{}` |
| `s3Gateway.probes.readiness` | Readiness probe; `null` disables it | `{httpGet: {path: /healthz, port: http}}` |
| `s3Gateway.probes.liveness` | Liveness probe; `null` disables it | `{httpGet: {path: /healthz, port: http}}` |
| `s3Gateway.probes.startup` | Optional startup probe | `null` |
| `s3Gateway.pdb.enabled` | Create a gateway PodDisruptionBudget | `true` |
| `s3Gateway.pdb.maxUnavailable` | Maximum unavailable gateway Pods, as a count or percentage | `1` |
| `s3Gateway.terminationGracePeriodSeconds` | Pod termination grace period in seconds | `45` |
| `s3Gateway.envVars` | Gateway environment variables; supports direct values, ConfigMap references, and Secret references | See individual settings below |
| `s3Gateway.envVars.S3_GATEWAY_FORCE_HTTPS` | Require HTTPS storage endpoints and public destination addresses | `true` |
| `s3Gateway.envVars.S3_GATEWAY_MAX_UPLOAD_BYTES` | Maximum upload size in bytes (1 GiB); keep this value quoted | `"1073741824"` |
| `s3Gateway.envVars.S3_GATEWAY_MAX_CONCURRENT_REQUESTS` | Maximum concurrent transfers per gateway process | `20` |
| `s3Gateway.envVars.S3_GATEWAY_TIMEOUT_SECONDS` | Transfer deadline and upstream read timeout in seconds | `3600` |
| `s3Gateway.envVars.S3_GATEWAY_SHUTDOWN_GRACE_SECONDS` | Drain deadline in seconds; keep below the Pod termination grace period | `30` |
| `s3Gateway.resources` | Gateway container resource requests and limits | `{requests: {cpu: 50m, memory: 128Mi}, limits: {cpu: "1", memory: 256Mi}}` |
| `s3Gateway.nodeSelector` | Node selector for gateway Pods | `{}` |
| `s3Gateway.affinity` | Affinity for gateway Pods | `{}` |
| `s3Gateway.tolerations` | Tolerations for gateway Pods | `[]` |

`S3_GATEWAY_RULES` and `S3_GATEWAY_PORT` are reserved in `envVars`; configure
`rules` and `service.targetPort` instead.

HTTPS/public DNS upstreams are required by default. Development values explicitly
allow the local HTTP RustFS endpoint by setting `S3_GATEWAY_FORCE_HTTPS=false`.
Allow GET on output prefixes for validation and
restrict worker network egress to enforce the gateway boundary. See the
[audio extractor gateway documentation](../../audio-extractor/README.md#s3-egress-gateway)
for configuration, operational limits, security policy, Compose/Tilt usage, and tests.
