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

The completed `backfill_storage_objects` command is removed. No bucket-copying or
provider-migration functionality is included.
