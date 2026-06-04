"""Delete original file data after retention + grace period."""

from django.core.management.base import BaseCommand

from core.models import (
    File,
    FileLifecycleStateChoices,
    get_original_file_data_cutoff_datetime,
)
from core.tasks.file import process_original_file_data_deletion


class Command(BaseCommand):
    """Lifecycle command for original file data deletion."""

    help = "Delete original file data after retention + grace period."

    def handle(self, *args, **options):
        pending_count = File.objects.filter(
            hard_deleted_at__isnull=True,
            lifecycle_state=FileLifecycleStateChoices.ACTIVE,
            created_at__lte=get_original_file_data_cutoff_datetime(
                include_grace_period=False
            ),
        ).update(
            lifecycle_state=FileLifecycleStateChoices.PENDING_ORIGINAL_DATA_DELETION
        )

        eligible_files = File.objects.filter(
            hard_deleted_at__isnull=True,
            lifecycle_state=FileLifecycleStateChoices.PENDING_ORIGINAL_DATA_DELETION,
            created_at__lte=get_original_file_data_cutoff_datetime(
                include_grace_period=True
            ),
        ).values_list("id", named=True)

        deleted_count = 0
        for file in eligible_files.iterator(chunk_size=100):
            process_original_file_data_deletion.delay(file.id)
            deleted_count += 1

        self.stdout.write(
            "Marked "
            f"{pending_count} file(s) pending original data deletion, "
            f"queued deletion for {deleted_count} file(s)."
        )
