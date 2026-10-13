from django.db import migrations


def restore_file_states(apps, schema_editor):
    """Restore the inferred value when rolling the schema back."""
    File = apps.get_model("core", "File")
    AudioJob = apps.get_model("core", "AudioJob")
    db = schema_editor.connection.alias
    for file in File.objects.using(db).iterator(chunk_size=500):
        job = (
            AudioJob.objects.using(db)
            .filter(file_id=file.pk)
            .order_by("-created_at", "-id")
            .first()
        )
        state = "pending_audio_extraction"
        if job and job.status == "processing":
            state = "extracting_audio"
        elif job and job.status in {"failed", "stale"}:
            state = "audio_extraction_failed"
        elif job and job.status == "success" and job.mode == "validation":
            state = "extraction_done"
        File.objects.using(db).filter(pk=file.pk).update(audio_extraction_state=state)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0019_backfill_audio_jobs"),
    ]

    operations = [
        migrations.RunPython(migrations.RunPython.noop, restore_file_states),
        migrations.RemoveField(model_name="file", name="audio_extraction_state"),
    ]
