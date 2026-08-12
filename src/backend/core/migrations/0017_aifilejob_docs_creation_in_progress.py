from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0016_remove_file_file_snapshot_complete_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="aifilejob",
            name="docs_creation_in_progress",
            field=models.BooleanField(default=False),
        ),
    ]
