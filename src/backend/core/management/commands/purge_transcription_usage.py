"""Purge transcription usage history beyond the configured retention period."""

from datetime import timedelta

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from core.models import TranscriptionUsage


class Command(BaseCommand):
    """Delete expired ledger entries in bounded batches, preserving recent quota."""

    help = "Purge transcription usage older than TRANSCRIPTION_USAGE_RETENTION_DAYS"

    def add_arguments(self, parser):
        parser.add_argument(
            "--batch-size",
            type=int,
            default=1000,
            help="Rows per batch (default: 1000)",
        )

    def handle(self, *args, **options):
        days = settings.TRANSCRIPTION_USAGE_RETENTION_DAYS
        if days < 1:
            raise CommandError("TRANSCRIPTION_USAGE_RETENTION_DAYS must be at least 1.")
        batch_size = options["batch_size"]
        if batch_size < 1:
            raise CommandError("--batch-size must be at least 1.")

        cutoff = timezone.now() - timedelta(days=days)
        expired = TranscriptionUsage.objects.filter(submitted_at__lt=cutoff)
        count = 0
        while ids := list(
            expired.order_by("submitted_at", "pk").values_list("pk", flat=True)[
                :batch_size
            ]
        ):
            deleted, _ = expired.filter(pk__in=ids).delete()
            count += deleted

        self.stdout.write(f"Purged {count} transcription usage record(s).")
