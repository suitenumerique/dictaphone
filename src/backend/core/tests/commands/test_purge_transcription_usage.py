"""Retention cleanup for the durable transcription usage ledger."""

from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

import pytest
from freezegun import freeze_time

from core import factories, models

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("ignored", [False, True])
@freeze_time("2026-10-19 12:00:00")
def test_purge_transcription_usage_default_retention(ignored, settings):
    """Keep a full year based on submission time, including ignored usage history."""
    assert settings.TRANSCRIPTION_USAGE_RETENTION_DAYS == 365
    cutoff = timezone.now() - timedelta(days=365)
    expired = factories.TranscriptionUsageFactory(
        submitted_at=cutoff - timedelta(seconds=1), ignored=ignored
    )
    retained = [
        factories.TranscriptionUsageFactory(submitted_at=timestamp, ignored=ignored)
        for timestamp in (cutoff, cutoff + timedelta(seconds=1), timezone.now())
    ]
    output = StringIO()

    call_command("purge_transcription_usage", stdout=output)

    assert not models.TranscriptionUsage.objects.filter(pk=expired.pk).exists()
    assert set(models.TranscriptionUsage.objects.values_list("pk", flat=True)) == {
        usage.pk for usage in retained
    }
    assert "Purged 1 transcription usage record(s)." in output.getvalue()


@freeze_time("2026-10-19 12:00:00")
def test_purge_transcription_usage_custom_retention_and_batches(settings):
    """A shorter retention removes all expired batches and keeps the quota window."""
    settings.TRANSCRIPTION_USAGE_RETENTION_DAYS = 1
    cutoff = timezone.now() - timedelta(days=1)
    factories.TranscriptionUsageFactory.create_batch(
        5, submitted_at=cutoff - timedelta(seconds=1)
    )
    recent = factories.TranscriptionUsageFactory(submitted_at=cutoff)
    output = StringIO()

    call_command("purge_transcription_usage", batch_size=2, stdout=output)

    assert list(models.TranscriptionUsage.objects.values_list("pk", flat=True)) == [
        recent.pk
    ]
    assert "Purged 5 transcription usage record(s)." in output.getvalue()
    # Repeated executions are harmless once all expired rows have been purged.
    output = StringIO()
    call_command("purge_transcription_usage", stdout=output)
    assert "Purged 0 transcription usage record(s)." in output.getvalue()


@pytest.mark.parametrize("days", [0, -1])
def test_purge_transcription_usage_rejects_unsafe_retention(settings, days):
    """Misconfiguration must not remove usage still needed to enforce quota."""
    settings.TRANSCRIPTION_USAGE_RETENTION_DAYS = days
    usage = factories.TranscriptionUsageFactory()
    with pytest.raises(CommandError, match="RETENTION_DAYS must be at least 1"):
        call_command("purge_transcription_usage")
    assert models.TranscriptionUsage.objects.filter(pk=usage.pk).exists()


@pytest.mark.parametrize("batch_size", [0, -1])
def test_purge_transcription_usage_rejects_invalid_batch_size(batch_size):
    """Reject batch sizes that would prevent cleanup from progressing."""
    with pytest.raises(CommandError, match="--batch-size must be at least 1"):
        call_command("purge_transcription_usage", batch_size=batch_size)
