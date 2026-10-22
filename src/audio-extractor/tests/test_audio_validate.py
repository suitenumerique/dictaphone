"""Independent Opus validation tests."""

from pathlib import Path
from unittest.mock import patch

import pytest

from audio_extractor.audio_transcode import _convert
from audio_extractor.audio_validate import _validate_opus
from audio_extractor.utils import ProcessingError


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


@pytest.mark.parametrize("output_sample_rate", [8000, 12000, 16000, 24000, 48000])
def test_16khz_mp3_timestamps_pass_validation(tmp_path, output_sample_rate):
    """Sample timestamps stay exact beyond the first granule rounding failure."""
    sample = Path(__file__).parent / "assets/audio-sample-16khz.mp3"
    source = tmp_path / "repeated.mp3"
    # Silent original frames from 16:55.524 to 16:57.540 (peak below -78 dBFS).
    # Repeat ~2 seconds of raw MP3 frames to reach the failure at ~31 seconds.
    source.write_bytes(sample.read_bytes() * 21)
    output = tmp_path / "audio.ogg"

    duration = _convert(source, output, 60, output_sample_rate=output_sample_rate)

    assert duration == pytest.approx(42.336, abs=0.02)
    _validate_opus(output, 60)


def test_non_audio_file_reports_actual_opusinfo_output():
    """Validating Python source preserves opusinfo's actual diagnostics."""
    source = Path(__file__)

    with pytest.raises(ProcessingError) as error:
        _validate_opus(source, 60)

    message = str(error.value)
    assert "opusinfo exited with status 1" in message
    assert f'Processing file "{source}"...' in message
    assert f'ERROR: No Ogg data found in file "{source}".' in message
    assert "Input probably not Ogg." in message
