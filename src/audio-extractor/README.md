# Audio extractor

The audio extractor is a command-line worker meant to run audio stream extraction & validation with FFmpeg and opusdec. Each process handles at most one job
from one queue (exposed as an HTTP endpoint), reports the result, and exits. If the queue is empty, it exits
without processing a job.

Set `AUDIO_EXTRACTOR_MODE` to `transcoding` or `validation` to choose the queue.
Transcoding is the default.

## API

The worker sends its token as a bearer token when polling and reporting completion.
The API returns HTTP 204 when the selected queue is empty.

The transcoding worker polls `GET /audio-jobs/transcoding/next`. A job looks like:

```json
{
  "id": "job-id",
  "job_kind": "transcoding",
  "source_url": "https://storage.example/signed-get",
  "destination_url": "https://storage.example/signed-put"
}
```

It downloads the source, converts the first audio stream to mono OGG Opus, uploads
it to the signed destination URL, then posts to
`POST /audio-jobs/transcoding/complete`. A successful response includes the audio
duration:

```json
{"id": "job-id", "status": "success", "duration_seconds": 12.5}
```

The validation worker polls `GET /audio-jobs/validation/next`. Its job looks like:

```json
{
  "id": "job-id",
  "job_kind": "validation",
  "source_url": "https://storage.example/signed-get"
}
```

It downloads the source and checks the OGG Opus stream with `opusinfo` and
`opusdec`, then posts to `POST /audio-jobs/validation/complete`:

```json
{"id": "job-id", "status": "success"}
```

Failed jobs are reported with `"status": "failure"` and an `error` message. The
worker also includes processing metadata in completion reports.

## Configuration

All settings use the `AUDIO_EXTRACTOR_` prefix:

| Variable | Required | Default | Description |
| --- | --- | --- | --- |
| `AUDIO_EXTRACTOR_API_URL` | Yes | — | API base URL, such as `http://localhost:8000` |
| `AUDIO_EXTRACTOR_TOKEN` | Yes | — | Bearer token, at least 32 characters long |
| `AUDIO_EXTRACTOR_MODE` | No | `transcoding` | Queue to process: `transcoding` or `validation` |
| `AUDIO_EXTRACTOR_OUTPUT_SAMPLE_RATE` | No | `16000` | Output sample rate in Hz: `8000`, `12000`, `16000`, `24000`, or `48000` |
| `AUDIO_EXTRACTOR_OUTPUT_BITRATE` | No | `64k` | Output bitrate, such as `64k` or `96k` |
| `AUDIO_EXTRACTOR_REQUEST_TIMEOUT` | No | `30` | HTTP timeout in seconds |
| `AUDIO_EXTRACTOR_COMMAND_TIMEOUT` | No | `900` | Timeout for each media command in seconds |
| `AUDIO_EXTRACTOR_MAX_INPUT_BYTES` | No | `1073741824` | Maximum downloaded file size in bytes (1 GiB) |
| `AUDIO_EXTRACTOR_WORK_DIR` | No | `/work` | Directory for temporary job files |

## Run locally

With Python 3.14+, `uv`, and the `ffmpeg` and `opus-tools` commands installed, sync
the dependencies, set the required environment variables, and run the worker:

```sh
cd src/audio-extractor
uv sync --all-groups
export AUDIO_EXTRACTOR_API_URL=http://localhost:8000
export AUDIO_EXTRACTOR_TOKEN=replace-with-a-token-at-least-32-characters
uv run python -m audio_extractor
```

Set `AUDIO_EXTRACTOR_MODE=validation` to run the validation worker. The development
dependency group includes Ruff, Pylint, and pytest.
