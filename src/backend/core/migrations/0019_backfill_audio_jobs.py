"""Backfill audio jobs in transactions that release locks after each chunk."""

import uuid
from itertools import islice

from django.conf import settings
from django.db import migrations, models, transaction


BATCH_SIZE = 500


def backfill_audio_jobs(apps, schema_editor):
    """Reference legacy objects in place; never access object storage here."""
    File = apps.get_model("core", "File")
    AudioJob = apps.get_model("core", "AudioJob")
    AiFileJob = apps.get_model("core", "AiFileJob")
    db = schema_editor.connection.alias
    files = (
        File.objects.using(db)
        .filter(audio_jobs__isnull=True)
        .order_by("pk")
        .iterator(chunk_size=BATCH_SIZE)
    )

    while chunk := list(islice(files, BATCH_SIZE)):
        jobs = []
        validations = []
        for file in chunk:
            done = file.audio_extraction_state == "extraction_done"
            failed = file.audio_extraction_state == "audio_extraction_failed"
            job_id = uuid.uuid4()
            job = AudioJob(
                id=job_id,
                file_id=file.pk,
                mode="transcoding",
                extraction_id=uuid.uuid4(),
                status="success" if done else "failed" if failed else "pending",
                duration_seconds=file.duration_seconds if done else None,
                output_key=(
                    f"{settings.FILE_UPLOAD_PATH}/{file.pk}.audio.ogg"
                    if done
                    else f"{settings.FILE_UPLOAD_PATH}/{file.pk}/audio/{job_id}.ogg"
                ),
                metadata={"migrated": True},
            )
            jobs.append(job)
            if done:
                validations.append(
                    AudioJob(
                        file_id=file.pk,
                        mode="validation",
                        status="success",
                        extraction_id=job.extraction_id,
                        source_job_id=job.pk,
                        metadata={"migrated": True},
                    )
                )

        with transaction.atomic(using=db):
            AudioJob.objects.using(db).bulk_create(jobs, batch_size=BATCH_SIZE)
            if validations:
                AudioJob.objects.using(db).bulk_create(
                    validations, batch_size=BATCH_SIZE
                )
                AiFileJob.objects.using(db).filter(
                    file_id__in=[job.file_id for job in validations],
                    type="transcript",
                ).update(
                    validated_audio_job_id=models.Case(
                        *[
                            models.When(file_id=job.file_id, then=models.Value(job.pk))
                            for job in validations
                        ],
                        output_field=models.UUIDField(),
                    )
                )


class Migration(migrations.Migration):
    atomic = False

    dependencies = [
        ("core", "0018_audio_jobs"),
    ]

    operations = [
        migrations.RunPython(backfill_audio_jobs, migrations.RunPython.noop),
    ]
