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
   URLs use the backend origin (the `/audio-jobs/...` endpoints are at the root).
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
