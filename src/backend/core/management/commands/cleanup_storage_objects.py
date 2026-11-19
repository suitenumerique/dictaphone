"""Retry tracked storage deletions without relying on the original job row."""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from botocore.exceptions import BotoCoreError, ClientError

from core.object_storage import delete_object, finalize_file_deletion
from core.storage_migration import cleanup_candidates


class Command(BaseCommand):
    """Retry storage deletions and finalize files whose cleanup is complete."""

    help = "Retry object deletions left in the deleting state"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        if options["limit"] < 1:
            raise CommandError("Limit must be positive")
        objects = (
            cleanup_candidates(timezone.now())
            .only("pk", "file")
            .order_by("pk")[: options["limit"]]
        )
        if options["dry_run"]:
            self.stdout.write(f"Would delete: {objects.count()}")
            return

        count = 0
        failures = 0
        files = set()
        for obj in objects.iterator(chunk_size=100):
            try:
                if delete_object(obj, respect_retention=True):
                    count += 1
                    files.add(obj.file_id)
            except (BotoCoreError, ClientError, OSError) as exc:
                failures += 1
                # Provider responses may contain credentials or signed URLs.
                self.stderr.write(f"object={obj.pk}: {type(exc).__name__}")

        for file_id in sorted(files):
            finalize_file_deletion(file_id)
        self.stdout.write(f"Deleted: {count}")
        if failures:
            raise CommandError(
                f"Storage cleanup incomplete: {failures} deletions failed"
            )
