# Object storage

`ObjectStorageObject` is the authoritative location of each application artifact.
The record contains its physical bucket, exact key, owning file, kind, state,
size, and optional integrity metadata. Bucket configuration resolves the endpoint
and credentials; those secrets are not stored in the database.

| Owner | Required object references |
| --- | --- |
| File | `original_object`, `temporary_upload_object` |
| Transcoding AudioJob | `output_object` |
| Validation AudioJob | No output; input comes from `source_job.output_object` |
| AiFileJob | `result_object` |

New models allocate their objects transactionally. File upload locations use the
creator's policy at creation time. Subsequent audio and AI objects use the owning
file's original object's bucket. Keys are allocated once; changing a filename or
policy does not rederive an existing location. Bulk inserts must supply their own
object references because they bypass model save hooks.

Reads, signed URLs, playback, and result writes follow these references. Media
authorization requires the exact bucket and key to identify a tracked media object
owned by the authorized file. There is no fallback to a file-level bucket or a
reconstructed legacy key. Existing key formats remain valid through their records.

File retention deadlines and lifecycle state remain on File. Original-data cleanup
deletes tracked original, temporary, and audio objects; full file cleanup also
deletes results and other tracked historical artifacts. Every storage record has
a file owner. Hard deletion keeps the file and its object records in the database
until storage cleanup completes. Failed storage deletions stay eligible for
retry with `cleanup_storage_objects`.

Before applying migration `0030`, run `cleanup_storage_objects` with the previous
release to clear pending deletions for files already removed from the database.
Stop old backend processes and jobs before applying the migration. It removes
ownerless `deleted` rows, restores links for rows whose files still exist, and
stops if any remaining ownerless rows still need cleanup.

ETags are opaque identifiers. Native provider checksums retain their algorithm and
full-object/composite semantics; backend AI writes record full-content SHA-256.
Checksum observations preserve established baselines and report comparable
mismatches. Metadata observation is not independent content read-back verification.

## Upgrades

