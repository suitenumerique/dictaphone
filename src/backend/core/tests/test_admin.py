"""Tests for admin classes."""

from io import BytesIO
from unittest.mock import Mock, patch

from django.contrib import messages
from django.core.files.storage import default_storage

import pytest

from core import factories
from core.admin import AiFileJobAdmin, FileAdmin
from core.models import AiFileJob, AiJobTypeChoices, File

pytestmark = pytest.mark.django_db


@patch("core.admin.call_transcribe_service.delay")
def test_admin_action_retry_transcript_generation_on_files(mock_delay):
    """Admin action should enqueue transcript retries for selected files."""
    file1 = factories.FileFactory()
    file2 = factories.FileFactory()

    admin_instance = FileAdmin(File, Mock())
    admin_instance.message_user = Mock()
    request = Mock()
    request.POST = {"language": "en"}
    queryset = File.objects.filter(id__in=[file1.id, file2.id])

    admin_instance.retry_transcript_generation(request, queryset)

    assert mock_delay.call_count == 2
    mock_delay.assert_any_call(file1.id, language="en")
    mock_delay.assert_any_call(file2.id, language="en")
    admin_instance.message_user.assert_called_once()


@patch("core.admin.call_transcribe_service.delay")
def test_admin_action_retry_transcript_generation_invalid_language(mock_delay):
    """Admin action should reject invalid language values."""
    file = factories.FileFactory()

    admin_instance = FileAdmin(File, Mock())
    admin_instance.message_user = Mock()
    request = Mock()
    request.POST = {"language": "zzz"}
    queryset = File.objects.filter(id=file.id)

    admin_instance.retry_transcript_generation(request, queryset)

    mock_delay.assert_not_called()
    admin_instance.message_user.assert_called_once_with(
        request,
        "Invalid language selected.",
        level=messages.ERROR,
    )


def test_admin_ai_file_job_delete_model_removes_storage_file():
    """Single AI job deletion in admin should remove storage object."""
    ai_job = factories.AiFileJobFactory(type=AiJobTypeChoices.SUMMARIZE)
    default_storage.save(ai_job.key, BytesIO(b"summary"))

    admin_instance = AiFileJobAdmin(AiFileJob, Mock())

    assert default_storage.exists(ai_job.key)
    admin_instance.delete_model(request=Mock(), obj=ai_job)

    assert not AiFileJob.objects.filter(id=ai_job.id).exists()
    assert not default_storage.exists(ai_job.key)


@pytest.mark.django_db(transaction=True)
def test_admin_ai_file_job_delete_queryset_removes_storage_files():
    """Bulk AI job deletion in admin should remove all storage objects."""
    ai_job_1 = factories.AiFileJobFactory(type=AiJobTypeChoices.TRANSCRIPT)
    ai_job_2 = factories.AiFileJobFactory(type=AiJobTypeChoices.SUMMARIZE)
    default_storage.save(ai_job_1.key, BytesIO(b'{"segments": []}'))
    default_storage.save(ai_job_2.key, BytesIO(b"summary"))

    admin_instance = AiFileJobAdmin(AiFileJob, Mock())
    queryset = AiFileJob.objects.filter(id__in=[ai_job_1.id, ai_job_2.id])

    assert default_storage.exists(ai_job_1.key)
    assert default_storage.exists(ai_job_2.key)
    admin_instance.delete_queryset(request=Mock(), queryset=queryset)

    assert not AiFileJob.objects.filter(id=ai_job_1.id).exists()
    assert not AiFileJob.objects.filter(id=ai_job_2.id).exists()
    assert not default_storage.exists(ai_job_1.key)
    assert not default_storage.exists(ai_job_2.key)
