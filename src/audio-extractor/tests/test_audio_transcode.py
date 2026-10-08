"""Audio transcoding tests."""

import shutil
from pathlib import Path
from unittest.mock import Mock, patch

import pytest

from audio_extractor.audio_transcode import _convert
from audio_extractor.utils import ProcessingError


def test_convert_uses_configured_ffmpeg_options_and_probes_output(tmp_path):
    output = tmp_path / "audio.ogg"

    def command(command, **kwargs):
        if command[0] == "ffmpeg":
            Path(command[-1]).write_bytes(b"ogg")
            return Mock(stdout="")
        return Mock(
            stdout=(
                '{"streams":[{"codec_type":"audio","codec_name":"opus",'
                '"channels":1,"sample_rate":"48000"}],'
                '"format":{"duration":"8.25"}}'
            )
        )

    with patch(
        "audio_extractor.utils.subprocess.run", side_effect=command
    ) as run_command:
        duration = _convert(
            tmp_path / "source.webm",
            output,
            60,
            output_sample_rate=24000,
            output_bitrate="96k",
        )

    assert duration == 8.25
    assert run_command.call_args_list[0].kwargs["timeout"] == 60
    ffmpeg = run_command.call_args_list[0].args[0]
    assert ffmpeg[ffmpeg.index("-ac") + 1] == "1"
    assert ffmpeg[ffmpeg.index("-ar") + 1] == "24000"
    assert ffmpeg[ffmpeg.index("-b:a") + 1] == "96k"
    assert ffmpeg[ffmpeg.index("-map") + 1] == "0:a:0"
    assert ffmpeg[ffmpeg.index("-f") + 1] == "ogg"


def test_convert_rejects_invalid_output_metadata(tmp_path):
    output = tmp_path / "audio.ogg"

    def command(command, **kwargs):
        if command[0] == "ffmpeg":
            Path(command[-1]).write_bytes(b"ogg")
            return Mock(stdout="")
        return Mock(stdout='{"streams":[], "format":{"duration":"0"}}')

    with (
        patch("audio_extractor.utils.subprocess.run", side_effect=command),
        pytest.raises(ProcessingError, match="invalid audio metadata"),
    ):
        _convert(tmp_path / "source.webm", output, 60)


REAL_MEDIA_SAMPLES = [
    ("audio-sample-android-chrome.webm", 2.346),
    ("audio-sample-android-firefox.ogg", 2.3025),
    ("audio-sample-android.m4a", 1.38),
    ("audio-sample-chromium.webm", 2.7165),
    ("audio-sample-firefox.ogg", 2.0865),
    ("audio-sample-ios-browser.webm", 2.6229),
    ("audio-sample-ios.m4a", 1.3705),
    ("audio-sample-mac-os-safari.webm", 2.3049),
    ("video-sample-visio.mp4", 5.34059),
]


@pytest.mark.parametrize(("asset_name", "expected_duration"), REAL_MEDIA_SAMPLES)
def test_real_media_samples_convert_to_ogg_opus(
    asset_name, expected_duration, tmp_path
):
    """Recordings from browsers and a video convert with their expected duration."""
    source = Path(__file__).parent / "assets" / asset_name
    output = tmp_path / "audio.ogg"

    duration = _convert(source, output, 60)

    assert duration == pytest.approx(expected_duration, abs=0.02)
    assert output.read_bytes().startswith(b"OggS")


def test_corrupted_media_fails_conversion(tmp_path):
    """Malformed input fails instead of producing valid output."""
    source = Path(__file__).parent / "assets/audio-sample-corrupted.m4a"
    with pytest.raises(ProcessingError):
        _convert(source, tmp_path / "audio.ogg", 60)


def test_video_without_audio_fails_conversion(tmp_path):
    """A video container without an audio stream cannot be extracted."""
    source = Path(__file__).parent / "assets/video-with-no-audio.mp4"
    with pytest.raises(ProcessingError):
        _convert(source, tmp_path / "audio.ogg", 60)
