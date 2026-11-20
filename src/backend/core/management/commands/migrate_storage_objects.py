"""Realign immutable artifacts with their creator's current bucket routing."""

import time
from uuid import UUID

from django.core.management.base import BaseCommand, CommandError

from core.models import ObjectStorageObject
from core.storage_migration import CLEANUP_SOURCE, inspect_objects, migrate_object

PROGRESS_INTERVAL_SECONDS = 20


def _parse_uuid(value, option):
    """Reject malformed selections before touching the database."""
    try:
        return UUID(str(value))
    except ValueError as exc:
        raise CommandError(f"{option} requires a valid UUID") from exc


def _migrate_objects(objects, *, source_bucket):
    for obj_id in objects.values_list("pk", flat=True):
        try:
            yield obj_id, migrate_object(obj_id, source_bucket=source_bucket)
        except Exception as exc:  # noqa: BLE001 # pylint: disable=broad-exception-caught
            yield obj_id, exc


class Command(BaseCommand):
    """Bounded, restartable migration driven entirely by tracked object rows."""

    help = (
        "Migrate finalized storage objects to the creator's currently configured bucket"
    )

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--batch-size", type=int, default=100)
        parser.add_argument("--limit", type=int, default=1000)
        parser.add_argument("--object", dest="objects", action="append", type=str)
        parser.add_argument("--file", dest="files", action="append", type=str)
        parser.add_argument("--source-bucket")
        parser.add_argument("--start-after", help="Resume after the last examined UUID")

    def handle(self, *args, **options):
        if options["batch_size"] < 1 or options["limit"] < 1:
            raise CommandError("Batch size and limit must be positive")
        object_ids = [
            _parse_uuid(value, "--object") for value in options["objects"] or []
        ]
        file_ids = [_parse_uuid(value, "--file") for value in options["files"] or []]
        source_bucket = options["source_bucket"]
        if source_bucket == "":
            raise CommandError("--source-bucket must not be empty")
        start_after = options["start_after"]
        cursor = (
            _parse_uuid(start_after, "--start-after")
            if start_after is not None
            else None
        )
        objects = ObjectStorageObject.objects.exclude(
            checksum_source=CLEANUP_SOURCE
        ).order_by("pk")
        if object_ids:
            objects = objects.filter(pk__in=object_ids)
        if file_ids:
            objects = objects.filter(file_identifier__in=file_ids)
        if source_bucket is not None:
            objects = objects.filter(storage_bucket_name=source_bucket)
        counts = dict.fromkeys(
            ("aligned", "migrated", "deferred", "failed", "skipped"), 0
        )
        processed = 0
        failures = []
        last_progress = time.monotonic()
        while processed < options["limit"]:
            batch = objects if cursor is None else objects.filter(pk__gt=cursor)
            batch = batch[: min(options["batch_size"], options["limit"] - processed)]
            results = (
                inspect_objects(batch).items()
                if options["dry_run"]
                else _migrate_objects(batch, source_bucket=source_bucket)
            )
            processed_before_batch = processed
            for obj_id, outcome in results:
                if isinstance(outcome, Exception):
                    # A bad artifact must not prevent independent transfers.
                    failures.append((obj_id, type(outcome).__name__))
                    result = "failed"
                else:
                    result = outcome
                counts[result] += 1
                processed += 1
                cursor = obj_id
                last_progress = self._write_progress_if_due(
                    processed, options["limit"], counts, obj_id, last_progress
                )
            if processed == processed_before_batch:
                break
        prefix = "Dry run (would migrate): " if options["dry_run"] else ""
        self.stdout.write(
            prefix + ", ".join(f"{key}={value}" for key, value in counts.items())
        )
        self.stdout.write(f"Last examined PK: {cursor if processed else 'none'}")
        self._write_failures(failures)
        if counts["failed"]:
            raise CommandError(f"{counts['failed']} storage object migration(s) failed")

    def _write_progress_if_due(self, processed, limit, counts, last, last_progress):
        """Write a snapshot only when the reporting interval has elapsed."""
        now = time.monotonic()
        if now - last_progress >= PROGRESS_INTERVAL_SECONDS:
            self.stdout.write(self._progress(processed, limit, counts, last))
            return now
        return last_progress

    def _write_failures(self, failures):
        """Report collected errors together after the migration finishes."""
        if failures:
            self.stderr.write(
                "Failed objects: "
                + ", ".join(f"{obj_id} ({error})" for obj_id, error in failures)
            )

    @staticmethod
    def _progress(processed, limit, counts, last):
        """Describe the current migration state without per-object output."""
        return (
            f"Progress: processed={processed}/{limit}, "
            + ", ".join(f"{key}={value}" for key, value in counts.items())
            + f", last_pk={last}"
        )
