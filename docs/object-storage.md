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

## Upgrades

Follow the [0.16.x backfill](../UPGRADE.md#0160) and
[0.17.0 schema transition](../UPGRADE.md#0170) in the upgrade guide.

## Retry outstanding deletions

To recover explicit deletion requests left in the `deleting` state, preview
and retry the tracked objects:

```sh
python manage.py cleanup_storage_objects --dry-run --limit 100
python manage.py cleanup_storage_objects --limit 100
```

The second command deletes tracked objects with outstanding deletion requests.
Cleanup records survive owner deletion, and successful cleanup retains a deleted
tombstone. Run this as needed for operational recovery.
