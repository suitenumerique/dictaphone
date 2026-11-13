"""Register database-addressable storage objects and inspect provider metadata."""

from uuid import UUID

from django.core.management.base import BaseCommand, CommandError

from botocore.exceptions import BotoCoreError, ClientError

from core.models import (
    AiJobStatusChoices,
    AudioJobStatusChoices,
    File,
    FileLifecycleStateChoices,
    FileUploadStateChoices,
    ObjectStorageObject,
)
from core.object_storage import (
    ObjectIntegrityError,
    check_integrity,
    head_object,
    observe_object,
    register_existing_file,
)


def candidates(file):
    """Include optional and expired artifacts without requiring them to exist."""
    original_expected = (
        file.upload_state == FileUploadStateChoices.READY
        and file.lifecycle_state == FileLifecycleStateChoices.ACTIVE
        and file.hard_deleted_at is None
    )
    yield ObjectStorageObject.Kind.ORIGINAL, file.file_key, original_expected
    yield ObjectStorageObject.Kind.TEMPORARY, file.temporary_file_key, False
    yield ObjectStorageObject.Kind.AUDIO, file.legacy_audio_file_key, False
    for job in file.audio_jobs.all():
        if job.output_key:
            yield (
                ObjectStorageObject.Kind.AUDIO,
                job.output_key,
                original_expected and job.status == AudioJobStatusChoices.SUCCESS,
            )
    for job in file.ai_jobs.all():
        yield (
            job.type,
            job.key,
            (file.hard_deleted_at is None and job.status == AiJobStatusChoices.SUCCESS),
        )


class Command(BaseCommand):
    """An idempotent, bounded backfill; no object listing or content downloads."""

    help = "Backfill object storage records, model references, and HEAD metadata"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--skip-head", action="store_true")
        parser.add_argument("--batch-size", type=int, default=100)
        parser.add_argument("--limit", type=int)
        parser.add_argument("--file-id", action="append", type=UUID)
        parser.add_argument("--after-file-id", type=UUID)

    def handle(self, *args, **options):
        if options["batch_size"] < 1 or (
            options["limit"] is not None and options["limit"] < 1
        ):
            raise CommandError("Batch size and limit must be positive")
        queryset = File.objects.order_by("pk")
        if options["file_id"]:
            queryset = queryset.filter(pk__in=options["file_id"])
        cursor = options["after_file_id"]
        counts = {
            "files": 0,
            "objects": 0,
            "missing": 0,
            "expected_missing": 0,
            "errors": 0,
        }
        while True:
            batch = queryset
            if cursor:
                batch = batch.filter(pk__gt=cursor)
            remaining = options["batch_size"]
            if options["limit"] is not None:
                remaining = min(remaining, options["limit"] - counts["files"])
            if remaining <= 0:
                break
            files = list(batch[:remaining])
            if not files:
                break
            for file in files:
                try:
                    self._process_file(file, options, counts)
                except File.DoesNotExist:
                    # Concurrent lifecycle cleanup removed this file before registration.
                    pass
                counts["files"] += 1
                cursor = file.pk
            self.stdout.write(
                f"Progress: files={counts['files']} after_file_id={cursor}"
            )
        self.stdout.write(
            ("Dry run: " if options["dry_run"] else "Completed: ")
            + " ".join(f"{name}={value}" for name, value in counts.items())
        )
        if counts["errors"] or counts["expected_missing"]:
            raise CommandError(
                "Storage verification incomplete; see object errors above"
            )

    def _process_file(self, file, options, counts):
        if not options["dry_run"]:
            register_existing_file(file)
        seen = set()
        for kind, key, expected in candidates(file):
            if key in seen:
                continue
            seen.add(key)
            counts["objects"] += 1
            if options["skip_head"]:
                continue
            obj = file.storage_objects.filter(key=key).first()
            if obj is None:
                obj = ObjectStorageObject(
                    file=file,
                    file_identifier=file.pk,
                    kind=kind,
                    storage_bucket_name=file.storage_bucket_name,
                    key=key,
                )
            if obj.state in {obj.State.DELETING, obj.State.DELETED}:
                continue
            try:
                if options["dry_run"]:
                    head = head_object(obj)
                    check_integrity(obj, head)
                    missing = head is None
                else:
                    observe_object(obj, publish=expected)
                    missing = obj.state == obj.State.MISSING
            except (BotoCoreError, ClientError, OSError, ObjectIntegrityError) as exc:
                counts["errors"] += 1
                # Never print provider responses containing credentials or signed URLs.
                self.stderr.write(f"file={file.pk} kind={kind}: {type(exc).__name__}")
                continue
            if missing:
                counts["missing"] += 1
                if expected:
                    counts["expected_missing"] += 1
                    self.stderr.write(
                        f"file={file.pk} kind={kind}: expected object missing"
                    )
