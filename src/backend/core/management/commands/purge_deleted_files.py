"""Purge deleted files."""

from django.core.management.base import BaseCommand
from django.db.models import Q

from core.configuration import filter_files_by_policy_cutoff
from core.models import File
from core.tasks.file import process_file_deletion


class Command(BaseCommand):
    """
    Purge deleted files (object storage and database object):
    - files marked as hard deleted in database
    - files marked as soft deleted and for which the trashbin retention period has expired
    """

    help = "Purge deleted files"

    def handle(self, *args, **options):
        """Browse purgeable files and queue them through the file deletion task."""

        purgeable = filter_files_by_policy_cutoff(
            File.objects.filter(hard_deleted_at__isnull=True),
            policy="trashbin",
            include_grace_period=True,
            base_field="deleted_at",
        )
        files_to_purge = File.objects.filter(
            Q(hard_deleted_at__isnull=False) | Q(pk__in=purgeable.values("pk"))
        )

        count = 0
        for file in files_to_purge.iterator():
            if file.hard_deleted_at is None:
                file.hard_delete()

            process_file_deletion.delay(file.id)
            count += 1

        self.stdout.write(f"Purged {count} deleted file(s).")
