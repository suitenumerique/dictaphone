"""Add AI failure reasons and a durable transcription usage ledger."""

import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


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
        migrations.CreateModel(
            name="TranscriptionUsage",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        help_text="primary key for the record as UUID",
                        primary_key=True,
                        serialize=False,
                        verbose_name="id",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        help_text="date and time at which a record was created",
                        verbose_name="created on",
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True,
                        help_text="date and time at which a record was last updated",
                        verbose_name="updated on",
                    ),
                ),
                ("ai_job_id", models.UUIDField(unique=True)),
                ("submitted_at", models.DateTimeField()),
                ("duration_seconds", models.FloatField()),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="transcription_usages",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "db_table": "transcription_usage",
                "indexes": [
                    models.Index(
                        fields=["user", "submitted_at"],
                        name="transcript_usage_user_time_idx",
                    )
                ],
            },
        ),
    ]
