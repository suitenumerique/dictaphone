# Audio extractor

The audio extractor continuously polls an HTTP queue and processes one attempt
at a time. Set `AUDIO_EXTRACTOR_MODE` to `transcoding` (the default) or `validation`.
An empty queue does not stop the worker; it waits five seconds before polling again.
API failures use exponential retries with jitter, capped at approximately 30 seconds.

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
the validity of all signed URLs. The API URL is the backend origin, without the
public `/api/v1.0/` prefix.

The transcoding worker polls `GET /audio-jobs/transcoding/next`. A job looks like:

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
`POST /audio-jobs/transcoding/complete`. A successful response includes the audio
duration:

```json
{"id": "job-id", "status": "success", "duration_seconds": 12.5}
```

The validation worker polls `GET /audio-jobs/validation/next`. Its job looks like:

```json
{
  "id": "job-id",
  "job_kind": "validation",
  "expires_at": "2026-10-12T12:05:00+00:00",
  "source_url": "https://storage.example/signed-get"
}
```

It downloads the source and checks the OGG Opus stream with `opusinfo` and
`opusdec`, then posts to `POST /audio-jobs/validation/complete`:

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
| `AUDIO_EXTRACTOR_API_URL` | Yes | — | API base URL, such as `http://localhost:8000` |
| `AUDIO_EXTRACTOR_TOKEN` | Yes | — | Bearer token, at least 32 characters long |
| `AUDIO_EXTRACTOR_MODE` | No | `transcoding` | Queue to process: `transcoding` or `validation` |
| `AUDIO_EXTRACTOR_OUTPUT_SAMPLE_RATE` | No | `16000` | Output sample rate in Hz: `8000`, `12000`, `16000`, `24000`, or `48000` |
| `AUDIO_EXTRACTOR_OUTPUT_BITRATE` | No | `64k` | Output bitrate, such as `64k` or `96k` |
| `AUDIO_EXTRACTOR_REQUEST_TIMEOUT` | No | `30` | HTTP timeout in seconds |
| `AUDIO_EXTRACTOR_COMMAND_TIMEOUT` | No | `900` | Timeout for each media command in seconds |
| `AUDIO_EXTRACTOR_MAX_INPUT_BYTES` | No | `1073741824` | Maximum downloaded file size in bytes (1 GiB) |
| `AUDIO_EXTRACTOR_WORK_DIR` | No | `/work` | Directory for temporary job files |
| `AUDIO_EXTRACTOR_SENTRY_DSN` | No | — | Sentry DSN; Sentry is disabled when unset |
| `AUDIO_EXTRACTOR_ENVIRONMENT` | No | — | Deployment environment used by Sentry and the HTTP user agent |
| `AUDIO_EXTRACTOR_RELEASE` | No | — | Release identifier used by Sentry and the HTTP user agent; omitted from the HTTP user agent when unset |

Before sending an event or breadcrumb, the worker strips credentials, query
parameters, and fragments from HTTP and HTTPS URLs in Sentry data while preserving
the URL path. Local variables, request bodies, tracing, and Sentry logs are disabled
to reduce the chance of a signed URL being included through another SDK field.

## Run locally

With Python 3.14+, `uv`, and the `ffmpeg` and `opus-tools` commands installed, sync
the dependencies, set the required environment variables, and run the worker:

```sh
cd src/audio-extractor
uv sync --all-groups
export AUDIO_EXTRACTOR_API_URL=http://localhost:8000
export AUDIO_EXTRACTOR_TOKEN=replace-with-a-token-at-least-32-characters
uv run python -m audio_extractor
```

Set `AUDIO_EXTRACTOR_MODE=validation` to run the validation worker. The development
dependency group includes Ruff, Pylint, and pytest.
