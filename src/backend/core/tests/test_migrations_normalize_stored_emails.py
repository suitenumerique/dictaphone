"""Regression tests for normalizing existing identity and bypass emails."""

from datetime import timedelta
from importlib import import_module

from django.db import connection
from django.db.migrations.executor import MigrationExecutor
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

import pytest

from core import factories, models

pytestmark = pytest.mark.django_db
migration = import_module("core.migrations.0025_normalize_stored_emails")


def _run_migration():
    """Use historical models, as Django does when applying the migration."""
    executor = MigrationExecutor(connection)
    apps = executor.loader.project_state([("core", "0024_oidc_access_policy")]).apps
    migration.forwards(apps, connection.schema_editor())


@pytest.mark.parametrize(
    "stored, expected",
    [
        (" John.Doe@Example.COM ", "john.doe@example.com"),
        ("Dısk.Diſk.DisK@Example.com", "dısk.diſk.disK@example.com"),
        (None, None),
        ("", ""),
    ],
)
def test_migration_normalizes_users(stored, expected):
    """Normalize legacy rows while preserving the separate admin login email."""
    user = factories.UserFactory(admin_email="Admin@Example.COM")
    models.User.objects.filter(pk=user.pk).update(email=stored)

    _run_migration()

    user.refresh_from_db()
    assert user.email == expected
    assert user.admin_email == "Admin@Example.COM"


def test_migration_retains_duplicate_users():
    """Users whose addresses become identical remain separate accounts."""
    users = [factories.UserFactory(), factories.UserFactory()]
    for user, email in zip(
        users, ["Disk@Example.com", "disk@example.com"], strict=True
    ):
        models.User.objects.filter(pk=user.pk).update(email=email)

    _run_migration()

    assert set(
        models.User.objects.filter(email="disk@example.com").values_list(
            "pk", flat=True
        )
    ) == {user.pk for user in users}


def test_migration_normalizes_bypasses_and_preserves_grants():
    """Normalization keeps bypass flags, expiry and Unicode characters intact."""
    expiry = timezone.now() + timedelta(days=1)
    entry = models.AccessBypassEmail.objects.create(
        email="other@example.com",
        is_active=False,
        note="manual grant",
        expires_at=expiry,
    )
    models.AccessBypassEmail.objects.filter(pk=entry.pk).update(
        email=" DisK@Example.COM "
    )

    _run_migration()
    _run_migration()

    entry.refresh_from_db()
    assert entry.email == "disK@example.com"
    assert entry.is_active is False
    assert entry.note == "manual grant"
    assert entry.expires_at == expiry
    assert models.AccessBypassEmail.objects.count() == 1


def test_migration_rejects_bypass_collisions_before_updating():
    """A collision requires manual resolution and cannot silently combine grants."""
    user = factories.UserFactory()
    models.User.objects.filter(pk=user.pk).update(email="User@Example.com")
    existing = models.AccessBypassEmail.objects.create(email="disk@example.com")
    conflicting = models.AccessBypassEmail.objects.create(
        email="other@example.com", is_active=False
    )
    models.AccessBypassEmail.objects.filter(pk=conflicting.pk).update(
        email=" DISK@Example.com "
    )

    with pytest.raises(
        RuntimeError, match="Resolve conflicting AccessBypassEmail"
    ) as error:
        _run_migration()

    assert str(existing.pk) in str(error.value)
    assert str(conflicting.pk) in str(error.value)
    assert "disk@" not in str(error.value).lower()
    user.refresh_from_db()
    conflicting.refresh_from_db()
    assert user.email == "User@Example.com"
    assert conflicting.email == " DISK@Example.com "


def test_migration_updates_in_bounded_batches(monkeypatch):
    """Flush each batch so the migration does not retain every changed user."""
    for index in range(3):
        user = factories.UserFactory()
        models.User.objects.filter(pk=user.pk).update(email=f"User{index}@Example.com")
    monkeypatch.setattr(migration, "BATCH_SIZE", 2)

    with CaptureQueriesContext(connection) as queries:
        _run_migration()

    updates = [
        query
        for query in queries
        if query["sql"].startswith('UPDATE "dictaphone_user"')
    ]
    assert len(updates) == 2
    assert set(models.User.objects.values_list("email", flat=True)) == {
        f"user{index}@example.com" for index in range(3)
    }
