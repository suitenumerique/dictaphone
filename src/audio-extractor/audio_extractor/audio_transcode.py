"""Audio conversion and output validation."""

import json
import math
from pathlib import Path

from audio_extractor.utils import ProcessingError, _run


def _convert(
    source: Path,
    destination: Path,
    timeout: float,
    *,
    output_sample_rate: int = 16000,
    output_bitrate: str = "64k",
) -> float:
    """Convert the first audio stream using configured output parameters."""
    command = [
        "ffmpeg",  # Media converter.
        "-nostdin",  # Never wait for interactive input.
        "-hide_banner",  # Keep logs focused on actionable errors.
        "-loglevel",  # Limit FFmpeg output volume.
        "error",  # Report errors only; stderr is captured on failure.
        "-fflags",
        "+discardcorrupt+genpts",  # Discard corrupt packets & generate missing PTS
        "-err_detect",  # Ignore errors if possible.
        "ignore_err",
        "-i",  # Specify the downloaded source file.
        str(source),  # Source media path.
        "-map_metadata",  # Remove metadata.
        "-1",  # Disable metadata mapping.
        "-map_chapters",  # Remove chapters.
        "-1",  # Disable chapter mapping.
        "-map",  # Select the first audio stream explicitly.
        "0:a:0",  # Ignore video and additional audio streams.
        "-vn",  # Do not write a video stream.
        "-c:a",  # Select the audio encoder.
        "libopus",  # Encode to the OGG Opus format.
        "-ac",  # Downmix all channels to mono.
        "1",  # Use a single audio channel.
        "-b:a",  # Set the target audio bitrate.
        output_bitrate,  # Use the configured bitrate.
        "-vbr",  # Enable variable bitrate encoding.
        "on",  # Let Opus allocate bits where they are most useful.
        "-application",  # Tune Opus for the intended workload.
        "audio",  # Use the full-quality audio application mode.
        "-af",  # Rebuild timestamps from decoded audio samples.
        "asetpts=N/SR/TB",  # Prevent non-monotonic timestamps in the OGG muxer.
        "-ar",  # Set the output sample rate.
        str(output_sample_rate),  # Use the configured sample rate.
        "-f",  # Force a stable output container.
        "ogg",  # Use the configured output format.
        "-y",  # Replace a temporary output if it already exists.
        str(destination),  # Output media path.
    ]
    _run(command, timeout)
    if not destination.is_file() or destination.stat().st_size == 0:
        raise ProcessingError("FFmpeg produced no audio output")
    metadata = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_type,codec_name,channels,sample_rate:format=duration",
            "-of",
            "json",
            str(destination),
        ],
        timeout,
        capture_output=True,
    )
    try:
        data = json.loads(metadata)
        stream = data["streams"][0]
        duration = float(data["format"]["duration"])
        valid = (
            stream.get("codec_type") == "audio"
            and stream.get("codec_name") == "opus"
            and int(stream["channels"]) == 1
            and int(stream["sample_rate"]) in {8000, 12000, 16000, 24000, 48000}
            and math.isfinite(duration)
            and duration > 0
        )
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ProcessingError("FFmpeg output has invalid audio metadata") from exc
    if not valid:
        raise ProcessingError("FFmpeg output is not a valid audio stream")
    return duration
