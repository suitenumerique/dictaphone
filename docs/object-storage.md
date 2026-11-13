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
deletes results and other tracked historical artifacts. Cleanup records survive
owner deletion with a retained file UUID. Failed explicit deletion intent can still
be retried using `cleanup_storage_objects`; completed tombstones remain for audit.

ETags are opaque identifiers. Native provider checksums retain their algorithm and
full-object/composite semantics; backend AI writes record full-content SHA-256.
Checksum observations preserve established baselines and report comparable
mismatches. Metadata observation is not independent content read-back verification.

## Upgrading from the tracking release

The earlier release's object backfill must already be complete, including owner
references for pending and failed jobs. Schema migration `0027` removes
`File.storage_bucket_name`, its indexes, and `AudioJob.output_key`, requires File
and AI references, and enforces output ownership by audio mode. It contains no data
backfill or object-storage operations. Incomplete references cause the schema
constraints to fail rather than silently reconstructing locations.

Coordinate this schema change with the application deployment: old application
and worker processes still depend on the removed columns and must be stopped
before applying the schema. Start the updated processes afterward.

The completed `backfill_storage_objects` command is removed. Use `migrate_storage_objects` below to realign finalized artifacts after routing
configuration changes.


## Moving tracked objects

Deploy the updated backend and result writers everywhere before running migrations.
No schema migration is required. Keep both source and destination bucket
configurations and credentials available until cleanup finishes. Configure the
creator's new routing in `DATA_POLICY_CONFIGURATIONS` and restart processes so all
instances use that configuration. The command resolves the current creator email,
including the default policy for files without a creator.

```sh
python manage.py migrate_storage_objects --dry-run --limit 1000
python manage.py migrate_storage_objects --batch-size 100 --limit 1000
python manage.py migrate_storage_objects --file FILE_UUID --source-bucket old-bucket
python manage.py migrate_storage_objects --object OBJECT_UUID
python manage.py cleanup_storage_objects --limit 1000
```

`--file` and `--object` may be repeated. Source filters use physical bucket names.
The limit bounds examined objects, including aligned and deferred rows; batches
bound database enumeration. For large inventories, partition by file/object or
source bucket to avoid repeatedly examining the same aligned rows. Each object
prints a result followed by aligned, migrated, deferred, and failed totals. A dry
run's migrated count means “would migrate”; it performs no storage or database
writes. Failures produce a nonzero exit status while other selected objects
continue. Reruns safely overwrite an untracked destination or a cleanup location
belonging to the same artifact, but refuse another tracked artifact's location.
No bucket listing is used.

Only available, published artifacts on finalized files are eligible. Pending
uploads, temporary upload keys, expired artifacts, and audio outputs with unexpired
signed upload URLs are deferred. File policy snapshots, deadlines (including grace
periods), timestamps, lifecycle state, ownership, and job references are preserved;
the command never saves the file. Eligibility is checked again before cutover.

One object row lock and database transaction cover the entire transfer and
verification. Budget database transaction timeouts for the largest object; writers
and deletion can wait for that transfer. There is no file-wide migration lock.
The backend downloads the source to temporary disk, uploads using the destination's
credentials, then reads the entire destination to compare byte length and SHA-256.
ETags are treated as opaque. Content type, encoding, language, disposition, cache
headers, expiry and user metadata are preserved. Provision temporary disk space
(`TMPDIR`) for the largest object per concurrent command, and network capacity for
one source download, one upload, and one full destination download per object.
Managed multipart uploads bound memory usage for large objects.

Before writing, the command commits an independent cleanup obligation in the
existing object table. These detached rows retain the owning file UUID and kind,
use `checksum_source=migration` and `state=deleting`, have no artifact references, and keep the authoritative object UUID in `etag`
solely to prevent another artifact from claiming the same cleanup location.
After verified cutover, the destination obligation is replaced atomically by an
old-source obligation; the authoritative object ID stays unchanged. These rows
are cleanup obligations, not rollback history. Interrupted or failed writes leave
the original row authoritative and the destination discoverable for cleanup or
retry. Run `cleanup_storage_objects` regularly, alongside normal retention jobs.

Old source copies can serve already issued download URLs for up to 24 hours (or
the configured audio timeout / AWS URL lifetime if longer). On these cleanup rows,
`published_at` identifies a retained source and `metadata_checked_at` stores its
cleanup deadline. Cleanup also consults the file's existing original-data,
hard-deletion and trash deadlines with grace periods, so URL retention never
extends those deadlines. Explicit file/original-data deletion includes all detached
obligations immediately. Deleted cleanup rows remain tombstones like other tracked
locations. Keep old credentials configured until their cleanup has succeeded.
