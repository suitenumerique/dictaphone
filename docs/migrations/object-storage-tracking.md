# Migrate existing files to object storage tracking

Use this guide when upgrading an existing deployment to a release that introduces
`ObjectStorageObject`. The migration populates tracking records and links existing
files, audio jobs, and AI jobs to their stored artifacts.

This is a database backfill. Objects keep their existing buckets and keys; the
command does not copy, move, or delete S3 objects. File retention deadlines and
lifecycle states remain unchanged. Moving data to another provider is a separate
operation.

## 1. Prepare the deployment

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

## 2. Choose how to run the command

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
[chart instructions](../../src/helm/dictaphone/README.md#manual-management-jobs)
for naming, monitoring, and Cilium policy selectors.

## 3. Preview the backfill

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

## 4. Backfill a canary, then the remaining files

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

## 5. Recover interrupted or failed runs

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

## 6. Confirm completion

Run a final pass from the beginning without `--limit`, `--after-file-id`, or
`--skip-head`. It should exit successfully with `errors=0` and
`expected_missing=0`. Review any optional missing objects separately.

Check representative original, audio, transcript, and summary references in the
admin. Retain the final summary and investigate unresolved errors before using
the registry as the basis for a later bucket migration.

## Interpret results

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

## Optional: retry outstanding storage deletions

This is an operational recovery command, not a required backfill step. If normal
application cleanup has left records in the `deleting` state, preview and retry
those explicit deletion requests:

```sh
python manage.py cleanup_storage_objects --dry-run --limit 100
python manage.py cleanup_storage_objects --limit 100
```

The second command deletes the tracked storage objects. It does not infer that
missing or unlinked objects should be deleted. Cleanup records survive deletion
of the owner job or file, and successful cleanup retains a deleted tombstone.
