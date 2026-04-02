"""Unit tests for AiFileJob model."""

# pylint: disable=C0301
# pylint: disable=C0303
from io import BytesIO

from django.core.files.storage import default_storage

import pytest

from core import factories
from core.models import AiJobStatusChoices, AiJobTypeChoices

pytestmark = pytest.mark.django_db


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
        ai_job.to_markdown()
        == """# Transcription 

## SPEAKER_00
Hello.
How are you?

## SPEAKER_01
Fine, thanks.
And you?

## SPEAKER_00
Great.
"""
    )


def test_models_ai_job_to_markdown_summary_formats_content():
    """Summary markdown should include header then raw summary content."""
    ai_job = factories.AiFileJobFactory(
        type=AiJobTypeChoices.SUMMARIZE,
        status=AiJobStatusChoices.SUCCESS,
    )
    default_storage.save(ai_job.key, BytesIO(b"Summary content"))

    assert ai_job.to_markdown() == "# Résumé \n \n Summary content"
