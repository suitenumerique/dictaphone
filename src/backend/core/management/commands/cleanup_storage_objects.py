"""Retry tracked storage deletions without relying on the original job row."""

from django.core.management.base import BaseCommand, CommandError

from core.models import ObjectStorageObject
from core.object_storage import delete_object


class Command(BaseCommand):
    """Retained cleanup records survive deletion of their owning file or job."""

    help = "Retry object deletions left in the deleting state"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        if options["limit"] < 1:
            raise CommandError("Limit must be positive")
        objects = ObjectStorageObject.objects.filter(
            state=ObjectStorageObject.State.DELETING,
        ).order_by("pk")[: options["limit"]]
        count = 0
        for obj in objects:
            if not options["dry_run"]:
                delete_object(obj)
            count += 1
        self.stdout.write(
            f"{'Would delete' if options['dry_run'] else 'Deleted'}: {count}"
        )
