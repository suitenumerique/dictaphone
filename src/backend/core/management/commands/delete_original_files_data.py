"""Delete original file data after retention + grace period."""

from django.core.management.base import BaseCommand

from core.configuration import filter_files_by_policy_cutoff
from core.models import (
    File,
    FileLifecycleStateChoices,
)
from core.tasks.file import process_original_file_data_deletion


class Command(BaseCommand):
    """Lifecycle command for original file data deletion."""

    help = "Delete original file data after retention + grace period."

    def handle(self, *args, **options):
        pending_count = filter_files_by_policy_cutoff(
            File.objects.filter(
                hard_deleted_at__isnull=True,
                lifecycle_state=FileLifecycleStateChoices.ACTIVE,
            ),
            policy="original_file_data",
        ).update(
            lifecycle_state=FileLifecycleStateChoices.PENDING_ORIGINAL_DATA_DELETION
        )

        eligible_files = filter_files_by_policy_cutoff(
            File.objects.filter(
                hard_deleted_at__isnull=True,
                lifecycle_state=FileLifecycleStateChoices.PENDING_ORIGINAL_DATA_DELETION,
            ),
            policy="original_file_data",
            include_grace_period=True,
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
