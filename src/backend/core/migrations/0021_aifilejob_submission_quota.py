"""Persist AI failure reasons and account for transcription submissions."""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("core", "0020_remove_file_audio_extraction_state")]

    operations = [
        migrations.AddField(
            model_name="aifilejob",
            name="failure_reason",
            field=models.CharField(
                blank=True,
                choices=[
                    ("AUDIO_TOO_LONG", "Audio too long"),
                    (
                        "RATE_LIMIT_TRANSCRIPTION_EXCEEDED",
                        "Transcription rate limit exceeded",
                    ),
                    ("UNKNOWN_FAILURE", "Unknown failure"),
                ],
                default="",
                max_length=40,
            ),
        ),
        migrations.AddField(
            model_name="aifilejob",
            name="submitted_at",
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name="aifilejob",
            name="submitted_audio_duration_seconds",
            field=models.FloatField(blank=True, null=True),
        ),
    ]
