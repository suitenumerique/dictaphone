"""Normalize identity and bypass emails, preserving users and admin emails.

Original casing cannot be restored on reversal. Bypass collisions must be resolved
explicitly: automatically merging grants could change their activity or expiry.
"""

import string

from django.db import migrations

_ASCII_LOWERCASE_TABLE = str.maketrans(string.ascii_uppercase, string.ascii_lowercase)
BATCH_SIZE = 500


def normalize_email(email):
    """Freeze the normalization used when this migration was written."""
    if email is None:
        return None
    return email.strip().translate(_ASCII_LOWERCASE_TABLE)


def forwards(apps, schema_editor):
    """Normalize stored emails without merging users or access grants."""
    alias = schema_editor.connection.alias
    bypass_model = apps.get_model("core", "AccessBypassEmail")
    seen = {}
    for pk, email in (
        bypass_model.objects.using(alias).values_list("pk", "email").iterator()
    ):
        normalized = normalize_email(email)
        if normalized in seen:
            raise RuntimeError(
                "Resolve conflicting AccessBypassEmail entries before retrying "
                f"email normalization: {seen[normalized]} and {pk}."
            )
        seen[normalized] = pk

    for model_name in ("User", "AccessBypassEmail"):
        manager = apps.get_model("core", model_name).objects.using(alias)
        batch = []
        for obj in manager.only("pk", "email").iterator(chunk_size=BATCH_SIZE):
            normalized = normalize_email(obj.email)
            if normalized == obj.email:
                continue
            obj.email = normalized
            batch.append(obj)
            if len(batch) == BATCH_SIZE:
                manager.bulk_update(batch, ["email"], batch_size=BATCH_SIZE)
                batch = []
        if batch:
            manager.bulk_update(batch, ["email"], batch_size=BATCH_SIZE)


class Migration(migrations.Migration):
    dependencies = [("core", "0024_oidc_access_policy")]

    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
