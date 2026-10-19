"""Index submission time for batched usage retention cleanup."""

from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models


class Migration(migrations.Migration):
    atomic = False

    dependencies = [("core", "0022_backfill_aifilejob_submissions")]

    operations = [
        AddIndexConcurrently(
            model_name="transcriptionusage",
            index=models.Index(
                fields=["submitted_at"], name="transcript_usage_time_idx"
            ),
        ),
    ]
