# Audio extractor

The audio extractor continuously polls an HTTP queue and processes one attempt
at a time. Set `AUDIO_EXTRACTOR_MODE` to `transcoding` (the default) or `validation`.
An empty queue does not stop the worker; it waits five seconds before polling again.
API failures use exponential retries with jitter, capped at approximately 30 seconds.

## Optional gVisor media isolation

Set `AUDIO_EXTRACTOR_MEDIA_SANDBOX=gvisor` to run `ffmpeg`, `ffprobe`, `opusinfo`,
and `opusdec` in a fresh gVisor sandbox for every command. The default is `none`,
which preserves direct execution for existing deployments and local development.
When enabled, sandbox failures never fall back to direct execution. A startup
check runs sandboxed FFmpeg before the worker becomes ready or claims a job.

The image bundles `runsc` release `20261102.0` and its companion binaries, verified
against the committed SHA-512 checksums. Updating the release requires updating
both `GVISOR_VERSION` in the Dockerfile and `gvisor-SHA512SUMS`. The separate,
read-only `/opt/media-rootfs` contains only the four media binaries, their ELF
dependencies, linker cache when applicable, and empty mount-point directories.
No Docker socket, nested Docker daemon, Kubernetes RuntimeClass, KVM device, or
node installation of gVisor is needed.

Python retains responsibility for HTTP and credentials. The sandbox uses Systrap,
no networking, no capabilities, a clean environment, private `/tmp`, and a bind
mount of only the current job at `/job`. Output files must be regular files with
a single link before the worker accesses them outside the sandbox. Runtime state
and temporary mount setup live under the writable work volume. Nested cgroup
management is disabled: the Kubernetes container's resource limits still apply
to the runtime and media processes together.

The launcher uses an explicit OCI specification with a single UID/GID mapping
from sandbox root to the worker's UID/GID. This uses runsc's native unprivileged
execution path, without the `--rootless` convenience flag or setuid helpers.
The supervisor explicitly force-deletes the sandbox after killing an attempt;
process-group cancellation alone is insufficient for detached runtime processes.
Cleanup failure stops the worker before it can reuse the workspace.

For a staging experiment on Kubernetes with AppArmor field support (1.30+), use
these Helm values alongside the image built from this source:

```yaml
audioExtractor:
  envVars:
    AUDIO_EXTRACTOR_MEDIA_SANDBOX: gvisor
  securityContext:
    seccompProfile:
      type: Unconfined
    appArmorProfile:
      type: Unconfined
```

These container-level overrides supersede the Pod's default seccomp profile.
Other chart defaults remain in force: UID/GID 10000, dropped capabilities,
no privilege escalation, and a read-only root filesystem. No annotation is
required with the modern AppArmor field. The outer worker's AppArmor and seccomp
restrictions are relaxed; gVisor still applies its own sandbox isolation. This
configuration does not satisfy the Restricted Pod Security Standard. Ops must
check admission policy, SELinux/AppArmor restrictions, and whether node kernels
permit unprivileged nested user namespaces and mounts. The settings do not
enable user namespaces if the host disables them. For production, evaluate
targeted outer-container profiles instead of carrying over these broad overrides.

Build the staging image from the repository root (publishing is a separate step):

```sh
docker build -f src/audio-extractor/Dockerfile \
  --target audio-extractor-production \
  -t lasuite/dictaphone-audio-extractor:gvisor-staging .
```

The staging deployment values in `dictaphone-deploiement/env/staging` select that
tag and enable the overrides above for both worker modes. Once deployed, check
for `gVisor media sandbox startup check passed`, both workers' readiness, a
successful transcoding task, and a successful validation task. Namespace or mount
permission errors at startup mean the effective node/container policy still
blocks sandbox creation. Missing-library errors indicate a rootfs packaging issue.
Removing the staging overrides, setting the sandbox mode to `none`, and restoring
the previous image tag rolls back the experiment.

Real-runtime integration tests cover conversion/probing/validation, file and
network isolation, command timeout cleanup, and supervisor cancellation. To run
them on a Linux host with the runtime installed and user namespaces available:

```sh
cd src/audio-extractor
uv run python build-media-rootfs.py /tmp/dictaphone-media-rootfs
RUN_GVISOR_TESTS=1 GVISOR_ROOTFS=/tmp/dictaphone-media-rootfs \
  uv run pytest tests/test_sandbox_integration.py
```

