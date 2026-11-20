"""Sweep expired uploads and process queued deletions on each cron run.

Operators can also queue outputs from historical failures or expire old pending
AI jobs before the same sweep runs.
"""

from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Exists, OuterRef
from django.utils import timezone

from botocore.exceptions import BotoCoreError, ClientError

from core.models import (
    AiFileJob,
    AiJobStatusChoices,
    AudioJob,
    AudioJobStatusChoices,
    File,
    FileUploadStateChoices,
    ObjectStorageObject,
)
from core.object_storage import (
    delete_expired_upload,
    delete_object,
    finalize_file_deletion,
    queue_object_deletion,
)
from core.storage_migration import CLEANUP_SOURCE, cleanup_candidates


def failed_job_objects():
    """Select artifacts still needing deletion intent from failed or stale jobs."""
    failed_ai = AiFileJob.objects.filter(
        result_object_id=OuterRef("pk"), status=AiJobStatusChoices.FAILED
    )
    failed_audio = AudioJob.objects.filter(
        output_object_id=OuterRef("pk"),
        status__in=[AudioJobStatusChoices.FAILED, AudioJobStatusChoices.STALE],
    )
    return ObjectStorageObject.objects.filter(
        Exists(failed_ai) | Exists(failed_audio)
    ).exclude(
        state__in=[
            ObjectStorageObject.State.DELETING,
            ObjectStorageObject.State.DELETED,
        ]
    )


class Command(BaseCommand):
    """Retry storage deletions and finalize files whose cleanup is complete."""

    help = "Delete expired temporary uploads and reconcile queued storage deletions"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--limit", type=int, default=100, help="Maximum rows per cleanup step"
        )
        parser.add_argument(
            "--failed-jobs",
            action="store_true",
            help="Queue artifact deletion for historical failed AI and audio jobs",
        )
        parser.add_argument(
            "--pending-ai-hours",
            type=int,
            help="Fail pending AI jobs created more than this many hours ago",
        )

    def handle(self, *args, **options):
        limit = options["limit"]
        hours = options["pending_ai_hours"]
        if limit < 1:
            raise CommandError("Limit must be positive")
        if hours is not None and hours < 1:
            raise CommandError("Pending AI job age must be positive")
        now = timezone.now()
        dry_run = options["dry_run"]
        # Record optional job work first so this run's sweep can pick it up.
        # Preview counts each step from the current state without queuing work.
        if hours is not None:
            self.fail_pending_jobs(now - timedelta(hours=hours), limit, dry_run)
        if options["failed_jobs"]:
            self.queue_failed_jobs(limit, dry_run)
        self.clean_objects(now, limit, dry_run)

    def fail_pending_jobs(self, cutoff, limit, dry_run):
        """Fail the oldest pending jobs, release quota, and queue result deletion."""
        jobs = AiFileJob.objects.filter(
            status=AiJobStatusChoices.PENDING, created_at__lt=cutoff
        ).order_by("created_at", "pk")[:limit]
        if dry_run:
            self.stdout.write(f"Would fail pending AI jobs: {jobs.count()}")
            return
        count = sum(job.mark_failed(cleanup_now=False) for job in jobs.iterator())
        self.stdout.write(f"Failed pending AI jobs: {count}")

    def queue_failed_jobs(self, limit, dry_run):
        """Backfill deletion intent for failed jobs from previous releases."""
        objects = failed_job_objects().only("pk", "file").order_by("pk")[:limit]
        if dry_run:
            self.stdout.write(f"Would queue failed job objects: {objects.count()}")
            return
        count = 0
        for obj in objects.iterator(chunk_size=100):
            queue_object_deletion(obj, cleanup_now=False)
            count += 1
        self.stdout.write(f"Queued failed job objects: {count}")

    def clean_objects(self, now, limit, dry_run):
        """Sweep expired uploads and due deletions in one bounded batch."""
        # Give temporary uploads a day plus the lifetime of their signed upload policy.
        cutoff = now - timedelta(
            days=1, seconds=settings.AWS_S3_UPLOAD_POLICY_EXPIRATION
        )
        expired_uploads = (
            ObjectStorageObject.objects.filter(
                kind=ObjectStorageObject.Kind.TEMPORARY, created_at__lt=cutoff
            )
            .exclude(checksum_source=CLEANUP_SOURCE)
            .exclude(state=ObjectStorageObject.State.DELETED)
            # Upload finalization may still be reading the staging key.
            .exclude(
                Exists(
                    File.objects.filter(
                        temporary_upload_object_id=OuterRef("pk"),
                        upload_state=FileUploadStateChoices.ANALYZING,
                    )
                )
            )
        )
        objects = (
            (cleanup_candidates(now) | expired_uploads)
            .only("pk", "file", "kind", "created_at", "checksum_source")
            .order_by("pk")[:limit]
        )
        if dry_run:
            self.stdout.write(f"Would delete: {objects.count()}")
            return

        count = 0
        failures = 0
        files = set()
        for obj in objects.iterator(chunk_size=100):
            try:
                if (
                    obj.kind == obj.Kind.TEMPORARY
                    and obj.created_at < cutoff
                    and obj.checksum_source != CLEANUP_SOURCE
                ):
                    deleted = delete_expired_upload(obj, cutoff)
                else:
                    # Respect active audio upload leases and retained migration copies.
                    deleted = delete_object(obj, respect_retention=True)
                if deleted:
                    count += 1
                    files.add(obj.file_id)
            except (BotoCoreError, ClientError, ImproperlyConfigured, OSError) as exc:
                failures += 1
                # Provider responses may contain credentials or signed URLs.
                self.stderr.write(f"object={obj.pk}: {type(exc).__name__}")

        # A hard-deleted file can be removed once all of its storage cleanup is complete.
        for file_id in sorted(files):
            finalize_file_deletion(file_id)
        self.stdout.write(f"Deleted: {count}")
        if failures:
            raise CommandError(
                f"Storage cleanup incomplete: {failures} deletions failed"
            )
