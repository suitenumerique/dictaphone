# Dictaphone architecture and sequence diagrams

The diagrams in this folder are standalone Mermaid source files. They are linked
from this page so that documentation tooling can render or include them without
copying the diagrams into every document.

## Architecture

- [System architecture](diagrams/system-architecture.mmd) — clients, Kubernetes
  ingress, Django, Celery workers, HTTP audio workers, the S3 egress gateway,
  storage, and the external summary service. The audio path has an FFmpeg
  re-encoding worker and a separate
  result-validation worker. Each Deployment runs a polling supervisor, isolates
  attempts in fresh child processes, and exposes Kubernetes health endpoints.
- [File routing by data policy](diagrams/file-routing-by-data-policy.mmd) — how
  an email address selects a policy, logical bucket, physical bucket, and the
  persisted retention snapshot for a file.
- [Data purge and S3 lifecycle](diagrams/data-purge-lifecycle.mmd) — the daily
  applicative purge and the independent S3-managed lifecycle policies that
  provide a second retention safeguard.

## Sequences

- [Audio worker lifecycle](diagrams/audio-worker-lifecycle.mmd) — continuous
  polling, per-attempt deadlines, the 15-minute claim cutoff, the independent
  20-minute watchdog, health probes, and container restarts.
- [File creation and upload from web or mobile](diagrams/file-upload-sequence.mmd)
  — the shared API and presigned-upload protocol through audio extraction
  enqueueing.
- [File processing after upload](diagrams/file-processing-sequence.mmd) — the
  audio processing path through the S3 gateway, followed by transcription job
  reservation, submission, and retry handling.
- [Audio re-encoding worker](diagrams/audio-reencoding-worker-sequence.mmd) —
  HTTP task polling, gateway transfers with signed source and destination URLs,
  FFmpeg conversion, completion callbacks, isolated attempt processes, and
  deadline recovery.
- [Audio validation worker](diagrams/audio-validation-worker-sequence.mmd) —
  HTTP task polling, gateway transfers with signed audio URLs, independent
  validation, completion callbacks, isolated attempt processes, and deadline
  recovery.
- [Mobile authentication with PKCE](diagrams/mobile-auth-pkce-sequence.mmd) —
  the OIDC browser round trip, one-time authorization code, verifier check, and
  JWT issuance.
- [Summary service processing](diagrams/summary-service-sequence.mmd) — the
  v2 summary endpoint, Celery task, result storage, and webhook delivery. The
  internal summary-construction steps are intentionally collapsed. The service
  is implemented in the sibling Meet repository under `src/summary/summary`.
- [Transcription service processing](diagrams/transcription-service-sequence.mmd)
  — the v2 transcription endpoint, WhisperX task, transcript storage, and
  success or failure webhook delivery.
- [Summary webhook to Dictaphone](diagrams/summary-webhook-sequence.mmd) — how
  Dictaphone validates and asynchronously stores a summary result received from
  the summary service.
- [Transcription webhook to Dictaphone](diagrams/transcription-webhook-sequence.mmd)
  — how Dictaphone validates, stores, and follows up on transcript webhook
  events received from the summary service.

## Implementation references

- File API and upload finalization: [`viewsets.py`](../src/backend/core/api/viewsets.py)
- File processing tasks: [`file.py`](../src/backend/core/tasks/file.py)
- Data-policy and bucket resolution: [`configuration.py`](../src/backend/core/configuration.py)
- Audio worker supervision: [`supervisor.py`](../src/audio-extractor/audio_extractor/supervisor.py)
- Worker storage transfer routing: [`http_client.py`](../src/audio-extractor/audio_extractor/http_client.py)
- S3 gateway validation and streaming: [`s3_gateway/`](../src/audio-extractor/audio_extractor/s3_gateway/)
- Transactional audio-job orchestration: [`audio_jobs.py`](../src/backend/core/audio_jobs.py)
- Audio worker health endpoints: [`health.py`](../src/audio-extractor/audio_extractor/health.py)
- Kubernetes deployment and routing: [`src/helm/`](../src/helm/)
