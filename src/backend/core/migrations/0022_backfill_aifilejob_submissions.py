"""Backfill existing AI jobs after the submission quota schema has committed."""

from django.conf import settings
from django.db import migrations, models


def backfill_submissions(apps, schema_editor):
    """Classify existing failures and include remote transcripts in the quota."""
    ai_job = apps.get_model("core", "AiFileJob")
    file = apps.get_model("core", "File")
    db = schema_editor.connection.alias
    failed_jobs = ai_job.objects.using(db).filter(status="failed")
    failed_jobs.update(failure_reason="UNKNOWN_FAILURE")
    for file_type, restrictions in settings.FILE_UPLOAD_RESTRICTIONS.items():
        failed_jobs.filter(
            file__type=file_type,
            file__duration_seconds__gt=restrictions["max_duration_seconds"],
        ).update(failure_reason="AUDIO_TOO_LONG")
    duration = file.objects.using(db).filter(pk=models.OuterRef("file_id"))
    ai_job.objects.using(db).filter(
        type="transcript", remote_job_id__isnull=False
    ).exclude(remote_job_id="").update(
        submitted_at=models.F("created_at"),
        submitted_audio_duration_seconds=models.Subquery(
            duration.values("duration_seconds")[:1]
        ),
    )


class Migration(migrations.Migration):
    dependencies = [("core", "0021_aifilejob_submission_quota")]

    operations = [
        migrations.RunPython(backfill_submissions, migrations.RunPython.noop),
    ]
