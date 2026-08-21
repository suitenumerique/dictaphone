# Dictaphone architecture and sequence diagrams

The diagrams in this folder are standalone Mermaid source files. They are linked
from this page so that documentation tooling can render or include them without
copying the diagrams into every document.

## Architecture

- [System architecture](diagrams/system-architecture.mmd) — clients, Kubernetes
  ingress, Django, Celery workers, storage, and the external summary service.
- [File routing by data policy](diagrams/file-routing-by-data-policy.mmd) — how
  an email address selects a policy, logical bucket, physical bucket, and the
  persisted retention snapshot for a file.

## Sequences

- [File creation and upload from web or mobile](diagrams/file-upload-sequence.mmd)
  — the shared API and presigned-upload protocol through audio extraction
  enqueueing.
- [File processing after upload](diagrams/file-processing-sequence.mmd) — the
  audio worker, FFmpeg extraction, persisted file storage, transcription task,
  and failure paths.
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
- Kubernetes deployment and routing: [`src/helm/`](../src/helm/)
