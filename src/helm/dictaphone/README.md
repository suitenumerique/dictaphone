# Dictaphone helm chart

## Parameters

### General configuration

| Name                                                                              | Description                                            | Value                                                            |
| --------------------------------------------------------------------------------- | ------------------------------------------------------ | ---------------------------------------------------------------- |
| `image.repository`                                                                | Repository to use to pull dictaphone's container image | `lasuite/dictaphone-backend`                                     |
| `image.tag`                                                                       | dictaphone's container tag                             | `latest`                                                         |
| `image.pullPolicy`                                                                | Container image pull policy                            | `IfNotPresent`                                                   |
| `image.credentials.username`                                                      | Username for container registry authentication         |                                                                  |
| `image.credentials.password`                                                      | Password for container registry authentication         |                                                                  |
| `image.credentials.registry`                                                      | Registry url for which the credentials are specified   |                                                                  |
| `image.credentials.name`                                                          | Name of the generated secret for imagePullSecrets      |                                                                  |
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
| `ingressAdmin.enabled`                                                            | whether to enable the Ingress or not                   | `false`                                                          |
| `ingressAdmin.className`                                                          | IngressClass to use for the Ingress                    | `nil`                                                            |
| `ingressAdmin.host`                                                               | Host for the Ingress                                   | `dictaphone.example.com`                                         |
| `ingressAdmin.path`                                                               | Path to use for the Ingress                            | `/admin`                                                         |
| `ingressAdmin.hosts`                                                              | Additional host to configure for the Ingress           | `[]`                                                             |
| `ingressAdmin.tls.enabled`                                                        | Weather to enable TLS for the Ingress                  | `true`                                                           |
| `ingressAdmin.tls.secretName`                                                     | Secret name for TLS config                             | `nil`                                                            |
| `ingressAdmin.tls.additional[].secretName`                                        | Secret name for additional TLS config                  |                                                                  |
| `ingressAdmin.tls.additional[].hosts[]`                                           | Hosts for additional TLS config                        |                                                                  |
| `ingressMediaFiles.enabled`                                                       | whether to enable the Ingress or not                   | `false`                                                          |
| `ingressMediaFiles.className`                                                     | IngressClass to use for the Ingress                    | `nil`                                                            |
| `ingressMediaFiles.host`                                                          | Host for the Ingress                                   | `dictaphone.example.com`                                         |
| `ingressMediaFiles.path`                                                          | Path to use for the Ingress                            | `/media/files/(.*)`                                              |
| `ingressMediaFiles.hosts`                                                         | Additional host to configure for the Ingress           | `[]`                                                             |
| `ingressMediaFiles.tls.enabled`                                                   | Weather to enable TLS for the Ingress                  | `true`                                                           |
| `ingressMediaFiles.tls.secretName`                                                | Secret name for TLS config                             | `nil`                                                            |
| `ingressMediaFiles.tls.additional[].secretName`                                   | Secret name for additional TLS config                  |                                                                  |
| `ingressMediaFiles.tls.additional[].hosts[]`                                      | Hosts for additional TLS config                        |                                                                  |
| `ingressMediaFiles.annotations.nginx.ingress.kubernetes.io/use-regex`             | Enable use of regex for ingress paths                  | `true`                                                           |
| `ingressMediaFiles.annotations.nginx.ingress.kubernetes.io/auth-url`              | Authentication URL for the ingress                     | `https://dictaphone.example.com/api/v1.0/files/media-auth/`      |
| `ingressMediaFiles.annotations.nginx.ingress.kubernetes.io/auth-response-headers` | Headers to pass from auth response                     | `Authorization, X-Amz-Date, X-Amz-Content-SHA256`                |
| `ingressMediaFiles.annotations.nginx.ingress.kubernetes.io/upstream-vhost`        | Upstream host for proxying                             | `minio.dictaphone.svc.cluster.local:9000`                        |
| `ingressMediaFiles.annotations.nginx.ingress.kubernetes.io/configuration-snippet` | Custom nginx configuration snippet                     | `add_header Content-Security-Policy "default-src 'none'" always; |

add_header Content-Disposition "attachment";
`|
|`serviceMediaFiles.host`                                                         |                                                        |`minio.dictaphone.svc.cluster.local`                                                                           |
|`serviceMediaFiles.port`                                                         |                                                        |`9000`                                                                                                         |
|`serviceMediaFiles.annotations`                                                  |                                                        |`{}` |

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
| `backend.securityContext`                             | Configure backend Pod security context                            | `nil`                                                                                                                                                                                                                                                                               |
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
| `backend.cronjobs[0].name`                     | Name of the CronJob                                                                | `clean-pending-files`                                     |
| `backend.cronjobs[0].schedule`                 | Schedule in cron format                                                            | `30 0 * * *`                                              |
| `backend.cronjobs[0].command`                  | The bash command to execute in the CronJob                                         | `["/bin/sh","-c","python manage.py clean_pending_files"]` |
| `backend.cronjobs[1].name`                     | Name of the CronJob                                                                | `purge-deleted-files`                                     |
| `backend.cronjobs[1].schedule`                 | Schedule in cron format                                                            | `45 0 * * *`                                              |
| `backend.cronjobs[1].command`                  | The bash command to execute in the CronJob                                         | `["/bin/sh","-c","python manage.py purge_deleted_files"]` |
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
| `backend.extraVolumeMounts`                    | Additional volumes to mount on the backend.                                        | `[]`                                                      |
| `backend.extraVolumes`                         | Additional volumes to mount on the backend.                                        | `[]`                                                      |
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
| `celeryBackend.securityContext`                             | Configure celeryBackend Pod security context                                             | `nil`                                                                                          |
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
| `celeryBackend.extraVolumeMounts`                           | Additional volumes to mount on the celeryBackend.                                        | `[]`                                                                                           |
| `celeryBackend.extraVolumes`                                | Additional volumes to mount on the celeryBackend.                                        | `[]`                                                                                           |
| `celeryBackend.pdb.enabled`                                 | Enable pdb on celeryBackend                                                              | `false`                                                                                        |

### frontend

| Name                                                   | Description                                                                         | Value                         |
| ------------------------------------------------------ | ----------------------------------------------------------------------------------- | ----------------------------- |
| `frontend.image.repository`                            | Repository to use to pull dictaphone's frontend container image                     | `lasuite/dictaphone-frontend` |
| `frontend.image.tag`                                   | dictaphone's frontend container tag                                                 | `latest`                      |
| `frontend.image.pullPolicy`                            | frontend container image pull policy                                                | `IfNotPresent`                |
| `frontend.dpAnnotations`                               | Annotations to add to the frontend Deployment                                       | `{}`                          |
| `frontend.command`                                     | Override the frontend container command                                             | `[]`                          |
| `frontend.args`                                        | Override the frontend container args                                                | `[]`                          |
| `frontend.replicas`                                    | Amount of frontend replicas                                                         | `3`                           |
| `frontend.shareProcessNamespace`                       | Enable share process namefrontend between containers                                | `false`                       |
| `frontend.sidecars`                                    | Add sidecars containers to frontend deployment                                      | `[]`                          |
| `frontend.securityContext`                             | Configure frontend Pod security context                                             | `nil`                         |
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
| `frontend.extraVolumeMounts`                           | Additional volumes to mount on the frontend.                                        | `[]`                          |
| `frontend.extraVolumes`                                | Additional volumes to mount on the frontend.                                        | `[]`                          |
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
