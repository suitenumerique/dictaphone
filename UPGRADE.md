# Upgrade

All instructions to upgrade this project from one release to the next will be
documented in this file. Upgrades must be run sequentially, meaning you should
not skip minor/major releases while upgrading (fix releases can be skipped).

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

For most upgrades, you just need to run the django migrations with
the following command inside your docker container:

`python manage.py migrate`

(Note : in your development environment, you can `make migrate`.)

## [Unreleased]

### Deployment-neutral defaults

Before deploying, set the following environment variables on **both the backend
and Celery workers** to preserve the previous service addresses and access text
if you relied on the old defaults. Existing explicit overrides should be kept
with their current values instead.

```dotenv
AI_SERVICE_URL=http://meet-summary.meet.svc.cluster.local/api/v2/
RESTRICTED_ACCESS_MESSAGE={"en":"Access is reserved to state public servants.","fr":"L’accès est réservé aux agents de la Fonction Publique d'État."}
RESTRICTED_ACCESS_DOCUMENTATION_URL=https://docs.numerique.gouv.fr/docs/9bbf7c2f-13a9-47e8-961c-98a874f44f1e/
```

These variables have **no `DJANGO_` prefix**. The message is a JSON object;
when exporting it from a shell, quote/escape it as a single value. The example
above is dotenv syntax, not a shell script. Keep the trailing slash on
`AI_SERVICE_URL` because the application appends API paths to it.

Docs integration now defaults to disabled. If you use it, also retain/set these
environment variables with your existing URL and API key:

```dotenv
DOCS_INTEGRATION_ENABLED=True
DOCS_BASE_URL=https://your-existing-docs-host
DOCS_SERVER_TO_SERVER_API_KEY=<your-existing-docs-api-key>
```

Use your actual existing Docs URL and secret. The previous default URL was
`https://example.com`; it was a placeholder, not a usable integration endpoint.
Leave `DOCS_INTEGRATION_ENABLED=False` if you do not use Docs.

The new defaults use `http://localhost:8000/api/v2/` for AI, generic
restricted-access text, and an empty documentation URL. The logging comment
now describes the existing stdout logging behavior.

### File type removal

Files no longer have a `type` field: its only supported value was
`audio_recording`. Run `python manage.py migrate` to remove the column and replace
the creator/type/creation index with a creator/creation index.

The file API keeps returning `type: "audio_recording"` as a read-only
compatibility field. Creation requests may omit `type`; legacy requests that
include it are accepted and ignored. The legacy `type=audio_recording` list
filter is accepted and ignored, and upload-limit error responses retain their
existing shape. Updated clients no longer depend on the response field, while
continuing to send it during creation for compatibility with older backends.
Backend, web, and mobile releases can therefore be deployed independently.
AI job types and MIME types keep their existing behavior.

### File upload restrictions

`FILE_UPLOAD_RESTRICTIONS` has been removed. Replace any overrides under its
`audio_recording` key with the following independent environment variables
(without a `DJANGO_` prefix):

| Previous key | Environment variable | Default |
| --- | --- | --- |
| `max_size` | `FILE_UPLOAD_MAX_SIZE` | `1073741824` bytes (1 GiB) |
| `max_count_by_user` | `FILE_UPLOAD_MAX_COUNT_BY_USER` | `200` |
| `max_duration_seconds` | `FILE_UPLOAD_MEDIA_MAX_DURATION_SECONDS` | `10860` seconds (3 h 1 min) |
| `allowed_extensions` | `FILE_UPLOAD_ALLOWED_EXTENSIONS` | Existing list, unchanged |
| `allowed_mimetypes` | `FILE_UPLOAD_ALLOWED_MIMETYPES` | Existing list, unchanged |

List overrides are comma-separated strings, for example
`FILE_UPLOAD_ALLOWED_EXTENSIONS=.mp3,.wav` and
`FILE_UPLOAD_ALLOWED_MIMETYPES=audio/mpeg,audio/webm;codecs=opus`.
Integer limits accept non-negative integers. The defaults and the
`FILE_UPLOAD_APPLY_RESTRICTIONS` switch are unchanged. The frontend configuration
keeps its existing `audio_recording` structure and advertises a duration limit
60 seconds below the backend limit (3 hours by default).

### Audio extraction workers

1. Stop uploads and drain/stop the legacy `dictaphone-audio` Celery workers before
   migrating. They must not write the old shared audio key after the migration.
   Pending messages on the retired `dictaphone-audio` queue can then be purged;
   the migration recreates pending extraction work as database attempts.
2. Configure `AUDIO_EXTRACTOR_TRANSCODING_TOKEN` and
   `AUDIO_EXTRACTOR_VALIDATION_TOKEN` on the backend. Supply the matching token as
   `AUDIO_EXTRACTOR_TOKEN` on each respective HTTP worker. Use separate secrets.
3. Run `python manage.py migrate`. The migration backfills audio attempt history
   and references existing audio objects in place; it performs no S3 operations.
   Completed files keep their existing results and are not transcribed again.
4. Helm users: rename `celeryAudioExtractor` values to `audioExtractor`. The two
   HTTP worker deployments replace the legacy audio Celery worker. Worker API
   URLs must include `/api/internal/${API_VERSION}` (currently `v1.0`), for example
   `http://dictaphone-backend/api/internal/v1.0`.
5. Enable the HTTP workers and resume uploads. `AUDIO_JOB_TIMEOUT_SECONDS`
   defaults to 300 and governs leases, signed URLs, and the worker's hard process
   timeout. Workers read `AUDIO_EXTRACTOR_JOB_TIMEOUT_SECONDS`; set it to the same
   positive integer as the backend's `AUDIO_JOB_TIMEOUT_SECONDS`. Helm copies it
   from `backend.envVars`, and Compose maps the shared backend value to the worker
   variable.
   Rebuild the worker image to include the command enforcing this deadline.
   `AUDIO_JOB_MAX_RETRIES` defaults to 3 retries after the initial attempt, per
   stage. Every retry gets its own attempt row and transcoding output key.

File cleanup includes all attempt outputs and the legacy audio and temporary
upload keys. Final deletion is deferred until outstanding signed audio upload
URLs expire, keeping database history available for cleanup. Admins can start a
new extraction from the file actions; active attempts are reused.
