"""Require a file owner for every storage object."""

from django.db import migrations, models


def restore_storage_owners(apps, schema_editor):
    """Recover legacy owner links without discarding incomplete cleanup."""
    alias = schema_editor.connection.alias
    objects = apps.get_model("core", "ObjectStorageObject").objects.using(alias)
    files = apps.get_model("core", "File").objects.using(alias)
    detached = objects.filter(file__isnull=True)
    detached.filter(state="deleted").delete()
    detached.filter(file_identifier__in=files.values("pk")).update(
        file_id=models.F("file_identifier")
    )
    if detached.exists():
        raise RuntimeError(
            "Uncleaned storage objects refer to deleted files. Finish their cleanup "
            "with the previous release before applying this migration."
        )


class Migration(migrations.Migration):
    dependencies = [("core", "0029_object_storage_deleting_index")]

    operations = [
        migrations.RunPython(restore_storage_owners, migrations.RunPython.noop),
        migrations.RunSQL("SET CONSTRAINTS ALL IMMEDIATE", migrations.RunSQL.noop),
        migrations.AlterField(
            model_name="objectstorageobject",
            name="file",
            field=models.ForeignKey(
                on_delete=models.DO_NOTHING,
                related_name="storage_objects",
                to="core.file",
            ),
        ),
    ]
