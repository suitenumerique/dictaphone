"""Resource-conscious audio extraction helpers."""

import json
import math
import shutil
import subprocess
import tempfile
from pathlib import Path

from django.conf import settings

from core.storage import get_storage_bucket_name, get_storage_for_file


class AudioExtractionError(RuntimeError):
    """Raised when a source cannot be converted to a valid audio file."""


class AudioExtractionRetryableError(AudioExtractionError):
    """Raised when extraction failed for a transient infrastructure reason."""


class NoAudioStreamError(AudioExtractionError):
    """Raised when a source media file does not contain an audio stream."""


def _run_checked(
    command: list[str], *, capture_stdout: bool = False
) -> subprocess.CompletedProcess[str]:
    """Run a bounded-output media command and turn failures into domain errors."""
    try:
        return subprocess.run(  # noqa: S603 - commands are built internally
            command,
            check=True,
            stdout=subprocess.PIPE if capture_stdout else subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=settings.MEDIA_COMMAND_TIMEOUT_SECONDS,
        )
    except (FileNotFoundError, OSError) as exc:
        raise AudioExtractionRetryableError(
            "The media processing binary is unavailable"
        ) from exc
    except subprocess.CalledProcessError as exc:
        details = (exc.stderr or "").strip()
        raise AudioExtractionError(
            f"Media processing failed{f': {details}' if details else ''}"
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise AudioExtractionError("Media processing timed out") from exc


def _probe_output(  # pylint: disable=too-many-boolean-expressions
    output_path: Path,
) -> float:
    """Verify the converted output and return its duration."""
    result = _run_checked(
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
            str(output_path),
        ],
        capture_stdout=True,
    )

    try:
        data = json.loads(result.stdout or "{}")
        stream = data["streams"][0]
        duration = float(data["format"]["duration"])
        channels = int(stream["channels"])
        sample_rate = int(stream["sample_rate"])
    except (
        AttributeError,
        KeyError,
        IndexError,
        TypeError,
        ValueError,
        json.JSONDecodeError,
    ) as exc:
        raise AudioExtractionError("The converted audio has invalid metadata") from exc

    if (
        stream.get("codec_name") != "opus"
        or stream.get("codec_type") != "audio"
        or channels != 1
        # Opus streams may report their decoder rate (48 kHz) even when the
        # input was resampled to 16 kHz before encoding.
        or sample_rate not in {8000, 12000, 16000, 24000, 48000}
        or not math.isfinite(duration)
        or duration <= 0
    ):
        raise AudioExtractionError("The converted audio is not a valid Opus stream")

    return duration


def _ensure_audio_stream(source_path: Path) -> None:
    """Reject valid media files that have no audio stream to extract."""
    result = _run_checked(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream=codec_type",
            "-of",
            "json",
            str(source_path),
        ],
        capture_stdout=True,
    )

    try:
        streams = json.loads(result.stdout or "{}").get("streams", [])
    except (AttributeError, TypeError, json.JSONDecodeError) as exc:
        raise AudioExtractionError("The source media has invalid metadata") from exc

    if not any(stream.get("codec_type") == "audio" for stream in streams):
        raise NoAudioStreamError("The source media contains no audio streams")


def extract_audio_to_storage(file) -> float:
    """Convert a stored source file to validated OGG Opus without buffering it in RAM."""
    source_suffix = f".{file.extension}" if file.extension else ""
    storage = get_storage_for_file(file)

    with tempfile.TemporaryDirectory(prefix="dictaphone-audio-") as directory:
        directory_path = Path(directory)
        source_path = directory_path / f"source{source_suffix}"
        output_path = directory_path / "audio.ogg"

        try:
            with (
                storage.open(file.file_key, "rb") as source,
                source_path.open("wb") as destination,
            ):
                shutil.copyfileobj(source, destination, length=1024 * 1024)
        except Exception as exc:
            raise AudioExtractionRetryableError(
                "The source file could not be downloaded"
            ) from exc

        _ensure_audio_stream(source_path)

        _run_checked(
            [
                "ffmpeg",  # Media converter.
                "-nostdin",  # Never wait for interactive input.
                "-hide_banner",  # Keep logs focused on actionable errors.
                "-loglevel",  # Limit FFmpeg output volume.
                "error",  # Report errors only; stderr is captured on failure.
                "-fflags",
                "+discardcorrupt+genpts",  # Discard corrupt packets & generate missing PTS
                "-err_detect",  # Ignore error if possible.
                "ignore_err",
                "-i",  # Specify the downloaded source file.
                str(source_path),  # Source media path.
                "-map",  # Select the first audio stream explicitly.
                "0:a:0",  # Ignore video and additional audio streams.
                "-vn",  # Do not write a video stream.
                "-c:a",  # Select the audio encoder.
                "libopus",  # Encode to the high-quality Opus codec.
                "-ac",  # Downmix all channels to mono.
                "1",  # Use a single audio channel.
                "-b:a",  # Set the target audio bitrate.
                "64k",  # Keep the transcription input compact.
                "-vbr",  # Enable variable bitrate encoding.
                "on",  # Let Opus allocate bits where they are most useful.
                "-application",  # Tune Opus for the intended workload.
                "audio",  # Use the full-quality audio application mode.
                "-af",  # Rebuild timestamps from decoded audio samples.
                "asetpts=N/SR/TB",  # Prevent non-monotonic timestamps in the OGG muxer.
                "-ar",  # Normalize the output sample rate.
                "16000",  # Use the transcription service sample rate.
                "-f",  # Force a stable output container.
                "ogg",  # Store the Opus stream in an OGG container.
                "-y",  # Replace a temporary output if it already exists.
                str(output_path),  # Destination temporary file.
            ]
        )

        try:
            output_is_empty = (
                not output_path.is_file() or output_path.stat().st_size == 0
            )
        except OSError as exc:
            raise AudioExtractionRetryableError(
                "The extracted audio could not be inspected"
            ) from exc

        if output_is_empty:
            raise AudioExtractionError("FFmpeg produced no audio output")

        output_duration = _probe_output(output_path)

        try:
            s3_client = storage.connection.meta.client
            s3_client.upload_file(
                str(output_path),
                get_storage_bucket_name(storage),
                file.audio_file_key,
                ExtraArgs={"ContentType": "audio/ogg"},
            )
        except Exception as exc:
            raise AudioExtractionRetryableError(
                "The extracted audio could not be stored"
            ) from exc

    return output_duration
