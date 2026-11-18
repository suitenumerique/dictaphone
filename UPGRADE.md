# Upgrade

This file contains release-specific deployment and data migration instructions.
Read the sections between your installed version and the target version, then
apply the applicable steps in chronological order. Backend/frontend release
versions and Helm chart versions are separate.

Run Django migrations with the target release's backend image and production
configuration, unless a section specifies an intermediate release:

```sh
python manage.py migrate --no-input
```

For local development, use `make migrate`. Back up the database before schema
changes and retain the configuration and credentials for existing storage buckets.

**Upgrading to 0.17.0 requires completing the 0.16.x storage backfill first.**
Use a 0.16.x image, preferably 0.16.1, for that procedure. The 0.17.0 image removes
the backfill command and legacy storage columns.

## [Unreleased]

## [0.17.0]

### Required deployment order

1. Complete the [0.16.0 storage tracking procedure](#0160) on a 0.16.x image,
   including its final verification pass. Include references for pending and
   failed jobs as well as completed artifacts.
2. Prepare the environment changes below on the backend and Celery workers.
3. Stop API and worker processes using the old schema, including audio workers
   and scheduled cleanup jobs. Migration `0027` removes columns used by the old
   application, so coordinate migration with the application rollout.
4. Run `python manage.py migrate --no-input` with the 0.17.0 image, then start
   the updated API, workers, and scheduled jobs.

Migration `0027` removes `File.storage_bucket_name`, its indexes, and
`AudioJob.output_key`, requires File and AI object references, and enforces audio
output ownership by mode. It performs no data backfill or S3 operations.
Incomplete references cause schema constraints to fail. Resolve them using the
0.16.x backfill before proceeding. Migration `0028` removes the redundant file
type and replaces its index as described below.

Artifact reads and writes now follow `ObjectStorageObject` references. Keep all
referenced buckets configured, with their existing endpoints and credentials.
Existing keys stay in place. The `backfill_storage_objects` command is retired
in 0.17.0. See [object storage](docs/object-storage.md) for the current model.

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

## [0.16.0]

### Object storage tracking (also applies to 0.16.1)

Run this procedure on **0.16.x before upgrading to 0.17.0**. Migration `0026`
adds the tracking schema but does not populate historical references. Deploying
the schema alone does not complete this upgrade.

This is a database backfill. Objects keep their existing buckets and keys; the
command does not copy, move, or delete S3 objects. File retention deadlines and
lifecycle states remain unchanged. Moving data to another provider is a separate
operation.

### 1. Prepare the deployment

- Make the backend image containing migration `0026` and the
  `backfill_storage_objects` command available to the deployment.
- Keep every bucket configuration referenced by existing files available,
  including its endpoint and credentials.
- Ensure the backfill can reach PostgreSQL and the configured storage endpoints
  and can issue HEAD requests for individual object keys.

Apply the schema migrations using the new backend image before starting the new
application version:

```sh
python manage.py migrate --no-input
```

Then deploy all API and worker instances with the new version. New writes must
register their objects before the historical backfill begins. Existing unregistered
artifacts remain readable through the legacy storage fallback during rollout.

### 2. Choose how to run the command

Run the commands below in a backend container with the deployment's configuration,
or configure a manual Job through Helm:

```yaml
backend:
  managementJobs:
    backfill-storage-objects:
      command: [python, manage.py, backfill_storage_objects]
      args: [--dry-run, --batch-size, "100"]
```

Deploy these values after the schema and application rollout. This creates a
suspended CronJob using the backend image, environment, secrets, and volumes.
For the default naming of a release named `dictaphone`, launch a preview with:

```sh
kubectl -n YOUR_NAMESPACE create job storage-backfill-preview-1 \
  --from=cronjob/dictaphone-backend-manual-backfill-storage-objects
kubectl -n YOUR_NAMESPACE logs -f job/storage-backfill-preview-1 -c dictaphone
```

For each subsequent step, set the corresponding command flags in `args`, deploy
the updated values, and create a Job with a new run name. Updating the template
does not modify an already running Job. Run only one backfill at a time.

Nothing runs automatically on deployment or on a schedule. Job retries default
to zero, and completed runs are retained for one day. Save the logs and progress
cursor before the Job expires. See the
[chart instructions](src/helm/dictaphone/README.md#manual-management-jobs)
for naming, monitoring, and Cilium policy selectors.

### 3. Preview the backfill

Start with a dry run:

```sh
python manage.py backfill_storage_objects --dry-run --batch-size 100
```

The command derives original uploads, temporary uploads, legacy audio, all audio
attempt outputs, transcripts, and summaries from database relationships. It checks
individual keys with HEAD requests; it never lists a bucket or downloads content.
A dry run makes no database or storage changes.

To preview a small set first, use `--limit 100` or repeat `--file-id UUID` for
selected files. `--batch-size` controls database batches, not the total run size.

Review missing required objects and provider errors before proceeding. The
[result reference below](#interpret-results) explains which findings need action.

### 4. Backfill a canary, then the remaining files

Remove `--dry-run` and run a bounded canary:

```sh
python manage.py backfill_storage_objects --limit 100 --batch-size 100
```

Inspect its summary and representative records in the read-only
`ObjectStorageObject` admin. Check the owning file, bucket, key, state, size, and
available checksum metadata. Confirm ordinary uploads and result retrieval still
work for the deployment.

Then run the complete backfill:

```sh
python manage.py backfill_storage_objects --batch-size 100
```

Registration is idempotent: rerunning from the beginning reuses existing records
and owner references. Existing linked locations are preserved; the command does
not select a new bucket from the creator's current email or policy.

### 5. Recover interrupted or failed runs

Progress lines include an `after_file_id` cursor. To resume after the last reported
batch:

```sh
python manage.py backfill_storage_objects --batch-size 100 \
  --after-file-id LAST_REPORTED_UUID
```

Files are ordered by UUID, not creation time. Newly created files may sort before
the cursor, which is why all writers must register new objects before backfilling.
After resuming, rerun from the beginning for the final verification pass.

A failed run can have successfully registered and checked other objects. The
cursor does not identify which earlier objects failed: retry their `--file-id`
values or rerun the full command after resolving the error.

`--skip-head` provides a database-only backfill if metadata requests must be
deferred. It does not verify presence or integrity; follow it with a full run
without that flag before considering the migration complete.

### 6. Confirm completion

Run a final pass from the beginning without `--limit`, `--after-file-id`, or
`--skip-head`. It should exit successfully with `errors=0` and
`expected_missing=0`. Review any optional missing objects separately.

Check representative original, audio, transcript, and summary references in the
admin. Retain the final summary and investigate unresolved errors before using
the registry as the basis for a later bucket migration.

### Interpret results

| Result | Meaning and action |
| --- | --- |
| `files` | Number of file records processed in this run. |
| `objects` | Number of database-derived candidate artifacts processed; this is not a count of physical S3 objects. |
| `missing` | Absent candidates, including optional temporary uploads, failed attempts, and expired artifacts. These do not all indicate data loss. |
| `expected_missing` | Missing artifacts required by a visible uploaded active file or successful job. Investigate the file and its lifecycle; the command exits unsuccessfully. |
| `errors` | Provider, authorization, connectivity, or integrity failures. Resolve and retry; the command exits unsuccessfully. |

Object records distinguish pending uploads, available artifacts, missing objects,
and deletion state. A pending record only reserves a location. Temporary uploads
can remain pending even when present because their signed upload URL can still
change their contents. Unverified or failed attempt outputs need not become
available during the backfill. Deleting and deleted records are left untouched.

Files hidden by their automatic hard-delete deadline are still backfilled during
the grace period. Missing artifacts on these files count only as `missing`, so
they do not fail verification. Objects that remain are registered and inspected
normally; the backfill does not restore user access or change retention deadlines.

HEAD observations record size, ETag, and recognized native provider checksums when
available. No historical content is downloaded to calculate a checksum. An absent
checksum is therefore expected for some providers or historical uploads and does
not itself fail the migration.

Checksums retain their algorithm and full-object/composite type. ETags are stored
separately and are not assumed to be MD5 hashes. Custom user metadata is not
treated as a provider-validated checksum. Existing checksum baselines are retained;
size changes or comparable full-object checksum mismatches on published objects
are reported as integrity errors. Explicit checksum API incompatibility allows a
plain HEAD fallback; authorization and transient errors remain failures.

`metadata_checked_at` means metadata was observed, not that content was downloaded
and independently rehashed. Concurrent observations cannot replace newer
publication or deletion state.


## [0.15.5]

### Configurable OIDC roles claim

If the provider uses a claim other than `roles`, set `OIDC_ROLES_CLAIM` to its
literal top-level UserInfo key, for example `provider:roles`, and include the
necessary scope in `OIDC_RP_SCOPES`. The default claim is `roles`.
There is no fallback to a different claim. See [access control](docs/access-control.md).

## [0.15.3]

### Access policy and email normalization

Run migrations `0024` and `0025`. To enable role restrictions, set
`OIDC_ALLOWED_ROLES` to a comma-separated list and ensure `OIDC_RP_SCOPES`
requests the provider's roles claim. Empty `OIDC_ALLOWED_ROLES` allows everyone.
Existing users without stored roles have `unknown` access when the policy is
enabled and must reauthenticate or receive an active **Access bypass email**.
Restricted and unknown users cannot upload or retry processing. New identities
with these statuses are redirected to `/restricted` without account creation.
Deploy clients that handle this access status and route. See
[access control](docs/access-control.md) for ongoing configuration.

Migration `0025` trims surrounding whitespace and lowercases ASCII characters
in stored identity and bypass emails. It preserves users and admin emails and
fails on bypass entries that normalize to the same address. Resolve those
conflicting grants explicitly, checking activity and expiry, then rerun migrate.
Original email casing cannot be restored by reversing the migration.

For existing local Keycloak installations, add the `user` and `priviledged_user`
realm roles, grant existing development users `priviledged_user`, and add a
multivalued **User Realm Role** mapper named `roles` to the client's dedicated
scope, included in UserInfo, ID tokens, and access tokens. Set
`OIDC_ALLOWED_ROLES=priviledged_user` and `OIDC_RP_SCOPES=openid email roles` in
the local environment file, recreate backend/workers, and sign in again.
Keycloak's realm import only initializes new realms.

## [0.15.0]

### Explicit credentials and token storage

Configure `DB_PASSWORD` (or credentials in `DATABASE_URL`), `AI_SERVICE_API_KEY`,
and `AI_WEBHOOK_API_KEY` explicitly. The previous built-in credentials were
removed. Supply the webhook key expected by the AI service or callbacks fail
authentication. Configure `AUDIO_EXTRACTOR_TRANSCODING_TOKEN` and
`AUDIO_EXTRACTOR_VALIDATION_TOKEN` on the backend and their corresponding
`AUDIO_EXTRACTOR_TOKEN` on each worker mode.

OIDC access and refresh token storage now default to disabled. If required by
your deployment, set `OIDC_STORE_ACCESS_TOKEN=True` and/or
`OIDC_STORE_REFRESH_TOKEN=True` explicitly. Refresh-token storage requires a
valid Fernet `OIDC_STORE_REFRESH_TOKEN_KEY`. Retain your existing valid key for
sessions containing encrypted refresh tokens. Custom image builds using the
`Build` configuration must supply `DJANGO_SECRET_KEY` explicitly.

### External result downloads

For webhook-supplied transcript and summary URLs, configure
`EXTERNAL_SOURCE_ALLOWED_URL_PREFIXES` as a JSON array of allowed origin/bucket
prefixes. `null` or an unset variable skips URL validation with a warning, while
`[]` denies all downloads. HTTPS is required when validation is enabled unless
`EXTERNAL_SOURCE_REQUIRE_HTTPS=False`. Redirects are rejected, so configure the
final source URL. Local HTTP storage needs an explicit HTTP override and prefixes.

### Helm chart 0.7.0

Enable `ingressPublic.enabled` and copy API hosts, ingress class, TLS settings,
and API annotations from `ingress` to `ingressPublic`. `ingress` serves the
frontend. Configure `ingressInternal` with the same hosts and ingress class plus
an appropriate source IP allowlist for media authentication, webhooks, and audio
workers. Check callbacks and worker access against that allowlist.
See [API ingresses](src/helm/dictaphone/README.md#api-ingresses) for controller
and compression requirements.

The chart defaults to non-root UID/GID 10000 and a read-only root filesystem.
Check custom images and persistent volume permissions. `/tmp` is provided by a
writable `emptyDir`; keep that mount when customizing volumes. See
[workload security defaults](src/helm/dictaphone/README.md#workload-security-defaults).

## [0.14.0]

### Rate limits and transcription usage

Run migrations `0021`–`0023`. Migration `0022` records historical transcript
submissions with remote job IDs using their creation time and file duration;
failed submissions are excluded from charged usage. The rolling per-user audio
quota defaults to 24 hours per 24 hours and accepts fractional values via
`RATE_LIMIT_AI_TRANSCRIPTION_AUDIO_HOURS_PER_24H`
(`0` blocks new positive-duration submissions).
Review `RATE_LIMIT_API_*` and `RATE_LIMIT_PKCE_TOKEN_EXCHANGE` for your deployment
and deploy clients that handle HTTP 429 and retry cooldowns.

Use shared Redis for production throttles and sessions. If PKCE exchanges pass
through proxies, set `AUTH_PKCE_TRUSTED_PROXIES` to the trusted proxy IPs/CIDRs
so failed exchanges are attributed to the correct client. Administrator login
also enforces account/IP lockouts, configured through
`RATE_LIMIT_ADMIN_LOGIN_FAILURE_LIMIT` and `RATE_LIMIT_ADMIN_LOGIN_COOLOFF_HOURS`.
Schedule `python manage.py purge_transcription_usage` to bound usage history;
`TRANSCRIPTION_USAGE_RETENTION_DAYS` defaults to 365.

## [0.13.0]

### Audio extraction workers

1. Stop uploads and drain/stop the legacy `dictaphone-audio` Celery workers before
   migrating. They must not write the old shared audio key after the migration.
   Pending messages on the retired `dictaphone-audio` queue can then be purged;
   the migration recreates pending extraction work as database attempts.
2. Configure `AUDIO_EXTRACTOR_TRANSCODING_TOKEN` and
   `AUDIO_EXTRACTOR_VALIDATION_TOKEN` on the backend. Supply the matching token as
   `AUDIO_EXTRACTOR_TOKEN` on each respective HTTP worker. Use separate secrets.
3. Run `python manage.py migrate --no-input` (migrations `0018`–`0020`).
   The migration backfills audio attempt history
   and references existing audio objects in place; it performs no S3 operations.
   Completed files keep their existing results and are not transcribed again.
4. Helm users: rename `celeryAudioExtractor` values to `audioExtractor`. Move
   image overrides from `image`, `frontend.image`, and `celeryAudioExtractor.image`
   to `images.backend`, `images.frontend`, and `images.audioExtractor`. Move
   registry credentials from `image.credentials` to `images.credentials`. The two
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

## [0.12.1]

### Upload ACL configuration

Bucket configuration now accepts `upload_acl` (default `"private"`). Set it to
JSON `null` for buckets with ACLs disabled. Deploy web/mobile clients that honor
the ACL returned by the upload API, including its absence for such buckets.
Add this key only after upgrading from 0.12.0, whose configuration rejects it.

## [0.12.0]

### Bucket routing and persisted retention deadlines

Replace the single-bucket storage settings with `S3_BUCKET_CONFIGURATIONS` and
`DATA_POLICY_CONFIGURATIONS`. Both accept JSON objects. For a single existing
bucket, a configuration can retain the existing secret environment variables:

```dotenv
S3_BUCKET_CONFIGURATIONS={"default":{"bucket_name_env":"AWS_STORAGE_BUCKET_NAME","access_key_id_env":"AWS_S3_ACCESS_KEY_ID","secret_access_key_env":"AWS_S3_SECRET_ACCESS_KEY","endpoint_url_env":"AWS_S3_ENDPOINT_URL","region_name":"your-region","signature_version":"s3v4"}}
DATA_POLICY_CONFIGURATIONS={"default":{"default":true,"bucket":"default"}}
```

Set the referenced variables to your existing bucket, credentials, and endpoint.
Omit `endpoint_url_env` for provider-default endpoints. Copy any existing region,
signature version, and public URL replacement into `region_name`,
`signature_version`, and `domain_replace` respectively. Bucket
names and credentials are resolved from the named environment variables.
Alternatively use the `S3_DEFAULT_BUCKET_NAME`, `S3_DEFAULT_ACCESS_KEY_ID`, and
`S3_DEFAULT_SECRET_ACCESS_KEY` variables referenced by the default configuration.

Configure the default profile to match the bucket and retention settings of
existing files **before running migrations `0014`–`0016`**. Migration `0016`
materializes the default policy for files predating snapshots, including
trash-bin deadlines for deleted files. It does not choose a historical policy
from the creator's current email or move S3 objects. Review deletion deadlines
before resuming cleanup tasks. Future configuration changes apply to new files;
existing files retain their snapshots.

Older copies of migration `0016` omitted the legacy bucket when populating
snapshots; the fix is included in 0.17.0 (`b61dfcd`). If that migration fails on
an older image because `storage_bucket_name` is null, use the corrected migration
code for this step before continuing the intermediate-release upgrades.

## [0.11.0]

### API authentication

OIDC user access tokens are no longer accepted as general API credentials.
Update integrations relying on that authentication path to use the supported
session or application mobile JWT authentication.

## [0.9.0]

### Automated data retention

Migration `0012` adds file lifecycle state. Review retention settings before
enabling `delete_original_files_data` and `auto_hard_delete_files` scheduled
commands. These commands enforce original-data and full-file deletion deadlines.
Keep `purge_deleted_files` scheduled for trash-bin cleanup. Helm supplies
retention CronJobs; review their schedules and configuration for your deployment.

## [0.5.4]

### Legacy mobile authentication removal

The `/api/v1.0/mobile-redirect/` route was removed. Update mobile clients using
session/CSRF deep links to the PKCE authorization-code exchange flow before
upgrading the backend. Keep `MOBILE_DEEP_LINK_SCHEME` aligned with the client.
