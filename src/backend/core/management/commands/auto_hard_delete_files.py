"""Hard delete files after retention + grace period."""

from django.core.management.base import BaseCommand

from core.models import (
    File,
    FileLifecycleStateChoices,
    get_file_hard_delete_cutoff_datetime,
)
from core.tasks.file import process_file_deletion


class Command(BaseCommand):
    """Lifecycle command for hard deletion."""

    help = "Hard delete files after retention + grace period."

    def handle(self, *args, **options):
        pending_count = (
            File.objects.filter(
                hard_deleted_at__isnull=True,
                created_at__lte=get_file_hard_delete_cutoff_datetime(
                    include_grace_period=False
                ),
            )
            .exclude(lifecycle_state=FileLifecycleStateChoices.PENDING_AUTO_HARD_DELETE)
            .update(lifecycle_state=FileLifecycleStateChoices.PENDING_AUTO_HARD_DELETE)
        )

        eligible_files = File.objects.filter(
            hard_deleted_at__isnull=True,
            lifecycle_state=FileLifecycleStateChoices.PENDING_AUTO_HARD_DELETE,
            created_at__lte=get_file_hard_delete_cutoff_datetime(
                include_grace_period=True
            ),
        )

        hard_deleted_count = 0
        for file in eligible_files.iterator():
            if file.deleted_at is None:
                file.soft_delete()
            file.hard_delete()
            process_file_deletion.delay(file.id)
            hard_deleted_count += 1

        self.stdout.write(
            "Marked "
            f"{pending_count} file(s) pending auto hard delete, "
            f"queued hard deletion for {hard_deleted_count} file(s)."
        )
