"""Index cleanup candidates without blocking writes to storage objects."""

from django.contrib.postgres.operations import AddIndexConcurrently
from django.db import migrations, models


class Migration(migrations.Migration):
    atomic = False

    dependencies = [("core", "0028_remove_file_type")]

    operations = [
        AddIndexConcurrently(
            model_name="objectstorageobject",
            index=models.Index(
                fields=["id"],
                condition=models.Q(state="deleting"),
                name="storage_object_deleting_idx",
            ),
        ),
    ]
