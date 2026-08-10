"""Hard delete files after retention + grace period."""

from django.core.management.base import BaseCommand

from core.configuration import filter_files_by_policy_cutoff
from core.models import (
    File,
    FileLifecycleStateChoices,
)
from core.tasks.file import process_file_deletion


class Command(BaseCommand):
    """Lifecycle command for hard deletion."""

    help = "Hard delete files after retention + grace period."

    def handle(self, *args, **options):
        pending_count = (
            filter_files_by_policy_cutoff(
                File.objects.filter(hard_deleted_at__isnull=True),
                policy="file_hard_delete",
            )
            .exclude(lifecycle_state=FileLifecycleStateChoices.PENDING_AUTO_HARD_DELETE)
            .update(lifecycle_state=FileLifecycleStateChoices.PENDING_AUTO_HARD_DELETE)
        )

        eligible_files = filter_files_by_policy_cutoff(
            File.objects.filter(
                hard_deleted_at__isnull=True,
                lifecycle_state=FileLifecycleStateChoices.PENDING_AUTO_HARD_DELETE,
            ),
            policy="file_hard_delete",
            include_grace_period=True,
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
