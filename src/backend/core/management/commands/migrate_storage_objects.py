"""Realign immutable artifacts with their creator's current bucket routing."""

from django.core.management.base import BaseCommand, CommandError

from core.models import ObjectStorageObject
from core.storage_migration import migrate_object


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

    def handle(self, *args, **options):
        if options["batch_size"] < 1 or options["limit"] < 1:
            raise CommandError("Batch size and limit must be positive")
        objects = ObjectStorageObject.objects.exclude(checksum_source="migration")
        if options["objects"]:
            objects = objects.filter(pk__in=options["objects"])
        if options["files"]:
            objects = objects.filter(file_identifier__in=options["files"])
        if options["source_bucket"]:
            objects = objects.filter(storage_bucket_name=options["source_bucket"])
        counts = dict.fromkeys(("aligned", "migrated", "deferred", "failed"), 0)
        last = None
        processed = 0
        while processed < options["limit"]:
            batch = objects.order_by("pk")
            if last is not None:
                batch = batch.filter(pk__gt=last)
            ids = list(
                batch.values_list("pk", flat=True)[
                    : min(options["batch_size"], options["limit"] - processed)
                ]
            )
            if not ids:
                break
            for obj_id in ids:
                try:
                    result = migrate_object(obj_id, dry_run=options["dry_run"])
                except Exception as exc:  # noqa: BLE001 # pylint: disable=broad-exception-caught
                    # A bad artifact must not prevent independent transfers.
                    result = "failed"
                    self.stderr.write(f"{obj_id}: {type(exc).__name__}: {exc}")
                counts[result] += 1
                processed += 1
                self.stdout.write(f"{obj_id}: {result}")
            last = ids[-1]
        prefix = "Dry run (would migrate): " if options["dry_run"] else ""
        self.stdout.write(
            prefix + ", ".join(f"{key}={value}" for key, value in counts.items())
        )
        if counts["failed"]:
            raise CommandError(f"{counts['failed']} storage object migration(s) failed")