`GVISOR_RUNSC` can override `/usr/local/bin/runsc` for these tests. Its
`gvisor-bin/` companions must be alongside it. Testing on a Linux host verifies
the launcher; the built Alpine image and actual staging policy must also be
validated. On Docker, nested execution may require
`--security-opt seccomp=unconfined --security-opt apparmor=unconfined`.
See [gVisor rootless operation](https://gvisor.dev/docs/user_guide/rootless/)
and [Kubernetes AppArmor configuration](https://kubernetes.io/docs/tutorials/security/apparmor/).

## Worker lifecycle and health

The supervisor accepts tasks for `AUDIO_EXTRACTOR_MAX_RUNTIME_SECONDS` (900 seconds,
15 minutes). This includes idle time. At that deadline it stops claiming new work,
finishes the current attempt, cleans its workspace, and exits successfully.
Deployments restart the container. Normal 15-minute runs exceed Kubernetes' usual
ten-minute restart-backoff reset period; genuine early crashes can still back off.

Every attempt runs in a fresh child process to discard process state after parsing
untrusted media. `AUDIO_EXTRACTOR_JOB_TIMEOUT_SECONDS` limits the whole attempt,
including downloads, media commands, retries, uploads, and completion reporting.
Set it to the backend's `AUDIO_JOB_TIMEOUT_SECONDS`; Helm and Compose pass that value.
When the API provides `expires_at`, the worker also respects the server's lease.
It reserves up to five seconds of the budget for reporting an interrupted attempt.
At the deadline it kills the child's process group, including media commands,
and removes temporary files. Unreported attempts recover through backend lease expiry.

The container wrapper independently sends SIGTERM after
`AUDIO_EXTRACTOR_PROCESS_TIMEOUT_SECONDS` (1200 seconds, 20 minutes), then SIGKILL
if the process remains after `AUDIO_EXTRACTOR_SHUTDOWN_GRACE_SECONDS` (30 seconds).
The absolute watchdog bound is therefore 20 minutes 30 seconds by default.
SIGTERM and SIGINT stop claims and cancel the active child; they do not drain a
full task. Polling HTTP requests retain their configured request timeout, and the
outer watchdog/Kubernetes grace period bounds an unresponsive supervisor.
Timeout and grace values must be positive integers. The normal runtime must be
less than the process timeout.

The supervisor serves HTTP health probes on `AUDIO_EXTRACTOR_HEALTH_PORT` (8080):

- `/startupz`: initialization is complete.
- `/livez`: supervisor progress is recent; idle queues and API outages stay live.
- `/readyz`: the queue API has responded successfully and the worker is not draining.

Busy workers remain ready until the lifetime deadline. Probe handlers use local
state and make no backend or storage requests. A stalled supervisor becomes
unhealthy even if the HTTP server still responds. Readiness reports availability;
the supervisor itself stops claiming work when draining.

Helm configures all three probes on both worker Deployments, a 45-second Pod
termination grace period, and a rolling update with zero unavailable replicas
and one surge replica. Configure `audioExtractor.probes`, `strategy`, and
`terminationGracePeriodSeconds` to override these defaults. No Service is needed.
The root filesystem remains read-only; `/work` is cleaned on startup, after each
attempt, and on shutdown because its `emptyDir` survives container restarts.

## API

The worker sends its token as a bearer token when polling and reporting completion.
The API returns HTTP 204 when the selected queue is empty.

The backend creates one `AudioJob` row per attempt, recording creation, claim,
deadline, and completion times. Successful transcoding queues independent
validation of that attempt's output. Only validation success starts transcription.
Failures and expired leases create new attempts, up to `AUDIO_JOB_MAX_RETRIES`
(default: three retries per stage). Each transcoding attempt uploads to a unique
key. Late completions receive HTTP 409 and duplicate matching completions are
accepted without scheduling further work.

Configure the backend's `AUDIO_EXTRACTOR_TRANSCODING_TOKEN` and
`AUDIO_EXTRACTOR_VALIDATION_TOKEN` to match each worker's `AUDIO_EXTRACTOR_TOKEN`.
`AUDIO_JOB_TIMEOUT_SECONDS` (default: 300) controls both the claim deadline and
the validity of all signed URLs. Set the API URL to the backend origin followed
by `/api/internal/${API_VERSION}`, where `API_VERSION` is the backend setting
(currently `v1.0`). For example: `http://localhost:8000/api/internal/v1.0`.

The transcoding worker polls `GET /api/internal/v1.0/audio-jobs/transcoding/next`.
A job looks like:

```json
{
  "id": "job-id",
  "job_kind": "transcoding",
  "expires_at": "2026-10-12T12:05:00+00:00",
  "source_url": "https://storage.example/signed-get",
  "destination_url": "https://storage.example/signed-put",
  "destination_headers": {"X-amz-acl": "private"}
}
```

`destination_headers` is optional and defaults to an empty object. The worker sends
these headers with the upload. Include any headers required by the signed
destination URL, such as `X-amz-acl` when the URL was signed with an ACL.

It downloads the source, converts the first audio stream to mono OGG Opus, uploads
it to the signed destination URL, then posts to
`POST /api/internal/v1.0/audio-jobs/transcoding/complete`. A successful response
includes the audio duration:

```json
{"id": "job-id", "status": "success", "duration_seconds": 12.5}
```

The validation worker polls `GET /api/internal/v1.0/audio-jobs/validation/next`.
Its job looks like:

```json
{
  "id": "job-id",
  "job_kind": "validation",
  "expires_at": "2026-10-12T12:05:00+00:00",
  "source_url": "https://storage.example/signed-get"
}
```

It downloads the source and checks the OGG Opus stream with `opusinfo` and
`opusdec`, then posts to `POST /api/internal/v1.0/audio-jobs/validation/complete`:

```json
{"id": "job-id", "status": "success"}
```

Failed jobs are reported with `"status": "failure"` and an `error` message. The
worker also includes processing metadata in completion reports.

## Configuration

Worker settings use the `AUDIO_EXTRACTOR_` prefix:

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `AUDIO_EXTRACTOR_MAX_RUNTIME_SECONDS` | No | `900` | Stop claiming tasks after this worker lifetime; finish the current attempt |
| `AUDIO_EXTRACTOR_PROCESS_TIMEOUT_SECONDS` | No | `1200` | Independent process watchdog; sends SIGTERM |
| `AUDIO_EXTRACTOR_SHUTDOWN_GRACE_SECONDS` | No | `30` | Watchdog grace before SIGKILL |
| `AUDIO_EXTRACTOR_JOB_TIMEOUT_SECONDS` | No | `300` | Whole-attempt budget, matching the backend lease and signed URL duration |
| `AUDIO_EXTRACTOR_POLL_INTERVAL_SECONDS` | No | `5` | Wait after an empty queue response |
| `AUDIO_EXTRACTOR_HEALTH_PORT` | No | `8080` | HTTP startup, liveness, and readiness port |
| `AUDIO_EXTRACTOR_API_URL` | Yes | — | Internal API base URL including `/api/internal/${API_VERSION}`, such as `http://localhost:8000/api/internal/v1.0` |
| `AUDIO_EXTRACTOR_TOKEN` | Yes | — | Bearer token, at least 32 characters long |
| `AUDIO_EXTRACTOR_MODE` | No | `transcoding` | Queue to process: `transcoding` or `validation` |
| `AUDIO_EXTRACTOR_OUTPUT_SAMPLE_RATE` | No | `16000` | Output sample rate in Hz: `8000`, `12000`, `16000`, `24000`, or `48000` |
| `AUDIO_EXTRACTOR_OUTPUT_BITRATE` | No | `64k` | Output bitrate, such as `64k` or `96k` |
| `AUDIO_EXTRACTOR_REQUEST_TIMEOUT` | No | `30` | HTTP timeout in seconds |
| `AUDIO_EXTRACTOR_COMMAND_TIMEOUT` | No | `900` | Timeout for each media command in seconds |
| `AUDIO_EXTRACTOR_MAX_INPUT_BYTES` | No | `1073741824` | Maximum downloaded file size in bytes (1 GiB) |
| `AUDIO_EXTRACTOR_WORK_DIR` | No | `/work` | Directory for temporary job files |
| `AUDIO_EXTRACTOR_MEDIA_SANDBOX` | No | `none` | Media command execution: `none` or `gvisor`; sandbox startup failures are fatal when enabled |
| `AUDIO_EXTRACTOR_RUNSC_PATH` | No | `/usr/local/bin/runsc` | Bundled gVisor runtime executable |
| `AUDIO_EXTRACTOR_SANDBOX_ROOTFS` | No | `/opt/media-rootfs` | Read-only minimal media filesystem |
| `SENTRY_DSN` | No | — | Sentry DSN; Sentry is disabled when unset |
| `SENTRY_TRACES_SAMPLE_RATE` | No | `0.0` | Fraction of transactions to trace, from `0.0` (none) to `1.0` (all) |
| `AUDIO_EXTRACTOR_ENVIRONMENT` | No | — | Deployment environment used by Sentry and the HTTP user agent |

The Sentry release and HTTP user agent version are read from the package version in
`pyproject.toml`; they are not configurable through an environment variable.

Before sending an event or breadcrumb, the worker strips credentials, query
parameters, and fragments from HTTP and HTTPS URLs in Sentry data while preserving
the URL path and marking removed query parameters with `?[redacted]`. Trace
sampling is controlled by `SENTRY_TRACES_SAMPLE_RATE` and is off by default.

## Run locally

With Python 3.14+, `uv`, and the `ffmpeg` and `opus-tools` commands installed, sync
the dependencies, set the required environment variables, and run the worker:

```sh
cd src/audio-extractor
uv sync --all-groups
export AUDIO_EXTRACTOR_API_URL=http://localhost:8000/api/internal/v1.0
export AUDIO_EXTRACTOR_TOKEN=replace-with-a-token-at-least-32-characters
uv run python -m audio_extractor
```

Set `AUDIO_EXTRACTOR_MODE=validation` to run the validation worker. The development
dependency group includes Ruff, Pylint, and pytest.

## S3 egress gateway

The same image can run a credential-free proxy for presigned S3 downloads and
uploads:

```sh
python -m audio_extractor.s3_gateway
```

Set `S3_GATEWAY_RULES` to a JSON array allowing specific endpoints, buckets,
methods, and key prefixes:

```json
[
  {
    "endpoint": "https://storage.example.com",
    "addressing_style": "path",
    "buckets": {
      "dictaphone-inputs": {"GET": ["files/"]},
      "dictaphone-outputs": {"GET": ["files/"], "PUT": ["files/"]}
    }
  }
]
```

Use `addressing_style: "virtual"` for bucket subdomains. Endpoints must be HTTPS
origins without paths or ports; prefixes must be nonempty directories ending in
`/`. Allow GET on output prefixes so the validation worker can read them.

Standalone workers use `S3_GATEWAY_URL=http://s3-gateway:8080/proxy`; leaving it
unset or empty uses direct transfers. The proxy accepts GET/PUT at `/proxy` with
the presigned URL in `X-Target-URL`, and serves health checks at `/healthz`.
Only ordinary object downloads and uploads are supported. The gateway preserves
the provider's `upload_acl` header when supplied by the backend.

Keep the gateway internal and restrict ingress to workers. Enforce worker egress
through network policies; setting `S3_GATEWAY_URL` alone does not restrict direct
connections. Storage destinations must resolve to public addresses by default.
Keep `S3_GATEWAY_FORCE_HTTPS=true` in production, and avoid logging presigned URLs
or `X-Target-URL`.

### Deployment

Compose, Helm, and Tilt route workers through the gateway by default:

- **Helm:** supply `s3Gateway.rules` as a YAML array; missing rules fail rendering.
  Set `s3Gateway.enabled: false` to disable the gateway.
- **Compose:** local RustFS rules live in `env.d/development/s3-gateway.dist`.
  Set worker `S3_GATEWAY_URL` to an empty value to use direct transfers.
- **Tilt:** rules come from `src/helm/env.d/<environment>/values.dictaphone.yaml.gotmpl`.

Development configurations allow HTTP RustFS with `S3_GATEWAY_FORCE_HTTPS=false`.
The gateway defaults to port 8080, a 1 GiB upload
limit, 20 concurrent transfers, and a one-hour transfer timeout. See
[audio_extractor/s3_gateway](audio_extractor/s3_gateway/) for all settings and
validation rules.

To enable Sentry, set `SENTRY_DSN` in the gateway environment (Helm:
`s3Gateway.envVars`). Optional settings are `S3_GATEWAY_ENVIRONMENT` and
`SENTRY_TRACES_SAMPLE_RATE` (default: `0`). The gateway release is read from the
audio-extractor package version, matching the worker. The gateway
uses the worker's URL scrubbers for events, transactions, and breadcrumbs, with
request bodies, local variables, and Sentry logs disabled.

### Verification

```sh
make test-audio-extractor
```

Storage integration tests use `S3_ENDPOINT_URL` for RustFS and `S3_GATEWAY_URL`
for the gateway. Without a gateway URL, they start an in-process gateway.
Standalone `uv run pytest` skips these tests when `S3_ENDPOINT_URL` is unset.

Completion callbacks returning `410 Gone` mean that the file is no longer
available for processing (for example, it was deleted or reached its retention
deadline). Both workers discard the completion and finish the attempt normally,
without retries, error reporting, or a fallback failure callback. Other HTTP
errors retain their existing handling.
