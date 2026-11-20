"""Sweep expired uploads and process queued deletions on each cron run.

Operators can also queue outputs from historical failures or expire old pending
AI jobs before the same sweep runs.
"""

from datetime import timedelta
from time import monotonic

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Exists, OuterRef, Q
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

PROGRESS_INTERVAL_SECONDS = 20


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


def cleanup_batches(queryset, batch_size, limit, *, oldest_first=False):
    """Page over candidates once, including rows that remain eligible after a failure."""
    queryset = (
        queryset.order_by("created_at", "pk")
        if oldest_first
        else queryset.order_by("pk")
    )
    remaining = limit
    page = queryset
    while remaining is None or remaining > 0:
        size = batch_size if remaining is None else min(batch_size, remaining)
        batch = list(page[:size])
        if not batch:
            break
        last = batch[-1]
        yield batch
        if remaining is not None:
            remaining -= len(batch)
        if oldest_first:
            page = queryset.filter(
                Q(created_at__gt=last.created_at)
                | Q(created_at=last.created_at, pk__gt=last.pk)
            )
        else:
            page = queryset.filter(pk__gt=last.pk)


class Command(BaseCommand):
    """Retry storage deletions and finalize files whose cleanup is complete."""

    help = "Delete expired temporary uploads and reconcile queued storage deletions"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument(
            "--limit",
            type=int,
            help="Maximum rows per cleanup step (default: unlimited)",
        )
        parser.add_argument(
            "--batch-size", type=int, default=100, help="Rows per batch (default: 100)"
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
        batch_size = options["batch_size"]
        hours = options["pending_ai_hours"]
        if limit is not None and limit < 1:
            raise CommandError("Limit must be positive")
        if batch_size < 1:
            raise CommandError("Batch size must be positive")
        if hours is not None and hours < 1:
            raise CommandError("Pending AI job age must be positive")
        now = timezone.now()
        dry_run = options["dry_run"]
        # Record optional job work first so this run's sweep can pick it up.
        # Preview counts each step from the current state without queuing work.
        if hours is not None:
            self.fail_pending_jobs(
                now - timedelta(hours=hours), limit, batch_size, dry_run
            )
        if options["failed_jobs"]:
            self.queue_failed_jobs(limit, batch_size, dry_run)
        self.clean_objects(now, limit, batch_size, dry_run)

    def fail_pending_jobs(self, cutoff, limit, batch_size, dry_run):
        """Fail the oldest pending jobs, release quota, and queue result deletion."""
        jobs = AiFileJob.objects.filter(
            status=AiJobStatusChoices.PENDING, created_at__lt=cutoff
        )
        if dry_run:
            self.stdout.write(f"Would fail pending AI jobs: {jobs[:limit].count()}")
            return
        count = 0
        last_progress = monotonic()
        for batch in cleanup_batches(jobs, batch_size, limit, oldest_first=True):
            for job in batch:
                count += job.mark_failed(cleanup_now=False)
                last_progress = self.write_progress_if_due(
                    last_progress, f"failed_pending_ai_jobs={count}"
                )
        self.stdout.write(f"Failed pending AI jobs: {count}")

    def queue_failed_jobs(self, limit, batch_size, dry_run):
        """Backfill deletion intent for failed jobs from previous releases."""
        objects = failed_job_objects().only("pk", "file")
        if dry_run:
            self.stdout.write(
                f"Would queue failed job objects: {objects[:limit].count()}"
            )
            return
        count = 0
        last_progress = monotonic()
        for batch in cleanup_batches(objects, batch_size, limit):
            for obj in batch:
                queue_object_deletion(obj, cleanup_now=False)
                count += 1
                last_progress = self.write_progress_if_due(
                    last_progress, f"queued_failed_job_objects={count}"
                )
        self.stdout.write(f"Queued failed job objects: {count}")

    def clean_objects(self, now, limit, batch_size, dry_run):
        """Sweep expired uploads and due deletions in bounded batches."""
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
        objects = (cleanup_candidates(now) | expired_uploads).only(
            "pk", "file", "kind", "created_at", "checksum_source"
        )
        if dry_run:
            self.stdout.write(f"Would delete: {objects[:limit].count()}")
            return

        processed = count = failures = 0
        last_progress = monotonic()
        for batch in cleanup_batches(objects, batch_size, limit):
            for deleted, failed in self.clean_batch(batch, cutoff):
                processed += 1
                count += deleted
                failures += failed
                last_progress = self.write_progress_if_due(
                    last_progress,
                    f"processed={processed}, deleted={count}, failed={failures}",
                )
        self.stdout.write(f"Deleted: {count}")
        if failures:
            raise CommandError(
                f"Storage cleanup incomplete: {failures} deletions failed"
            )

    def write_progress_if_due(self, last_progress, message):
        """Flush interim progress so it is visible in container logs."""
        now = monotonic()
        if now - last_progress >= PROGRESS_INTERVAL_SECONDS:
            self.stdout.write(f"Progress: {message}")
            self.stdout.flush()
            return now
        return last_progress

    def clean_batch(self, batch, cutoff):
        """Report each deletion outcome and finalize fully cleaned files."""
        files = set()
        for obj in batch:
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
                    files.add(obj.file_id)
                yield deleted, False
            except (BotoCoreError, ClientError, ImproperlyConfigured, OSError) as exc:
                # Provider responses may contain credentials or signed URLs.
                self.stderr.write(f"object={obj.pk}: {type(exc).__name__}")
                yield False, True

        # A hard-deleted file can be removed once all of its storage cleanup is complete.
        for file_id in sorted(files):
            finalize_file_deletion(file_id)
