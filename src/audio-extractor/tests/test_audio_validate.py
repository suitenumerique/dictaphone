"""Independent Opus validation tests."""

from pathlib import Path
from unittest.mock import patch

from audio_extractor.audio_transcode import _convert
from audio_extractor.audio_validate import _validate_opus


def test_opus_validation_uses_both_independent_tools(tmp_path):
    """Validation invokes opusinfo and decodes the complete stream."""
    source = tmp_path / "audio.ogg"
    source.touch()
    with patch("audio_extractor.audio_validate._run") as run_command:
        _validate_opus(source, 42)

    assert [call.args[0][0] for call in run_command.call_args_list] == [
        "opusinfo",
        "opusdec",
    ]
    assert run_command.call_args_list[1].args[0][-1] == "/dev/null"
    assert all(call.args[1] == 42 for call in run_command.call_args_list)


def test_converted_fixture_passes_independent_opus_validation(tmp_path):
    """The separate Opus tools can parse and decode FFmpeg output."""
    source = Path(__file__).parent / "assets/audio-sample-chromium.webm"
    output = tmp_path / "audio.ogg"

    _convert(source, output, 60)
    _validate_opus(output, 60)
