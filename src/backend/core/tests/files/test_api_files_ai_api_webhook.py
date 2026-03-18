"""
Tests for files API endpoint in dictaphone's core app: create
"""

import logging
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from django.utils import timezone

import pytest
from freezegun import freeze_time
from rest_framework import status
from rest_framework.test import APIClient

from core import factories
from core.models import File, FileTypeChoices, FileUploadStateChoices

pytestmark = pytest.mark.django_db


def test_api_files_transcribe_webhook_anonymous(caplog):
    """Anonymous users should not be allowed to call webhook."""
    with caplog.at_level(logging.WARNING):
        response = APIClient().post(
            "/api/v1.0/files/ai-webhook/",
            {},
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    assert "Bad Authorization header (ip:" in caplog.text


def test_api_files_transcribe_webhook_authenticated(settings):
    """Calls to the webhook with a proper API key should be accepted"""

    settings.AI_WEBHOOK_API_KEY = "good-key"
    response = APIClient().post(
        "/api/v1.0/files/ai-webhook/",
        {},
        headers={"Authorization": "Bearer good-key"},
    )

    assert response.status_code == status.HTTP_200_OK
