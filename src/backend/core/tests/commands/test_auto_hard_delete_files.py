"""Tests for auto_hard_delete_files management command."""

from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.files.storage import default_storage
from django.core.management import call_command
from django.utils import timezone

import pytest

from core import factories, models
from core.tasks.file import process_file_deletion

pytestmark = pytest.mark.django_db


@pytest.mark.django_db(transaction=True)
def test_auto_hard_delete_files_success(settings):
    """Command should mark pending and hard delete only files past grace period."""
    settings.FILE_AUTO_HARD_DELETE_AFTER_DAYS = 10
    settings.FILE_AUTO_HARD_DELETE_AFTER_GRACE_PERIOD_DAYS = 2
    now = timezone.now()

    recent_file = factories.FileFactory(upload_bytes=b"recent")
    pending_file = factories.FileFactory(upload_bytes=b"pending")
    delete_file = factories.FileFactory(upload_bytes=b"delete")

    models.File.objects.filter(pk=recent_file.pk).update(
        created_at=now - timedelta(days=9)
    )
    models.File.objects.filter(pk=pending_file.pk).update(
        created_at=now - timedelta(days=11)
    )
    models.File.objects.filter(pk=delete_file.pk).update(
        created_at=now - timedelta(days=13)
    )

    out = StringIO()
    with patch(
        "core.management.commands.auto_hard_delete_files.process_file_deletion.delay",
        side_effect=process_file_deletion,
    ):
        call_command("auto_hard_delete_files", stdout=out)

    recent_file.refresh_from_db()
    pending_file.refresh_from_db()

    assert (
        out.getvalue().strip()
        == "Marked 2 file(s) pending auto hard delete, queued hard deletion for 1 file(s)."
    )
    assert recent_file.lifecycle_state == models.FileLifecycleStateChoices.ACTIVE
    assert pending_file.lifecycle_state == (
        models.FileLifecycleStateChoices.PENDING_AUTO_HARD_DELETE
    )
    assert models.File.objects.filter(id=delete_file.id).exists() is False

    assert default_storage.exists(recent_file.file_key)
    assert default_storage.exists(pending_file.file_key)
    assert not default_storage.exists(delete_file.file_key)


@pytest.mark.django_db(transaction=True)
def test_auto_hard_delete_files_ignores_already_hard_deleted(settings):
    """Already hard-deleted files should not be enqueued again."""
    settings.FILE_AUTO_HARD_DELETE_AFTER_DAYS = 10
    settings.FILE_AUTO_HARD_DELETE_AFTER_GRACE_PERIOD_DAYS = 2
    now = timezone.now()

    file = factories.FileFactory(upload_bytes=b"hard-deleted")
    file.soft_delete()
    file.hard_delete()
    models.File.objects.filter(pk=file.pk).update(created_at=now - timedelta(days=20))

    out = StringIO()
    with patch(
        "core.management.commands.auto_hard_delete_files.process_file_deletion.delay",
        side_effect=process_file_deletion,
    ) as mock_delay:
        call_command("auto_hard_delete_files", stdout=out)

    file.refresh_from_db()
    assert file.hard_deleted_at is not None
    assert file.lifecycle_state == models.FileLifecycleStateChoices.ACTIVE
    assert mock_delay.call_count == 0
    assert out.getvalue().strip().endswith("queued hard deletion for 0 file(s).")
