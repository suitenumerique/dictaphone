"""Tests for delete_original_file_data management command."""

from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.core.files.storage import default_storage
from django.core.management import call_command
from django.utils import timezone

import pytest

from core import factories, models
from core.tasks.file import process_original_file_data_deletion

pytestmark = pytest.mark.django_db


@pytest.mark.django_db(transaction=True)
def test_delete_original_files_data_success(settings):
    """Command should mark pending and delete only files past grace period."""
    settings.ORIGINAL_FILE_DATA_DELETE_AFTER_DAYS = 10
    settings.ORIGINAL_FILE_DATA_DELETE_AFTER_GRACE_PERIOD_DAYS = 2
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
        "core.management.commands.delete_original_files_data.process_original_file_data_deletion.delay",  # pylint:disable=line-too-long
        side_effect=process_original_file_data_deletion,
    ):
        call_command("delete_original_files_data", stdout=out)

    recent_file.refresh_from_db()
    pending_file.refresh_from_db()
    delete_file.refresh_from_db()

    assert (
        out.getvalue().strip()
        == "Marked 2 file(s) pending original data deletion, queued deletion for 1 file(s)."
    )
    assert recent_file.lifecycle_state == models.FileLifecycleStateChoices.ACTIVE
    assert pending_file.lifecycle_state == (
        models.FileLifecycleStateChoices.PENDING_ORIGINAL_DATA_DELETION
    )
    assert delete_file.lifecycle_state == (
        models.FileLifecycleStateChoices.ORIGINAL_DATA_DELETED
    )

    assert default_storage.exists(recent_file.file_key)
    assert default_storage.exists(pending_file.file_key)
    assert not default_storage.exists(delete_file.file_key)


@pytest.mark.django_db(transaction=True)
def test_delete_original_files_data_ignores_hard_deleted_files(settings):
    """Hard-deleted files should not be touched by the command."""
    settings.ORIGINAL_FILE_DATA_DELETE_AFTER_DAYS = 10
    settings.ORIGINAL_FILE_DATA_DELETE_AFTER_GRACE_PERIOD_DAYS = 2
    now = timezone.now()

    file = factories.FileFactory(upload_bytes=b"hard-deleted")
    file.soft_delete()
    file.hard_delete()
    models.File.objects.filter(pk=file.pk).update(created_at=now - timedelta(days=20))

    out = StringIO()
    with patch(
        "core.management.commands.delete_original_files_data.process_original_file_data_deletion.delay",  # pylint:disable=line-too-long
        side_effect=process_original_file_data_deletion,
    ) as mock_delay:
        call_command("delete_original_files_data", stdout=out)

    file.refresh_from_db()
    assert file.lifecycle_state == models.FileLifecycleStateChoices.ACTIVE
    assert mock_delay.call_count == 0
    assert out.getvalue().strip().endswith("queued deletion for 0 file(s).")
