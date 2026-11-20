"""Reconcile pending object records against their persisted storage locations."""

from time import monotonic

from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from botocore.exceptions import BotoCoreError, ClientError

from core.models import ObjectStorageObject
from core.object_storage import head_object, metadata_values

PROGRESS_INTERVAL_SECONDS = 20


def reconcile_object(obj, *, dry_run):
    """Classify the key and update the row if it still matches the observation."""
    head = head_object(obj)
    state = obj.State.DELETED if head is None else obj.State.AVAILABLE
    if dry_run:
        return state

    now = timezone.now()
    values = {"state": state, "metadata_checked_at": now, "updated_at": now}
    if head is None:
        values["deleted_at"] = now
    else:
        values.update(
            published_at=obj.published_at or now,
            deleted_at=None,
            etag=head.get("ETag", obj.etag),
            size=obj.size if obj.size is not None else head["ContentLength"],
        )
        # Keep recorded integrity baselines for subsequent reads and migration.
        if not obj.checksum_value:
            values.update(
                (name, value)
                for name, value in metadata_values(head).items()
                if name.startswith("checksum_")
            )

    updated = ObjectStorageObject.objects.filter(
        pk=obj.pk,
        state=obj.State.PENDING,
        storage_bucket_name=obj.storage_bucket_name,
        key=obj.key,
        updated_at=obj.updated_at,
    ).update(**values)
    return state if updated else "skipped"


class Command(BaseCommand):
    """Check pending storage locations in a single physical bucket."""

    help = "Mark pending object records as available or deleted based on storage HEAD"

    def add_arguments(self, parser):
        parser.add_argument("--source-bucket", required=True)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--batch-size", type=int, default=100)
        parser.add_argument("--limit", type=int)

    def handle(self, *args, **options):
        bucket = options["source_bucket"]
        batch_size = options["batch_size"]
        limit = options["limit"]
        if not bucket.strip():
            raise CommandError("--source-bucket must not be empty")
        if batch_size < 1 or (limit is not None and limit < 1):
            raise CommandError("Batch size and limit must be positive")

        objects = ObjectStorageObject.objects.filter(
            storage_bucket_name=bucket, state=ObjectStorageObject.State.PENDING
        ).order_by("pk")[:limit]
        counts = dict.fromkeys(("available", "deleted", "skipped", "failed"), 0)
        last_progress = monotonic()
        for obj in objects.iterator(chunk_size=batch_size):
            try:
                outcome = reconcile_object(obj, dry_run=options["dry_run"])
            except (BotoCoreError, ClientError, ImproperlyConfigured, OSError) as exc:
                self.stderr.write(f"object={obj.pk}: {type(exc).__name__}")
                outcome = "failed"
            counts[outcome] += 1
            now = monotonic()
            if now - last_progress >= PROGRESS_INTERVAL_SECONDS:
                self.stdout.write(
                    f"Progress: examined={sum(counts.values())}, last_pk={obj.pk}"
                )
                self.stdout.flush()
                last_progress = now

        prefix = "Dry run: " if options["dry_run"] else ""
        self.stdout.write(
            prefix + ", ".join(f"{name}={count}" for name, count in counts.items())
        )
        if counts["failed"]:
            raise CommandError(
                f"Storage reconciliation incomplete: {counts['failed']} checks failed"
            )
