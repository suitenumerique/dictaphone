"""Tests for admin classes."""

from unittest.mock import Mock, patch

from django.contrib import messages

import pytest

from core import factories
from core.admin import FileAdmin
from core.models import File

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
