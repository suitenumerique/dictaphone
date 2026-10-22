"""Unit tests for AiFileJob model."""

# pylint: disable=C0301
# pylint: disable=C0303
from io import BytesIO

from django.core.files.storage import default_storage

import pytest

from core import factories
from core.models import (
    AiFileJob,
    AiJobFailureReasonChoices,
    AiJobStatusChoices,
    AiJobTypeChoices,
)

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("reason", AiJobFailureReasonChoices.values)
def test_models_ai_job_failure_reason_choices(reason):
    """Each explicit failure choice is persisted with the failed status."""
    job = factories.AiFileJobFactory(status=AiJobStatusChoices.PENDING)

    job.mark_failed(reason)

    job.refresh_from_db()
    assert job.status == AiJobStatusChoices.FAILED
    assert job.failure_reason == reason
    job.full_clean()


def test_models_ai_job_failure_defaults_to_unknown():
    """Unclassified failures use the public unknown failure choice."""
    job = factories.AiFileJobFactory(status=AiJobStatusChoices.PENDING)

    job.mark_failed()

    job.refresh_from_db()
    assert job.failure_reason == AiJobFailureReasonChoices.UNKNOWN_FAILURE


def test_models_ai_job_failure_rejects_unrecognized_reason():
    """Service error strings cannot be persisted as public failure reasons."""
    job = factories.AiFileJobFactory(status=AiJobStatusChoices.PENDING)

    with pytest.raises(ValueError):
        job.mark_failed("arbitrary_error")

    job.refresh_from_db()
    assert job.status == AiJobStatusChoices.PENDING
    assert job.failure_reason == ""


def test_models_ai_job_to_markdown_transcript_formats_whisperx_response():
    """Transcript markdown should group contiguous segments by speaker."""
    ai_job = factories.AiFileJobFactory(
        type=AiJobTypeChoices.TRANSCRIPT,
        status=AiJobStatusChoices.SUCCESS,
    )
    default_storage.save(
        ai_job.key,
        BytesIO(
            (
                b'{"segments": ['
                b'{"start": 0.0, "end": 1.0, "text": "Hello.", "words": [], "speaker": "SPEAKER_00"},'
                b'{"start": 1.0, "end": 2.0, "text": "How are you?", "words": [], "speaker": "SPEAKER_00"},'
                b'{"start": 2.0, "end": 3.0, "text": "Fine, thanks.", "words": [], "speaker": "SPEAKER_01"},'
                b'{"start": 3.0, "end": 4.0, "text": "And you?", "words": [], "speaker": "SPEAKER_01"},'
                b'{"start": 4.0, "end": 5.0, "text": "Great.", "words": [], "speaker": "SPEAKER_00"}'
                b'], "word_segments": []}'
            )
        ),
    )

    assert (
        ai_job.to_markdown("fr")
        == """# Transcript

**00:00 · Participant 1** Hello. How are you?

**00:02 · Participant 2** Fine, thanks. And you?

**00:04 · Participant 1** Great."""
    )


def test_models_ai_job_to_markdown_summary_formats_content():
    """Summary markdown should include header then raw summary content."""
    ai_job = factories.AiFileJobFactory(
        type=AiJobTypeChoices.SUMMARIZE,
        status=AiJobStatusChoices.SUCCESS,
    )
    default_storage.save(ai_job.key, BytesIO(b"Summary content"))

    assert ai_job.to_markdown("fr") == "# Résumé \n \n Summary content"


def test_models_ai_job_delete_removes_storage_file():
    """Deleting an AI job should also remove its file from storage."""
    ai_job = factories.AiFileJobFactory(type=AiJobTypeChoices.SUMMARIZE)
    default_storage.save(ai_job.key, BytesIO(b"Summary content"))

    assert default_storage.exists(ai_job.key)
    ai_job.delete()

    assert not AiFileJob.objects.filter(id=ai_job.id).exists()
    assert not default_storage.exists(ai_job.key)