Follow the [0.16.x backfill](../UPGRADE.md#0160) and
[0.17.0 schema transition](../UPGRADE.md#0170) in the upgrade guide.

## Retry outstanding deletions

To recover explicit deletion requests and clean up eligible copies left by bucket
migrations, preview and retry tracked objects in the `deleting` state:

```sh
python manage.py cleanup_storage_objects --dry-run --limit 100
python manage.py cleanup_storage_objects --limit 100
```

The second command deletes eligible tracked objects. When cleanup succeeds, it
also removes any hard-deleted file whose storage is now fully cleaned.

## Moving tracked objects

Use `migrate_storage_objects` to realign finalized artifacts after routing
configuration changes.

Deploy the updated backend and result writers everywhere before running migrations.
No schema migration is required. Keep both bucket configurations and credentials
available throughout the migration and cleanup. Equip the destination bucket with
an `AbortIncompleteMultipartUpload` lifecycle rule or the provider equivalent.
Configure the creator's new routing in `DATA_POLICY_CONFIGURATIONS` and restart
processes so all instances use that configuration. The command resolves the
current creator email and uses the default policy for files without a creator.

```sh
python manage.py migrate_storage_objects --dry-run --limit 1000
python manage.py migrate_storage_objects --batch-size 100 --limit 1000
python manage.py migrate_storage_objects --start-after LAST_EXAMINED_UUID
python manage.py migrate_storage_objects --file FILE_UUID --source-bucket old-bucket
python manage.py migrate_storage_objects --object OBJECT_UUID
python manage.py cleanup_storage_objects --limit 1000
```

`--file` and `--object` may be repeated. Source filters use physical bucket names.
The limit bounds examined objects, including aligned and deferred rows. Each run
prints per-object results, totals, and the last examined UUID. Pass that UUID to
`--start-after` with the same filters to continue the scan. Select deferred rows
again once they become eligible. A dry run counts eligible migrations and performs
no storage or database writes. Failures produce a nonzero exit status while other
selected objects continue. Reruns can overwrite untracked destinations and reuse
cleanup locations for the same artifact once the copy is due for cleanup.
A location owned by another tracked artifact causes a failure. No bucket listing
is used.

To parallelize a source bucket on Kubernetes, configure a
[`backend.managementJobs` template](../src/helm/dictaphone/README.md#manual-management-jobs)
for `migrate_storage_objects --source-bucket old-bucket` and create multiple Jobs
with distinct names from that template. Each command transfers one object at a
time. It reports `skipped` when it cannot immediately lock an object for reservation
or transfer, or when the object is no longer in scope. Skipped candidates count
toward each Job's `--limit` and advance its scan cursor. Set `--limit` to cover the
expected source inventory for a single pass, or resume bounded runs with their
cursors. After the parallel Jobs complete, scan the source bucket again from the
beginning to revisit skipped objects. Retry failed objects and objects that become
eligible separately as needed.

Available, published artifacts on finalized files are eligible for transfer.
For eligible objects already marked `missing` or `deleted`, migration updates
the recorded bucket in the database and preserves the object ID, key, metadata,
and deletion timestamp. It makes no storage requests and creates no
cleanup record for the source. A pending cleanup record at the destination
defers the move until cleanup finishes. These updates count as `migrated`.
Deleted artifacts can be migrated after their retention deadline. Migration
cleanup records are excluded from the scan.

If a file records completed original data deletion, migration repairs its
`missing` original, temporary upload, and audio records to `deleted`. This
also applies when the bucket is already aligned. Other missing records retain
their state. The historical deletion time
may be unknown, so migration preserves `deleted_at` as recorded. A passed
retention deadline or a pending deletion alone does not establish deletion.
Transcripts and summaries are outside the scope of original data cleanup.

The command reports objects already in their expected bucket as aligned, unless
an in-place state repair is needed. Available originals and audio on active files
or files pending original-data deletion can move until the original-data grace
deadline. Trashed files remain eligible until their trash purge grace deadline.
Eligible missing originals and audio can move even after the original-data grace
deadline.
Pending uploads, temporary upload keys outside completed original data cleanup,
and audio outputs with unexpired signed upload URLs are deferred when a move is
needed. A transfer is also deferred if the recorded full-object checksum
algorithm cannot be verified. File policy snapshots, deadlines (including grace
periods), timestamps, lifecycle state, ownership, and job references are
preserved. The command checks eligibility again before cutover.

One object row lock and database transaction cover the entire transfer and
verification. Budget database transaction timeouts for the largest object; writers
and deletion can wait for that transfer. There is no file-wide migration lock.
The backend downloads the source to temporary disk, verifies any supported
full-object checksum, and uploads using the destination's credentials and
configured upload ACL. The migration checks the destination size with HEAD and,
when the provider returns a supported full-object checksum, compares it with the
checksum of the local source bytes. Otherwise it reads the entire destination
to verify the size and SHA-256. ETags remain opaque. The upload preserves content
type, encoding, language, disposition, cache headers, expiry, and user metadata.
Provision temporary disk space (`TMPDIR`) for the largest object per concurrent
command and network capacity for a source download, an upload, and a possible
full destination download. Uploads stream from disk. Objects up to
`FILE_UPLOAD_MAX_SIZE` (capped at S3's 5 GiB single-request limit) use a single
PUT; larger objects use multipart parts of that size.

Before writing, the command commits an independent cleanup obligation in the
existing object table. These rows link to the owning file and keep the object kind,
use `checksum_source=migration` and `state=deleting`, have no artifact
references, and keep the authoritative object UUID in `etag` to tie the cleanup
location to that artifact.
After verified cutover, the destination obligation is replaced atomically by an
old-source obligation; the authoritative object ID stays unchanged. These rows
are cleanup obligations, not rollback history. Interrupted or failed writes leave
the original row authoritative and the destination discoverable for cleanup or
retry. Run `cleanup_storage_objects` regularly alongside normal retention jobs.
The command removes tracked objects. Use the destination lifecycle rule to abort
incomplete multipart uploads, which persist until completed or aborted.

Old source copies keep serving URLs issued before cutover for up to 24 hours (or
the configured audio timeout or S3 signed URL lifetime if longer). This covers
signed URLs and media URLs that still name the old bucket: media authorization
signs requests for the retained copy while its authoritative object is live and
the usual access checks pass. On these cleanup rows,
`published_at` identifies a retained source and `metadata_checked_at` stores its
cleanup deadline. Cleanup also consults the file's existing original-data,
hard-deletion and trash deadlines with grace periods, so URL retention never
extends those deadlines. Explicit file or original-data deletion tasks reschedule
while a signed audio upload URL remains valid. Once the task proceeds to
`delete_file_objects`, it deletes the migration copies in scope without waiting
for their retained download URLs to expire. Successful cleanup removes these
copy records.

### Reconcile pending objects after the source stops receiving writes

A source bucket can still have `pending` rows after the routing switch. For
example, the 0.16.x backfill could record a checksum for an original that it found
without publishing the row. The migration defers pending rows, so you may need
to reconcile them before rerunning it.

Run reconciliation once uploads and background jobs can no longer write to the
source bucket. It checks every pending row in the specified physical bucket,
regardless of object kind, file lifecycle, or grace period. Preview the results
first, then apply them.

```sh
python manage.py reconcile_pending_storage_objects --source-bucket old-bucket --dry-run --limit 100
python manage.py reconcile_pending_storage_objects --source-bucket old-bucket
python manage.py migrate_storage_objects --source-bucket old-bucket
```

Reconciliation uses read-only S3 `HEAD` requests. It marks present keys
`available` and confirmed missing keys `deleted` in the database. Permission
errors and other failed checks leave the affected rows pending and are reported
by object UUID. The migration rerun applies the usual eligibility and retention
rules to the reconciled rows.

### Retire the source bucket

Before removing a source bucket's configuration or credentials, verify that no
non-deleted authoritative object still references the bucket and that no
cleanup obligations for the bucket remain. Deferred audio
objects can still depend on the source bucket after cleanup succeeds. Revisit
those objects once their signed upload URLs expire.
