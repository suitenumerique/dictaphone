from django.db import migrations, models


def backfill_file_configuration(apps, schema_editor):
    """Materialize the default configuration for files created before snapshots."""
    from core.configuration import get_default_profile

    File = apps.get_model("core", "File")
    default_profile = get_default_profile()

    for file in File.objects.filter(storage_bucket_name__isnull=True).iterator():
        values = default_profile.as_file_snapshot(file.created_at)
        if file.deleted_at is not None:
            values.update(default_profile.as_trashbin_snapshot(file.deleted_at))
        File.objects.filter(pk=file.pk).update(**values)


class Migration(migrations.Migration):

    dependencies = [("core", "0015_file_audio_extraction_state")]

    operations = [
        migrations.RunPython(backfill_file_configuration, migrations.RunPython.noop),
        migrations.RemoveConstraint(
            model_name='file',
            name='file_snapshot_complete',
        ),
        migrations.RemoveConstraint(
            model_name='file',
            name='file_original_deadline_order',
        ),
        migrations.RemoveConstraint(
            model_name='file',
            name='file_hard_delete_deadline_order',
        ),
        migrations.AlterField(
            model_name='file',
            name='file_auto_hard_delete_at',
            field=models.DateTimeField(),
        ),
        migrations.AlterField(
            model_name='file',
            name='file_auto_hard_delete_at_with_grace_period',
            field=models.DateTimeField(),
        ),
        migrations.AlterField(
            model_name='file',
            name='original_file_data_delete_at',
            field=models.DateTimeField(),
        ),
        migrations.AlterField(
            model_name='file',
            name='original_file_data_delete_at_with_grace_period',
            field=models.DateTimeField(),
        ),
        migrations.AlterField(
            model_name='file',
            name='storage_bucket_name',
            field=models.CharField(max_length=63),
        ),
        migrations.AddConstraint(
            model_name='file',
            constraint=models.CheckConstraint(condition=models.Q(('original_file_data_delete_at__lte', models.F('original_file_data_delete_at_with_grace_period'))), name='file_original_deadline_order'),
        ),
        migrations.AddConstraint(
            model_name='file',
            constraint=models.CheckConstraint(condition=models.Q(('file_auto_hard_delete_at__lte', models.F('file_auto_hard_delete_at_with_grace_period'))), name='file_hard_delete_deadline_order'),
        ),
    ]
