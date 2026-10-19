"""Backfill failure reasons and usage from fields present before rate limiting."""

from itertools import batched

from django.conf import settings
from django.db import migrations

BATCH_SIZE = 500


def backfill_submissions(apps, schema_editor):
    """Classify existing failures and include remote transcripts in the quota."""
    ai_job = apps.get_model("core", "AiFileJob")
    usage = apps.get_model("core", "TranscriptionUsage")
    db = schema_editor.connection.alias
    failed_jobs = ai_job.objects.using(db).filter(status="failed")
    failed_jobs.update(failure_reason="UNKNOWN_FAILURE")
    for file_type, restrictions in settings.FILE_UPLOAD_RESTRICTIONS.items():
        failed_jobs.filter(
            file__type=file_type,
            file__duration_seconds__gt=restrictions["max_duration_seconds"],
        ).update(failure_reason="AUDIO_TOO_LONG")
    # Main has no submission snapshot: a remote ID proves submission, and the
    # job's creation time and file duration are the available historical values.
    submissions = ai_job.objects.using(db).filter(
        type="transcript",
        remote_job_id__isnull=False,
        file__creator_id__isnull=False,
    ).exclude(remote_job_id="").order_by("pk").values_list(
        "pk", "file__creator_id", "created_at", "file__duration_seconds",
        "status", "failure_reason",
    )
    for rows in batched(submissions.iterator(chunk_size=BATCH_SIZE), BATCH_SIZE):
        usage.objects.using(db).bulk_create(
            [
                usage(
                    ai_job_id=job_id,
                    user_id=user_id,
                    submitted_at=created_at,
                    duration_seconds=duration,
                    ignored=status == "failed",
                    ignored_reason=(
                        f"Transcription failed: {reason}" if status == "failed" else ""
                    ),
                )
                for job_id, user_id, created_at, duration, status, reason in rows
            ],
            ignore_conflicts=True,
        )


class Migration(migrations.Migration):
    dependencies = [("core", "0021_aifilejob_submission_quota")]

    operations = [
        migrations.RunPython(backfill_submissions, migrations.RunPython.noop),
    ]
