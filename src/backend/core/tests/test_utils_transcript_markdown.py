"""Tests for transcript paragraph formatting in Docs exports."""

import pytest

from core.utils import format_transcript_for_markdown
from core.webhook_models import WhisperXResponse


def make_transcript(segments):
    """Build a response from compact segment fixtures."""
    return WhisperXResponse(
        segments=[
            {"start": start, "end": end, "speaker": speaker, "text": text, "words": []}
            for start, end, speaker, text in segments
        ],
        word_segments=[],
    )


@pytest.mark.parametrize(
    "language, label", [("en", "Speaker"), ("fr-FR", "Participant")]
)
def test_markdown_groups_by_speaker_and_sixty_second_span(language, label):
    """Match client grouping, including the inclusive limit and paragraph reset."""
    transcript = make_transcript(
        [
            (10, 30, "SPEAKER_42", " Hello. "),
            (30, 70, "SPEAKER_42", " Still speaking. "),
            (70, 71, "SPEAKER_42", "A new paragraph."),
            (71, 130, "SPEAKER_42", "At the next limit."),
            (130, 131, "SPEAKER_42", "Another paragraph."),
            (131, 132, "SPEAKER_09", "Another speaker."),
            (132, 133, "SPEAKER_42", "Back again."),
        ]
    )

    assert format_transcript_for_markdown(transcript, language) == (
        "# Transcript\n\n"
        f"**00:10 · {label} 1** Hello. Still speaking.\n\n"
        f"**01:10 · {label} 1** A new paragraph. At the next limit.\n\n"
        f"**02:10 · {label} 1** Another paragraph.\n\n"
        f"**02:11 · {label} 2** Another speaker.\n\n"
        f"**02:12 · {label} 1** Back again."
    )


@pytest.mark.parametrize(
    "segments, expected",
    [
        ([], "# Transcript"),
        (
            [(0, 90, "a", "One long segment."), (90, 91, "a", "Next.")],
            "# Transcript\n\n**00:00 · Speaker 1** One long segment."
            "\n\n**01:30 · Speaker 1** Next.",
        ),
        (
            [(None, None, None, "Hello."), (None, None, None, "Again.")],
            "# Transcript\n\n**00:00 · Speaker 1** Hello. Again.",
        ),
        (
            [
                (0, 1, "a", "First."),
                (60, None, "a", "At limit."),
                (61, None, "a", "Over limit."),
            ],
            "# Transcript\n\n**00:00 · Speaker 1** First. At limit."
            "\n\n**01:01 · Speaker 1** Over limit.",
        ),
        (
            [(3661.9, 3662, "a", "An hour later.")],
            "# Transcript\n\n**01:01:01 · Speaker 1** An hour later.",
        ),
    ],
)
def test_markdown_handles_timing_edge_cases(segments, expected):
    """Keep segments intact and use client timing fallbacks for missing values."""
    assert format_transcript_for_markdown(make_transcript(segments)) == expected
