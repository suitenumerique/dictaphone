"""Tests for email notification tasks."""

# Django adds ``mail.outbox`` when the locmem email backend is active in tests.
# pylint: disable=no-member

from django.core import mail

import pytest

from core import factories
from core.models import AiJobStatusChoices, AiJobTypeChoices
from core.tasks.mail import send_transcription_ready_email

pytestmark = pytest.mark.django_db


def test_send_transcription_ready_email_success(settings):
    """A successful transcript sends a localized email to its creator."""
    settings.EMAIL_APP_BASE_URL = "https://dictaphone.example.com/"
    settings.EMAIL_BRAND_NAME = "Dictaphone"
    settings.EMAIL_LOGO_IMG = "https://example.com/logo.png"
    settings.EMAIL_SUPPORT_EMAIL = "support@example.com"
    job = factories.AiFileJobFactory(
        type=AiJobTypeChoices.TRANSCRIPT,
        status=AiJobStatusChoices.SUCCESS,
        file__title="Team meeting",
    )

    send_transcription_ready_email(job.id)

    assert len(mail.outbox) == 1
    email = mail.outbox[0]
    assert email.to == [job.file.creator.email]
    assert email.subject == "Your transcription is ready"
    assert "Team meeting" in email.body
    assert f"https://dictaphone.example.com/recordings/{job.file_id}" in email.body
    assert email.alternatives[0][1] == "text/html"


def test_send_transcription_ready_email_skips_non_successful_job():
    """Pending and failed jobs must not send notifications."""
    job = factories.AiFileJobFactory(
        type=AiJobTypeChoices.TRANSCRIPT,
        status=AiJobStatusChoices.PENDING,
    )

    send_transcription_ready_email(job.id)

    assert not mail.outbox


def test_send_transcription_ready_email_skips_creator_without_email():
    """A user without an email address must not cause a send attempt."""
    job = factories.AiFileJobFactory(
        type=AiJobTypeChoices.TRANSCRIPT,
        status=AiJobStatusChoices.SUCCESS,
        file__creator__email=None,
    )

    send_transcription_ready_email(job.id)

    assert not mail.outbox
